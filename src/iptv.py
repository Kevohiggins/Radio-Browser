import os
import json
import requests
from threading import Thread

CACHE_FILE = os.path.join(os.environ.get('APPDATA', ''), 'radio_browser_iptv_cache.json')
ADULT_CACHE_FILE = os.path.join(os.environ.get('APPDATA', ''), 'radio_browser_iptv_adult_cache.json')
# URL de la lista principal y limpia de iptv-org
IPTV_URL = "https://iptv-org.github.io/iptv/index.m3u"
ADULT_URL = "http://adultiptv.net/chs.m3u"

GROUPS_ES = {
    "Animation": "Animación", "Auto": "Automotor", "Business": "Negocios", 
    "Classic": "Clásico", "Comedy": "Comedia", "Documentary": "Documentales", 
    "Education": "Educación", "Entertainment": "Entretenimiento", "Family": "Familia", 
    "Kids": "Infantil", "Lifestyle": "Estilo de Vida", "Movies": "Películas", 
    "Music": "Música", "News": "Noticias", "Religion": "Religión", 
    "Science": "Ciencia", "Shop": "Compras", "Sports": "Deportes", 
    "Travel": "Viajes", "Weather": "Clima", "General": "General", 
    "Legislative": "Legislativo", "Culture": "Cultura", "Series": "Series",
    "Adult": "Adultos"
}

from countries_es import COUNTRIES_ES

def get_country_name(code):
    return COUNTRIES_ES.get(code.lower(), code.upper())


def parse_m3u(content):
    channels = []
    lines = content.splitlines()
    current_channel = {}
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith("#EXTINF:"):
            # Extraer el nombre del canal (todo después de la última coma)
            parts = line.split(",", 1)
            name = parts[1].strip() if len(parts) > 1 else "Unknown Channel"
            
            # Intentar extraer grupo (group-title)
            group = ""
            if 'group-title="' in line:
                try:
                    group = line.split('group-title="')[1].split('"')[0]
                except:
                    pass
            
            # Extraer país desde tvg-id (ej: "123tv.de@SD" -> "de")
            country = ""
            if 'tvg-id="' in line:
                try:
                    tvg_id = line.split('tvg-id="')[1].split('"')[0]
                    tvg_id = tvg_id.split('@')[0]
                    if '.' in tvg_id:
                        parsed_country = tvg_id.rsplit('.', 1)[1].lower()
                        if len(parsed_country) == 2:
                            country = parsed_country
                except:
                    pass
            
            if country:
                country = get_country_name(country)
            if group:
                group = GROUPS_ES.get(group, group)
                
            current_channel = {
                'name': name,
                'group': group,
                'country': country
            }
        elif line.startswith("http"):
            if current_channel:
                current_channel['url'] = line
                # Añadir un identificador interno (falso UUID o hash)
                current_channel['stationuuid'] = f"iptv_{hash(line)}"
                channels.append(current_channel)
                current_channel = {}
                
    return channels

def load_cached_channels():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return []

def save_cache(channels):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(channels, f, ensure_ascii=False)
    except Exception as e:
        print(f"Error guardando caché IPTV: {e}")

def load_cached_adult_channels():
    if os.path.exists(ADULT_CACHE_FILE):
        try:
            with open(ADULT_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return []

def save_adult_cache(channels):
    try:
        with open(ADULT_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(channels, f, ensure_ascii=False)
    except Exception as e:
        print(f"Error guardando caché IPTV adultos: {e}")

def parse_adult_m3u(content):
    """Parsea la lista M3U de adultos y les fuerza group='Adultos'."""
    channels = []
    lines = content.splitlines()
    current_name = None
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            parts = line.split(",", 1)
            current_name = parts[1].strip() if len(parts) > 1 else "Canal sin nombre"
        elif line.startswith("http") and current_name:
            channels.append({
                'name': current_name,
                'group': 'Adultos',
                'country': '',
                'url': line,
                'stationuuid': f"adult_{hash(line)}"
            })
            current_name = None
    return channels

def update_channels_async(callback=None):
    """Descarga la lista M3U en segundo plano y actualiza el caché."""
    def worker():
        try:
            r = requests.get(IPTV_URL, timeout=15)
            if r.status_code == 200:
                channels = parse_m3u(r.text)
                if channels:
                    save_cache(channels)
                    if callback:
                        callback(channels)
        except Exception as e:
            print(f"Error descargando IPTV: {e}")
            if callback:
                callback(None)
                
    Thread(target=worker, daemon=True).start()

def update_adult_channels_async(callback=None):
    """Descarga la lista M3U de adultos en segundo plano."""
    def worker():
        try:
            r = requests.get(ADULT_URL, timeout=15)
            if r.status_code == 200:
                channels = parse_adult_m3u(r.text)
                if channels:
                    save_adult_cache(channels)
                    if callback:
                        callback(channels)
        except Exception as e:
            print(f"Error descargando IPTV adultos: {e}")
            if callback:
                callback(None)
    Thread(target=worker, daemon=True).start()

def get_channels(callback=None):
    """
    Intenta cargar los canales desde el caché. 
    Si no hay caché, los descarga.
    Si hay caché, devuelve esos pero igual actualiza en segundo plano.
    """
    cached = load_cached_channels()
    if not cached:
        update_channels_async(callback)
        return []
    else:
        # Actualización silenciosa en segundo plano
        update_channels_async()
        return cached

def get_adult_channels(callback=None):
    """Carga canales adultos desde caché o los descarga."""
    cached = load_cached_adult_channels()
    if not cached:
        update_adult_channels_async(callback)
        return []
    else:
        update_adult_channels_async()
        return cached

def search_channels(channels, query):
    if not query:
        return channels[:500] # Limitar a 500 para no trabar la UI
        
    query = query.lower()
    results = [c for c in channels if query in c.get('name', '').lower()]
    return results[:500]
