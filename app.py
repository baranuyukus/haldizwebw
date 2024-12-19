from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Project, Analysis, AnalysisPoint, ScheduledAnalysis, SystemSettings
from location_generator import LocationGenerator
from rank_analyzer import RankAnalyzer
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from flask_migrate import Migrate
import matplotlib
matplotlib.use('Agg')  # GUI backend yerine Agg kullan
import json
from weasyprint import HTML
import base64
from bs4 import BeautifulSoup
from functools import wraps

# .env dosyasını yükle
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Veritabanı ve login yöneticisini başlat
db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Zamanlanmış görevler için scheduler
scheduler = BackgroundScheduler()
scheduler.start()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        
        flash('Geçersiz kullanıcı adı veya şifre')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Bu kullanıcı adı zaten kullanılıyor')
            return redirect(url_for('register'))
            
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        return redirect(url_for('dashboard'))
        
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    projects = Project.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', projects=projects)

@app.route('/project/new', methods=['GET', 'POST'])
@login_required
def new_project():
    if request.method == 'POST':
        coordinates = request.form.get('coordinates', '')
        
        # Koordinatları parçala ve zoom seviyesini 11z olarak sabitle
        try:
            lat, lon = coordinates.replace('@', '').split(',')[:2]
            center_coordinates = f"@{lat},{lon},11z"  # Zoom seviyesini 11z olarak sabitleme
        except:
            flash('Geçersiz koordinat formatı. Lütfen Google Maps\'ten kopyaladığınız koordinatları kullanın.')
            return redirect(url_for('new_project'))
        
        # Yeni parametreleri al
        num_points = int(request.form.get('num_points', 16))
        shape = request.form.get('shape', 'circle')
        
        project = Project(
            name=request.form.get('name'),
            keyword=request.form.get('keyword'),
            target_business=request.form.get('target_business'),
            center_coordinates=center_coordinates,
            radius_km=float(request.form.get('radius_km', 2.0)),
            user_id=current_user.id,
            num_points=num_points,  # Yeni alan
            shape=shape  # Yeni alan
        )
        db.session.add(project)
        db.session.commit()
        
        # Analizi arka planda başlat
        scheduler.add_job(
            run_analysis,
            args=[project.id],
            id=f'initial_analysis_{project.id}'
        )
        
        flash('Proje oluşturuldu. İlk analiz arka planda çalışıyor, sonuçlar hazır olduğunda görüntüleyebilirsiniz.')
        return redirect(url_for('project_detail', project_id=project.id))
    
    return render_template('new_project.html')

@app.route('/project/<int:project_id>')
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        return redirect(url_for('dashboard'))
    
    # En son analizi kontrol et
    latest_analysis = Analysis.query.filter_by(project_id=project_id).order_by(Analysis.analysis_date.desc()).first()
    analyses = Analysis.query.filter_by(project_id=project_id).order_by(Analysis.analysis_date.desc()).all()
    
    analysis_status = 'completed' if latest_analysis and latest_analysis.map_file_path else 'running'
    
    return render_template(
        'project_detail.html',
        project=project,
        analyses=analyses,
        latest_analysis=latest_analysis,
        analysis_status=analysis_status
    )

@app.route('/analysis/<int:analysis_id>')
@login_required
def analysis_detail(analysis_id):
    analysis = Analysis.query.get_or_404(analysis_id)
    if analysis.project.user_id != current_user.id:
        return redirect(url_for('dashboard'))
    
    # Analiz noktalarını JSON'a dönüştürülebilir formata çevir
    points_data = []
    for point in analysis.points:
        points_data.append({
            'coordinates': point.coordinates,
            'latitude': point.latitude,
            'longitude': point.longitude,
            'position': point.position,
            'rating': point.rating,
            'rating_count': point.rating_count
        })
        
    return render_template('analysis_detail.html', 
                         analysis=analysis,
                         points=points_data)

