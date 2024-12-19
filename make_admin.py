from flask import Flask
from models import db, User

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    user = User.query.filter_by(username='admin').first()
    if user:
        user.is_admin = True
        db.session.commit()
        print(f"Admin yetkisi verildi: {user.username}")
    else:
        print("Kullanıcı bulunamadı") 