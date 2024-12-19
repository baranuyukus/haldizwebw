import requests
import folium
import os
import re
from datetime import datetime

class RankAnalyzer:
    def __init__(self, target_business):
        self.target_business = target_business
        self.locations_data = []
        self.serper_api_key = os.getenv('SERPER_API_KEY')

    def normalize_business_name(self, name):
        """İşletme adını normalize eder"""
        if not name:
            return ""
        # Küçük harfe çevir
        name = name.lower()
        # Türkçe karakterleri değiştir
        name = name.replace('ı', 'i').replace('ğ', 'g').replace('ü', 'u').replace('ş', 's').replace('ö', 'o').replace('ç', 'c')
        # Noktalama işaretlerini ve fazla boşlukları temizle
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', ' ', name).strip()
        return name

    def business_names_match(self, name1, name2, similarity_threshold=0.85):
        """İki işletme isminin benzerliğini kontrol eder"""
        if not name1 or not name2:
            return False
            
        name1 = self.normalize_business_name(name1)
        name2 = self.normalize_business_name(name2)
        
        # Tam eşleşme kontrolü
        if name1 == name2:
            return True
            
        # Kelime bazlı karşılaştırma
        words1 = set(name1.split())
        words2 = set(name2.split())
        
        # Eğer hedef işletme adı diğer ismin içinde tam olarak geçiyorsa
        if ' '.join(words1) in ' '.join(words2) or ' '.join(words2) in ' '.join(words1):
            return True
            
        # Önemli kelimeleri kontrol et
        important_words1 = {w for w in words1 if len(w) > 2 and w not in {'ve', 'ile'}}
        important_words2 = {w for w in words2 if len(w) > 2 and w not in {'ve', 'ile'}}
        
        # Önemli kelimelerin en az %80'i eşleşmeli
        if not important_words1 or not important_words2:
            return False
            
        common_words = important_words1.intersection(important_words2)
        match_ratio = len(common_words) / min(len(important_words1), len(important_words2))
        
        if match_ratio >= 0.8:
            return True
            
        # Levenshtein mesafesi kontrolü
        distance = self.levenshtein_distance(name1, name2)
        max_length = max(len(name1), len(name2))
        if max_length == 0:
            return False
            
        similarity = 1 - (distance / max_length)
        return similarity >= similarity_threshold

    def levenshtein_distance(self, s1, s2):
        """İki string arasındaki Levenshtein mesafesini hesaplar"""
        if len(s1) < len(s2):
            return self.levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def get_serper_data(self, keyword, lat, lon):
        """Serper API'den veri çeker"""
        url = "https://google.serper.dev/maps"
        payload = {
            "q": keyword,
            "hl": "tr",
            "ll": f"@{lat},{lon},11z",  # Zoom seviyesini 11 olarak sabitliyoruz
            "type": "maps",
            "limit": 20  # Sonuç limitini 20'ye çıkarıyoruz
        }
        headers = {
            "X-API-KEY": self.serper_api_key,
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            response.raise_for_status()  # HTTP hatalarını kontrol et
            data = response.json()
            
            # Debug bilgisi
            print(f"\nAPI İsteği yapıldı: {lat}, {lon}")
            print(f"Toplam sonuç sayısı: {len(data.get('places', []))}")
            
            return data
        except Exception as e:
            print(f"API hatası: {str(e)}")
            return {"places": []}

    def get_position(self, data, business_name):
        """Verilen işletmenin sıralamasını bulur"""
        if 'places' not in data or not data['places']:
            print("API'den veri alınamadı veya sonuç bulunamadı.")
            return None
            
        # Debug bilgisi
        print(f"\nAranan işletme: {business_name}")
        print(f"API'den gelen toplam işletme sayısı: {len(data['places'])}")
        print("API'den gelen işletmeler:")
        
        # Tüm işletmeleri listele
        all_businesses = []
        for i, place in enumerate(data['places'], 1):
            title = place.get('title', '')
            print(f"{i}. {title}")
            all_businesses.append({
                'title': title,
                'position': i,
                'rating': place.get('rating', 0),
                'rating_count': place.get('ratingCount', 0)
            })
            
        # Önce tam eşleşme ara
        for business in all_businesses:
            if self.normalize_business_name(business['title']) == self.normalize_business_name(business_name):
                print(f"TAM EŞLEŞME BULUNDU: {business['title']} (Pozisyon: {business['position']})")
                return business['position']
        
        # Tam eşleşme bulunamazsa, benzerlik kontrolü yap
        highest_similarity = 0
        best_match = None
        
        for business in all_businesses:
            name1 = self.normalize_business_name(business['title'])
            name2 = self.normalize_business_name(business_name)
            
            # Kelime bazlı karşılaştırma
            words1 = set(name1.split())
            words2 = set(name2.split())
            
            # Tam kelime eşleşmesi kontrolü
            if business_name.lower() in business['title'].lower():
                print(f"Kelime eşleşmesi bulundu: {business['title']} (Pozisyon: {business['position']})")
                return business['position']
            
            # Benzerlik oranı hesapla
            distance = self.levenshtein_distance(name1, name2)
            max_length = max(len(name1), len(name2))
            similarity = 1 - (distance / max_length) if max_length > 0 else 0
            
            if similarity > highest_similarity:
                highest_similarity = similarity
                best_match = business
        
        # Sadece yüksek benzerlik oranında eşleştir
        if highest_similarity >= 0.85 and best_match:
            print(f"Yüksek benzerlik bulundu: {best_match['title']} (Benzerlik: {highest_similarity:.2f}, Pozisyon: {best_match['position']})")
            return best_match['position']
        
        print("Eşleşme bulunamadı.")
        return None

    def get_rating(self, data, business_name):
        """Verilen işletmenin puanını bulur"""
        if 'places' not in data:
            return None
            
        # Önce tam eşleşme ara
        for place in data['places']:
            if self.normalize_business_name(place.get('title', '')) == self.normalize_business_name(business_name):
                return place.get('rating')
        
        # Tam eşleşme yoksa benzerlik kontrolü yap
        highest_similarity = 0
        best_match_rating = None
        
        for place in data['places']:
            name1 = self.normalize_business_name(place.get('title', ''))
            name2 = self.normalize_business_name(business_name)
            
            if business_name.lower() in place.get('title', '').lower():
                return place.get('rating')
            
            distance = self.levenshtein_distance(name1, name2)
            max_length = max(len(name1), len(name2))
            similarity = 1 - (distance / max_length) if max_length > 0 else 0
            
            if similarity > highest_similarity:
                highest_similarity = similarity
                best_match_rating = place.get('rating')
        
        if highest_similarity >= 0.85:
            return best_match_rating
            
        return None

    def get_rating_count(self, data, business_name):
        """Verilen işletmenin değerlendirme sayısını bulur"""
        if 'places' not in data:
            return None
            
        # Önce tam eşleşme ara
        for place in data['places']:
            if self.normalize_business_name(place.get('title', '')) == self.normalize_business_name(business_name):
                return place.get('ratingCount')
        
        # Tam eşleşme yoksa benzerlik kontrolü yap
        highest_similarity = 0
        best_match_count = None
        
        for place in data['places']:
            name1 = self.normalize_business_name(place.get('title', ''))
            name2 = self.normalize_business_name(business_name)
            
            if business_name.lower() in place.get('title', '').lower():
                return place.get('ratingCount')
            
            distance = self.levenshtein_distance(name1, name2)
            max_length = max(len(name1), len(name2))
            similarity = 1 - (distance / max_length) if max_length > 0 else 0
            
            if similarity > highest_similarity:
                highest_similarity = similarity
                best_match_count = place.get('ratingCount')
        
        if highest_similarity >= 0.85:
            return best_match_count
            
        return None

    def add_location_data(self, coordinates, data):
        """Konum verisini ekler"""
        position = self.get_position(data, self.target_business)
        rating = self.get_rating(data, self.target_business)
        rating_count = self.get_rating_count(data, self.target_business)
        
        self.locations_data.append({
            'coordinates': coordinates,
            'position': position,
            'rating': rating,
            'rating_count': rating_count
        })

    def get_all_points(self):
        """Tüm noktaların verilerini döndürür"""
        return self.locations_data

    def create_position_map(self, output_path, center_coordinates):
        """Sıralama haritası oluşturur"""
        lat, lon = center_coordinates.replace('@', '').split(',')[:2]
        
        # Harita boyutunu ve başlangıç zoom seviyesini ayarla
        m = folium.Map(location=[float(lat), float(lon)], 
                      zoom_start=13,
                      width='100%',
                      height='800px',
                      control_scale=True)
        
        # Harita container CSS'i
        map_container_css = """
        <style>
        #map {
            width: 100% !important;
            height: 800px !important;
            margin: 0 auto;
            border: 2px solid #ccc;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        .leaflet-container {
            width: 100% !important;
            height: 100% !important;
        }
        </style>
        """
        
        # Merkez noktayı işaretle
        folium.Marker(
            [float(lat), float(lon)],
            popup='Merkez Nokta',
            tooltip='Merkez',
            icon=folium.Icon(color='red', icon='info-sign')
        ).add_to(m)
        
        # Her nokta için marker ekle
        for data in self.locations_data:
            coords = data['coordinates']
            lat, lon = coords.replace('@', '').split(',')[:2]
            position = data['position']
            rating = data['rating']
            rating_count = data['rating_count']
            
            # Renk ve boyut belirleme
            if position:
                if position <= 3:
                    color = '#28a745'  # Koyu yeşil
                    radius = 25
                elif position <= 10:
                    color = '#ffc107'  # Koyu turuncu
                    radius = 20
                else:
                    color = '#dc3545'  # Koyu kırmızı
                    radius = 15
            else:
                color = '#6c757d'  # Koyu gri
                radius = 12
            
            # Popup içeriği hazırlama
            popup_html = f"""
            <div style='font-family: Arial, sans-serif; font-size: 14px; min-width: 200px; padding: 10px;'>
                <h4 style='margin: 0 0 10px 0; color: {color}; font-size: 16px;'>
                    {position if position else 'Görünmüyor'}. Sıra
                </h4>
                <p style='margin: 5px 0;'>
                    {f'<b>Puan:</b> {rating}/5.0' if rating else ''}<br>
                    {f'<b>Değerlendirme:</b> {rating_count}' if rating_count else ''}
                </p>
                <p style='margin: 5px 0; font-size: 12px; color: #666;'>
                    Koordinatlar: {lat}, {lon}
                </p>
            </div>
            """
            
            # Daire marker ekleme
            circle = folium.CircleMarker(
                location=[float(lat), float(lon)],
                radius=radius,
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=f"<b>{position}. sıra</b>" if position else "<b>Görünmüyor</b>",
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.7,
                weight=3,
                opacity=0.9
            ).add_to(m)
            
            # Sıralama numarasını gösteren metin ekleme
            if position:
                folium.map.Marker(
                    [float(lat), float(lon)],
                    icon=folium.DivIcon(
                        html=f'''
                            <div style="
                                background-color: {color};
                                color: white;
                                border-radius: 50%;
                                width: 24px;
                                height: 24px;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                font-weight: bold;
                                font-size: 14px;
                                box-shadow: 0 0 5px rgba(0,0,0,0.3);
                            ">
                                {position}
                            </div>
                        ''',
                        icon_size=(24, 24),
                        icon_anchor=(12, 12)
                    )
                ).add_to(m)
        
        # Harita lejantı ekleme
        legend_html = """
        <div style="
            position: fixed; 
            bottom: 20px; 
            right: 20px; 
            z-index: 1000; 
            background-color: white;
            padding: 15px; 
            border: 2px solid #ccc; 
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
            font-family: Arial, sans-serif;
            font-size: 14px;
            max-width: 200px;
        ">
            <h4 style="margin: 0 0 10px 0;">Sıralama Göstergeleri</h4>
            <div style="display: flex; align-items: center; margin: 5px 0;">
                <span style="color: #28a745; font-size: 24px; margin-right: 10px;">●</span>
                <span>1-3. sıra</span>
            </div>
            <div style="display: flex; align-items: center; margin: 5px 0;">
                <span style="color: #ffc107; font-size: 24px; margin-right: 10px;">●</span>
                <span>4-10. sıra</span>
            </div>
            <div style="display: flex; align-items: center; margin: 5px 0;">
                <span style="color: #dc3545; font-size: 24px; margin-right: 10px;">●</span>
                <span>10+ sıra</span>
            </div>
            <div style="display: flex; align-items: center; margin: 5px 0;">
                <span style="color: #6c757d; font-size: 24px; margin-right: 10px;">●</span>
                <span>Görünmüyor</span>
            </div>
        </div>
        """
        
        # CSS ve JavaScript eklemeleri
        m.get_root().html.add_child(folium.Element(map_container_css))
        m.get_root().html.add_child(folium.Element(legend_html))
        
        # Haritayı HTML olarak kaydet
        m.save(output_path)
        
        # PNG versiyonunu oluştur
        png_path = output_path.replace('.html', '.png')
        
        # Folium plugins.Draw kullanarak PNG oluştur
        from folium import plugins
        
        # Draw kontrolünü ekle
        draw = plugins.Draw()
        draw.add_to(m)
        
        # Haritayı PNG olarak kaydet
        import io
        from PIL import Image
        
        img_data = m._to_png()
        img = Image.open(io.BytesIO(img_data))
        img.save(png_path)