@app.route('/api/run-analysis/<int:project_id>')
@login_required
def api_run_analysis(project_id):
    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
        
    analysis_id = run_analysis(project_id)
    return jsonify({'analysis_id': analysis_id})

def run_analysis(project_id):
    """Analiz işlemini gerçekleştirir"""
    with app.app_context():
        project = Project.query.get(project_id)
        
        # LocationGenerator ve RankAnalyzer'ı kullan
        lat, lon = project.center_coordinates.replace('@', '').split(',')[:2]
        location_gen = LocationGenerator(float(lat), float(lon), project.radius_km)
        
        # Analiz nesnesi oluştur
        analysis = Analysis(project_id=project_id)
        db.session.add(analysis)
        db.session.commit()
        
        # Analiz klasörü oluştur
        analysis_folder = f"static/analyses/{analysis.id}"
        os.makedirs(analysis_folder, exist_ok=True)
        
        try:
            # Koordinatları üret ve analiz et
            coordinates_list = location_gen.generate_coordinates(project.shape, project.num_points)
            analyzer = RankAnalyzer(project.target_business)
            
            # Her koordinat için veri çek ve kaydet
            for coords in coordinates_list:
                try:
                    lat, lon = coords.replace('@', '').split(',')[:2]
                    data = analyzer.get_serper_data(project.keyword, lat, lon)
                    analyzer.add_location_data(coords, data)
                    
                    # Veritabanına nokta bilgisini ekle
                    point = AnalysisPoint(
                        analysis_id=analysis.id,
                        coordinates=coords,
                        latitude=float(lat),
                        longitude=float(lon),
                        position=analyzer.get_position(data, project.target_business),
                        rating=analyzer.get_rating(data, project.target_business),
                        rating_count=analyzer.get_rating_count(data, project.target_business)
                    )
                    db.session.add(point)
                    
                except Exception as e:
                    print(f"Hata: {coords} için veri alınamadı - {str(e)}")
                    continue
            
            # Haritayı oluştur
            map_path = os.path.join(analysis_folder, 'map.html')
            analyzer.create_position_map(map_path, project.center_coordinates)
            
            # Analiz sonuçlarını güncelle
            points = analyzer.get_all_points()
            points_with_position = [p for p in points if p.get('position')]
            
            analysis.total_points = len(points)
            analysis.visible_points = len(points_with_position)
            analysis.average_position = sum(p['position'] for p in points_with_position) / len(points_with_position) if points_with_position else None
            analysis.best_position = min(p['position'] for p in points_with_position) if points_with_position else None
            analysis.worst_position = max(p['position'] for p in points_with_position) if points_with_position else None
            analysis.visibility_rate = (len(points_with_position) / len(points) * 100) if points else 0
            analysis.map_file_path = map_path.replace('static/', '')
            
            db.session.commit()
            return analysis.id
            
        except Exception as e:
            print(f"Analiz sırasında hata oluştu: {str(e)}")
            db.session.delete(analysis)
            db.session.commit()
            return None

def schedule_analysis(project_id, frequency):
    """Analizi zamanlar"""
    if frequency == 'daily':
        scheduler.add_job(
            run_analysis,
            'interval',
            days=1,
            args=[project_id],
            id=f'project_{project_id}_daily'
        )
    elif frequency == 'weekly':
        scheduler.add_job(
            run_analysis,
            'interval',
            weeks=1,
            args=[project_id],
            id=f'project_{project_id}_weekly'
        )
    elif frequency == 'monthly':
        scheduler.add_job(
            run_analysis,
            'interval',
            days=30,
            args=[project_id],
            id=f'project_{project_id}_monthly'
        )

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/project/<int:project_id>/delete', methods=['POST'])
@login_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Projeye ait analizleri sil
    analyses = Analysis.query.filter_by(project_id=project_id).all()
    for analysis in analyses:
        # Analiz dosyalarını sil
        if analysis.map_file_path:
            try:
                os.remove(os.path.join('static', analysis.map_file_path))
            except:
                pass
        if analysis.analysis_file_path:
            try:
                os.remove(os.path.join('static', analysis.analysis_file_path))
            except:
                pass
        
        # Analiz noktalarını sil
        AnalysisPoint.query.filter_by(analysis_id=analysis.id).delete()
        db.session.delete(analysis)
    
    # Zamanlanmış görevleri sil
    scheduler_jobs = [
        f'project_{project_id}_daily',
        f'project_{project_id}_weekly',
        f'project_{project_id}_monthly'
    ]
    for job_id in scheduler_jobs:
        try:
            scheduler.remove_job(job_id)
        except:
            pass
    
    # Projeyi sil
    db.session.delete(project)
    db.session.commit()
    
    flash('Proje başarıyla silindi.')
    return redirect(url_for('dashboard'))

