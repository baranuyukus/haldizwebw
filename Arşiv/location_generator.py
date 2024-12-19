import math
from geopy.distance import geodesic

class LocationGenerator:
    def __init__(self, center_lat, center_lon, radius_km):
        self.center_lat = float(center_lat)
        self.center_lon = float(center_lon)
        self.radius_km = float(radius_km)

    def generate_coordinates(self, pattern="circle", num_points=16):
        """Belirtilen desende koordinat noktaları üretir"""
        if pattern == "circle":
            return self._generate_circle_coordinates(num_points)
        elif pattern == "square":
            return self._generate_square_coordinates(num_points)
        else:
            raise ValueError(f"Geçersiz desen: {pattern}")

    def _generate_circle_coordinates(self, num_points):
        """Daire şeklinde koordinat noktaları üretir"""
        coordinates = []
        
        # Merkez noktayı ekle
        coordinates.append(f"@{self.center_lat},{self.center_lon}")
        
        # Çemberdeki noktaları ekle
        for i in range(num_points):
            angle = (2 * math.pi * i) / num_points
            point = self._get_point_at_distance(angle)
            coordinates.append(f"@{point[0]},{point[1]}")
            
            # İç çemberde noktalar ekle (yarı yarıçapta)
            if self.radius_km > 1:
                inner_point = self._get_point_at_distance(angle, self.radius_km / 2)
                coordinates.append(f"@{inner_point[0]},{inner_point[1]}")
        
        return coordinates

    def _generate_square_coordinates(self, num_points):
        """Kare şeklinde koordinat noktaları üretir"""
        coordinates = []
        
        # Merkez noktayı ekle
        coordinates.append(f"@{self.center_lat},{self.center_lon}")
        
        # Karenin kenar uzunluğunu hesapla (yarıçapın 2 katı)
        side_length = self.radius_km * 2
        
        # Nokta sayısından ızgara boyutunu hesapla
        grid_size = int(math.sqrt(num_points))
        
        # Izgara aralığını hesapla
        step = side_length / (grid_size - 1)
        
        # Başlangıç noktasını hesapla (sol üst köşe)
        start_lat = self.center_lat + (self.radius_km / 111.32)  # 1 derece yaklaşık 111.32 km
        start_lon = self.center_lon - (self.radius_km / (111.32 * math.cos(math.radians(self.center_lat))))
        
        # Izgaradaki her nokta için
        for i in range(grid_size):
            for j in range(grid_size):
                lat = start_lat - (i * step / 111.32)
                lon = start_lon + (j * step / (111.32 * math.cos(math.radians(lat))))
                coordinates.append(f"@{lat},{lon}")
        
        return coordinates

    def _get_point_at_distance(self, angle, distance_km=None):
        """Belirli bir açı ve mesafede nokta üretir"""
        if distance_km is None:
            distance_km = self.radius_km
            
        # Dünya'nın yaklaşık yarıçapı (km)
        R = 6371.0
        
        # Açıyı radyandan dereceye çevir
        brng = math.degrees(angle)
        
        # Mesafeyi radyana çevir
        d = distance_km / R
        
        # Başlangıç noktasının koordinatlarını radyana çevir
        lat1 = math.radians(self.center_lat)
        lon1 = math.radians(self.center_lon)
        
        # Yeni noktanın koordinatlarını hesapla
        lat2 = math.asin(
            math.sin(lat1) * math.cos(d) +
            math.cos(lat1) * math.sin(d) * math.cos(math.radians(brng))
        )
        
        lon2 = lon1 + math.atan2(
            math.sin(math.radians(brng)) * math.sin(d) * math.cos(lat1),
            math.cos(d) - math.sin(lat1) * math.sin(lat2)
        )
        
        # Radyandan dereceye çevir
        lat2 = math.degrees(lat2)
        lon2 = math.degrees(lon2)
        
        return lat2, lon2