@app.route('/analysis/<int:analysis_id>/delete', methods=['POST'])
@login_required
def delete_analysis(analysis_id):
    analysis = Analysis.query.get_or_404(analysis_id)
    if analysis.project.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Analiz dosyalarını sil
    if analysis.map_file_path:
        try:
            os.remove(os.path.join('static', analysis.map_file_path))
        except:
            pass
    if analysis.analysis_file_path:
        try:
            os.remove(os.path.join('static', analysis.analysis_file_path))
        except:
            pass
    
    # Analiz noktalarını sil
    AnalysisPoint.query.filter_by(analysis_id=analysis_id).delete()
    
    # Analizi sil
    project_id = analysis.project_id
    db.session.delete(analysis)
    db.session.commit()
    
    flash('Analiz başarıyla silindi.')
    return redirect(url_for('project_detail', project_id=project_id))

def get_map_base64(html_path):
    """HTML haritayı base64 kodlu veri URI'sine dönüştürür"""
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
            
        # BeautifulSoup ile HTML'i parse et
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Harita div'ini bul
        map_div = soup.find('div', {'class': 'folium-map'})
        if not map_div:
            return None
            
        # CSS ve JavaScript'i HTML içine yerleştir
        map_html = f"""
        <div style="width: 100%; height: 600px;">
            {str(map_div)}
        </div>
        """
        
        # Base64'e dönüştür
        map_base64 = base64.b64encode(map_html.encode()).decode()
        return f"data:text/html;base64,{map_base64}"
    except Exception as e:
        print(f"Harita dönüştürme hatası: {str(e)}")
        return None

@app.route('/analysis/<int:analysis_id>/pdf')
@login_required
def download_pdf_report(analysis_id):
    analysis = Analysis.query.get_or_404(analysis_id)
    if analysis.project.user_id != current_user.id:
        abort(403)
    
    # Tablo satırlarını oluşturan yardımcı fonksiyon
    def generate_table_rows(points):
        rows = []
        for point in points:
            position_class = ''
            if point['position']:
                if point['position'] <= 3:
                    position_class = 'color: #28a745;'
                elif point['position'] <= 10:
                    position_class = 'color: #ffc107;'
                else:
                    position_class = 'color: #dc3545;'
            
            rows.append(f"""
            <tr>
                <td>{point['coordinates']}</td>
                <td style="{position_class}">
                    {point['position'] if point['position'] else 'Görünmüyor'}
                </td>
                <td>{point['rating'] if point['rating'] else '-'}</td>
                <td>{point['rating_count'] if point['rating_count'] else '-'}</td>
            </tr>
            """)
        return '\n'.join(rows)
    
    # PDF rapor oluştur
    static_dir = os.path.join(app.static_folder, f'analyses/{analysis.id}')
    os.makedirs(static_dir, exist_ok=True)
    
    try:
        # Analiz noktalarını hazırla
        points_data = []
        for point in analysis.points:
            points_data.append({
                'coordinates': point.coordinates,
                'position': point.position,
                'rating': point.rating,
                'rating_count': point.rating_count
            })
        
        # Sıralama dağılımını hesapla
        distribution = [0, 0, 0, 0, 0]  # [1-3, 4-10, 11-20, 20+, Görünmüyor]
        for point in points_data:
            if not point['position']:
                distribution[4] += 1
            elif point['position'] <= 3:
                distribution[0] += 1
            elif point['position'] <= 10:
                distribution[1] += 1
            elif point['position'] <= 20:
                distribution[2] += 1
            else:
                distribution[3] += 1
        
        # PDF raporu oluştur
        pdf_path = os.path.join(static_dir, 'report.pdf')
        
        # Harita PNG dosyasının yolu
        map_png_path = os.path.join(app.root_path, 'static', analysis.map_file_path.replace('.html', '.png'))
        
        # HTML şablonu oluştur
        html_template = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                h1 {{ color: #333; text-align: center; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .section {{ margin: 20px 0; }}
                .stats {{ 
                    display: grid;
                    grid-template-columns: repeat(4, 1fr);
                    gap: 20px;
                    margin: 20px 0;
                }}
                .stat-box {{ 
                    padding: 20px; 
                    background: #f8f9fa; 
                    border-radius: 10px;
                    text-align: center;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                }}
                .stat-box h3 {{
                    margin: 0;
                    font-size: 16px;
                    color: #666;
                }}
                .stat-box p {{
                    margin: 10px 0 0 0;
                    font-size: 24px;
                    font-weight: bold;
                    color: #333;
                }}
                .map-container {{ text-align: center; margin: 20px 0; }}
                .map-container img {{ 
                    width: 100%;
                    max-width: 1200px;
                    border-radius: 10px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                }}
                .distribution-container {{
                    margin: 20px 0;
                    padding: 20px;
                    background: #f8f9fa;
                    border-radius: 10px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                }}
                .distribution-item {{
                    display: flex;
                    align-items: center;
                    margin: 10px 0;
                }}
                .distribution-label {{
                    flex: 1;
                    font-size: 14px;
                }}
                .distribution-bar {{
                    flex: 3;
                    height: 24px;
                    background: #eee;
                    border-radius: 12px;
                    overflow: hidden;
                    margin: 0 10px;
                }}
                .distribution-bar-fill {{
                    height: 100%;
                    transition: width 0.3s ease;
                }}
                .distribution-value {{
                    flex: 0 0 50px;
                    text-align: right;
                    font-weight: bold;
                }}
                .footer {{ text-align: center; margin-top: 50px; color: #666; }}
                table {{ 
                    width: 100%; 
                    border-collapse: collapse; 
                    margin: 20px 0;
                    font-size: 14px;
                }}
                th, td {{ 
                    padding: 12px; 
                    text-align: left; 
                    border-bottom: 1px solid #ddd;
                }}
                th {{ 
                    background-color: #f8f9fa;
                    font-weight: bold;
                }}
                h2 {{
                    color: #333;
                    margin-top: 40px;
                    margin-bottom: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Sıralama Analiz Raporu</h1>
                <p>İşletme: {analysis.project.target_business}</p>
                <p>Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
            </div>
            
            <div class="section">
                <div class="stats">
                    <div class="stat-box">
                        <h3>Görünürlük Oranı</h3>
                        <p>%{analysis.visibility_rate:.1f}</p>
                    </div>
                    <div class="stat-box">
                        <h3>Ortalama Sıralama</h3>
                        <p>{analysis.average_position:.1f}</p>
                    </div>
                    <div class="stat-box">
                        <h3>En İyi Sıralama</h3>
                        <p>{analysis.best_position}</p>
                    </div>
                    <div class="stat-box">
                        <h3>En Kötü Sıralama</h3>
                        <p>{analysis.worst_position}</p>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>Sıralama Dağılımı</h2>
                <div class="distribution-container">
                    <div class="distribution-item">
                        <span class="distribution-label">1-3. sıra</span>
                        <div class="distribution-bar">
                            <div class="distribution-bar-fill" style="width: {(distribution[0]/len(points_data))*100}%; background-color: #28a745;"></div>
                        </div>
                        <span class="distribution-value">{distribution[0]}</span>
                    </div>
                    <div class="distribution-item">
                        <span class="distribution-label">4-10. sıra</span>
                        <div class="distribution-bar">
                            <div class="distribution-bar-fill" style="width: {(distribution[1]/len(points_data))*100}%; background-color: #ffc107;"></div>
                        </div>
                        <span class="distribution-value">{distribution[1]}</span>
                    </div>
                    <div class="distribution-item">
                        <span class="distribution-label">11-20. sıra</span>
                        <div class="distribution-bar">
                            <div class="distribution-bar-fill" style="width: {(distribution[2]/len(points_data))*100}%; background-color: #fd7e14;"></div>
                        </div>
                        <span class="distribution-value">{distribution[2]}</span>
                    </div>
                    <div class="distribution-item">
                        <span class="distribution-label">20+ sıra</span>
                        <div class="distribution-bar">
                            <div class="distribution-bar-fill" style="width: {(distribution[3]/len(points_data))*100}%; background-color: #dc3545;"></div>
                        </div>
                        <span class="distribution-value">{distribution[3]}</span>
                    </div>
                    <div class="distribution-item">
                        <span class="distribution-label">Görünmüyor</span>
                        <div class="distribution-bar">
                            <div class="distribution-bar-fill" style="width: {(distribution[4]/len(points_data))*100}%; background-color: #6c757d;"></div>
                        </div>
                        <span class="distribution-value">{distribution[4]}</span>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>Sıralama Haritası</h2>
                <div class="map-container">
                    <img src="file://{map_png_path}" alt="Sıralama Haritası">
                </div>
            </div>
            
            <div class="section">
                <h2>Analiz Noktaları</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Koordinatlar</th>
                            <th>Sıralama</th>
                            <th>Puan</th>
                            <th>Değerlendirme Sayısı</th>
                        </tr>
                    </thead>
                    <tbody>
                        {generate_table_rows(points_data)}
                    </tbody>
                </table>
            </div>
            
            <div class="footer">
                <p>© {datetime.now().year} Maps Rank Tracker. Tüm hakları saklıdır.</p>
            </div>
        </body>
        </html>
        """
        
        # HTML'i PDF'e dönüştür
        HTML(string=html_template).write_pdf(pdf_path)
        
        # PDF'i indir
        return send_file(
            pdf_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'analiz_raporu_{analysis.id}.pdf'
        )
    except Exception as e:
        print(f"PDF oluşturma hatası: {str(e)}")
        flash('PDF raporu oluşturulurken bir hata oluştu.')
        return redirect(url_for('analysis_detail', analysis_id=analysis_id))

@app.route('/api/project/<int:project_id>/stats')
@login_required
def api_project_stats(project_id):
    project = Project.query.get_or_404(project_id)
    if project.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # En son analizi bul
    latest_analysis = Analysis.query.filter_by(project_id=project_id).order_by(Analysis.analysis_date.desc()).first()
    
    if latest_analysis:
        return jsonify({
            'lastAnalysis': latest_analysis.analysis_date.isoformat(),
            'visibility': latest_analysis.visibility_rate,
            'avgPosition': latest_analysis.average_position
        })
    
    return jsonify({
        'lastAnalysis': None,
        'visibility': 0,
        'avgPosition': 0
    })

@app.route('/api/dashboard/stats')
@login_required
def api_dashboard_stats():
    # Tüm projelerin analizlerini al
    analyses = Analysis.query.join(Project).filter(Project.user_id == current_user.id).all()
    
    # Temel istatistikler
    total_analyses = len(analyses)
    
    if analyses:
        avg_visibility = sum(a.visibility_rate for a in analyses) / total_analyses
        avg_position = sum(a.average_position for a in analyses if a.average_position) / total_analyses
    else:
        avg_visibility = 0
        avg_position = 0
    
    # Görünürlük trendi için son 30 günlük veri
    thirty_days_ago = datetime.now() - timedelta(days=30)
    trend_analyses = Analysis.query.join(Project).filter(
        Project.user_id == current_user.id,
        Analysis.analysis_date >= thirty_days_ago
    ).order_by(Analysis.analysis_date.asc()).all()
    
    visibility_trend = {
        'dates': [a.analysis_date.strftime('%d.%m') for a in trend_analyses],
        'values': [a.visibility_rate for a in trend_analyses]
    }
    
    # Sıralama dağılımı
    ranking_distribution = [0, 0, 0, 0, 0]  # [1-3, 4-10, 11-20, 20+, Görünmüyor]
    
    for analysis in analyses:
        for point in analysis.points:
            if not point.position:
                ranking_distribution[4] += 1  # Görünmüyor
            elif point.position <= 3:
                ranking_distribution[0] += 1
            elif point.position <= 10:
                ranking_distribution[1] += 1
            elif point.position <= 20:
                ranking_distribution[2] += 1
            else:
                ranking_distribution[3] += 1
    
    return jsonify({
        'totalAnalyses': total_analyses,
        'avgVisibility': round(avg_visibility, 1),
        'avgPosition': round(avg_position, 1),
        'visibilityTrend': visibility_trend,
        'rankingDistribution': ranking_distribution
    })

# Admin middleware
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Bu sayfaya erişim yetkiniz yok.')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Admin routes
@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    total_projects = Project.query.count()
    total_analyses = Analysis.query.count()
    users = User.query.all()
    
    # API key bilgilerini al
    settings = SystemSettings.query.order_by(SystemSettings.id.desc()).first()
    current_api_key = settings.serper_api_key if settings else os.getenv('SERPER_API_KEY')
    api_key_updated_at = settings.updated_at if settings else None
    api_key_updated_by = settings.updated_by if settings else None
    
    return render_template('admin/dashboard.html',
                         total_users=total_users,
                         total_projects=total_projects,
                         total_analyses=total_analyses,
                         users=users,
                         current_api_key=current_api_key,
                         api_key_updated_at=api_key_updated_at,
                         api_key_updated_by=api_key_updated_by)

@app.route('/admin/api-key', methods=['POST'])
@login_required
@admin_required
def admin_update_api_key():
    api_key = request.form.get('api_key')
    if not api_key:
        flash('API anahtarı boş olamaz.')
        return redirect(url_for('admin_dashboard'))
    
    # Yeni ayarı kaydet
    settings = SystemSettings(
        serper_api_key=api_key,
        updated_by_id=current_user.id
    )
    db.session.add(settings)
    db.session.commit()
    
    # .env dosyasını güncelle
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    env_lines = []
    with open(env_path, 'r') as f:
        for line in f:
            if line.startswith('SERPER_API_KEY='):
                line = f'SERPER_API_KEY={api_key}\n'
            env_lines.append(line)
    
    with open(env_path, 'w') as f:
        f.writelines(env_lines)
    
    flash('API anahtarı başarıyla güncellendi.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/user/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def admin_toggle_user_status(user_id):
    user = User.query.get_or_404(user_id)
    if user == current_user:
        flash('Kendi hesabınızın durumunu değiştiremezsiniz.')
        return redirect(url_for('admin_dashboard'))
    
    user.is_active = not user.is_active
    db.session.commit()
    
    flash(f"Kullanıcı durumu {'aktif' if user.is_active else 'pasif'} olarak güncellendi.")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/user/<int:user_id>/make-admin', methods=['POST'])
@login_required
@admin_required
def admin_make_admin(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Bu kullanıcı zaten admin.')
        return redirect(url_for('admin_dashboard'))
    
    user.is_admin = True
    db.session.commit()
    
    flash('Kullanıcı admin olarak atandı.')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000) 
