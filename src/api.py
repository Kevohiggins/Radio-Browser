import requests
import socket
import random
import json
import os

PAGE_SIZE = 20

def get_radio_browser_servers():
    """
    Obtiene la lista de servidores activos de Radio Browser usando DNS.
    """
    try:
        ip_addresses = [res[4][0] for res in socket.getaddrinfo("all.api.radio-browser.info", 80, type=socket.SOCK_STREAM)]
        server_names = []
        for ip in ip_addresses:
            try:
                hostname = socket.gethostbyaddr(ip)[0]
                server_names.append(hostname)
            except socket.herror:
                pass
        servers = [f"https://{name}" for name in server_names]
        random.shuffle(servers)
        return servers
    except socket.gaierror:
        # Fallback si falla el DNS
        return ["https://nl1.api.radio-browser.info", "https://de1.api.radio-browser.info"]
    except Exception:
        return ["https://nl1.api.radio-browser.info", "https://de1.api.radio-browser.info"]

def fetch_stations(endpoint, servers, page=0):
    """
    Consulta estaciones a los servidores de Radio Browser.
    """
    if not servers:
        return []

    offset = page * PAGE_SIZE
    connector = '&' if '?' in endpoint else '?'
    endpoint_url = f"{endpoint}{connector}offset={offset}&limit={PAGE_SIZE}&hidebroken=true"
    headers = {'User-Agent': 'MyRadioBrowserApp/1.0'}

    for base_url in servers:
        try:
            api_url = f"{base_url}{endpoint_url}"
            response = requests.get(api_url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException:
            continue
            
    return []

def search_stations(query, servers, page=0):
    endpoint = f"/json/stations/search?name={query}"
    return fetch_stations(endpoint, servers, page)

def load_recent_stations(servers, page=0):
    endpoint = "/json/stations/lastchange"
    return fetch_stations(endpoint, servers, page)

def load_genre_stations(genre, servers, page=0, tag_mapping=None):
    if tag_mapping and genre in tag_mapping:
        mapped_tags = tag_mapping[genre]
        tag_params = "&".join([f"tag={tag}" for tag in mapped_tags])
        endpoint = f"/json/stations/search?{tag_params}"
    else:
        endpoint = f"/json/stations/search?tag={genre.lower()}"
    return fetch_stations(endpoint, servers, page)

def translate_location(text, cache):
    """
    Traduce texto usando la API gratuita de Google Translate.
    """
    if not text or not text.strip():
        return text
    if text in cache:
        return cache[text]
        
    try:
        if text.isnumeric() or len(text) <= 2:
            return text
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=es&dt=t&q=" + text
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        translated_text = data[0][0][0]
        cache[text] = translated_text
        return translated_text
    except Exception:
        return text

def search_tunein_stations(query):
    """
    Busca emisoras en TuneIn usando la API pública de RadioTime.
    """
    try:
        url = f"https://opml.radiotime.com/Search.ashx?query={query}&render=json"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        stations = []
        for item in data.get('body', []):
            if item.get('type') == 'audio':
                stations.append({
                    'name': item.get('text', 'Sin nombre'),
                    'url': item.get('URL'),  # Endpoint de sintonización (Tune.ashx)
                    'url_resolved': None,    # Se resolverá al reproducir
                    'country': 'Desconocido',
                    'country_es': 'Desconocido',
                    'image': item.get('image', ''),
                    'subtext': item.get('subtext', ''),
                    'stationuuid': item.get('guide_id', ''),
                    'provider': 'tunein'
                })
                
        # Obtener localizaciones en paralelo
        from concurrent.futures import ThreadPoolExecutor
        def fetch_and_set_location(station):
            gid = station.get('stationuuid')
            if gid:
                try:
                    desc_url = f"https://opml.radiotime.com/Describe.ashx?id={gid}&render=json"
                    r = requests.get(desc_url, headers=headers, timeout=3)
                    if r.status_code == 200:
                        desc_data = r.json()
                        if desc_data.get('body'):
                            loc = desc_data['body'][0].get('location', 'Desconocido')
                            station['country'] = loc
                            station['country_es'] = loc
                except Exception:
                    pass

        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(fetch_and_set_location, stations)
            
        return stations
    except Exception as e:
        print(f"[API] Error buscando en TuneIn: {e}")
        return []

def resolve_tunein_stream(tune_url):
    """
    Obtiene la URL directa de streaming a partir del endpoint de sintonización de TuneIn.
    """
    if not tune_url:
        return None
    try:
        connector = '&' if '?' in tune_url else '?'
        url = f"{tune_url}{connector}render=json"
        headers = {'User-Agent': 'mpv 0.38.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        for item in data.get('body', []):
            if item.get('element') == 'audio' and item.get('url'):
                return item.get('url')
    except Exception as e:
        print(f"[API] Error resolviendo stream de TuneIn: {e}")
    return None

def get_user_location():
    try:
        r = requests.get('http://ip-api.com/json/', timeout=3)
        if r.status_code == 200:
            data = r.json()
            if data.get('status') == 'success':
                return data.get('lat'), data.get('lon')
    except Exception:
        pass
    return None, None

def load_radiobrowser_local_stations(servers, page=0, limit=20, distance_meters=100000):
    lat, lon = get_user_location()
    if not lat or not lon:
        return load_recent_stations(servers, page, limit)
        
    for server in servers:
        try:
            url = f"https://{server}/json/stations/search"
            params = {
                'geo_lat': lat,
                'geo_long': lon,
                'geo_distance': distance_meters,
                'limit': limit,
                'offset': page * limit,
                'hidebroken': 'true'
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            # Ordenar manualmente por clickcount si lo deseamos, o dejar el default
            data.sort(key=lambda x: x.get('clickcount', 0), reverse=True)
            return data
        except requests.exceptions.RequestException as e:
            print(f"[API] Error cargando locales de Radio-Browser en {server}: {e}")
            continue
    return []

def load_tunein_local_stations():
    """
    Obtiene las emisoras locales de TuneIn basadas en la geolocalización de la IP.
    """
    try:
        stations = []
        urls_to_fetch = [
            "http://opml.radiotime.com/Browse.ashx?c=local&render=json",
            "http://opml.radiotime.com/Browse.ashx?c=trending&render=json"
        ]
        
        seen_uuids = set()
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        for url in urls_to_fetch:
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                for item in data.get('body', []):
                    children = item.get('children', [])
                    for child in children:
                        if child.get('type') == 'audio':
                            uuid = child.get('guide_id', '')
                            if uuid not in seen_uuids:
                                seen_uuids.add(uuid)
                                stations.append({
                                    'name': child.get('text', 'Sin nombre'),
                                    'url': child.get('URL'),
                                    'url_resolved': None,
                                    'country': 'Trending' if 'trending' in url else 'Local',
                                    'country_es': 'Trending' if 'trending' in url else 'Local',
                                    'image': child.get('image', ''),
                                    'subtext': child.get('subtext', ''),
                                    'stationuuid': uuid,
                                    'provider': 'tunein'
                                })
                    if item.get('type') == 'audio':
                        uuid = item.get('guide_id', '')
                        if uuid not in seen_uuids:
                            seen_uuids.add(uuid)
                            stations.append({
                                'name': item.get('text', 'Sin nombre'),
                                'url': item.get('URL'),
                                'url_resolved': None,
                                'country': 'Trending' if 'trending' in url else 'Local',
                                'country_es': 'Trending' if 'trending' in url else 'Local',
                                'image': item.get('image', ''),
                                'subtext': item.get('subtext', ''),
                                'stationuuid': uuid,
                                'provider': 'tunein'
                            })
                
        # Obtener localizaciones en paralelo
        from concurrent.futures import ThreadPoolExecutor
        def fetch_and_set_location(station):
            gid = station.get('stationuuid')
            if gid:
                try:
                    desc_url = f"https://opml.radiotime.com/Describe.ashx?id={gid}&render=json"
                    r = requests.get(desc_url, headers=headers, timeout=3)
                    if r.status_code == 200:
                        desc_data = r.json()
                        if desc_data.get('body'):
                            loc = desc_data['body'][0].get('location', 'Local')
                            station['country'] = loc
                            station['country_es'] = loc
                except Exception:
                    pass

        with ThreadPoolExecutor(max_workers=10) as executor:
            executor.map(fetch_and_set_location, stations)
            
        return stations
    except Exception as e:
        print(f"[API] Error cargando locales de TuneIn: {e}")
        return []

def resolve_stream_url(url, depth=0):
    """
    Sigue las redirecciones HTTP (como las de StreamTheWorld o playlists)
    para obtener la URL final directa del stream.
    """
    if not url or depth > 3:
        return url
        
    if "notcompatible.enUS.mp3" in url or "georestricted.enUS.mp3" in url:
        return url
        
    try:
        headers = {'User-Agent': 'mpv 0.38.0'}
        r = requests.get(url, headers=headers, allow_redirects=True, stream=True, timeout=5)
        final_url = r.url
        content_type = r.headers.get('Content-Type', '').lower()
        
        is_playlist = False
        if 'mpegurl' in content_type or 'scpls' in content_type or 'playlist' in content_type or 'audio/x-scpls' in content_type:
            is_playlist = True
        elif any(ext in final_url.lower() for ext in ['.m3u', '.pls', 'listen.pls']):
            # No analizar archivos HLS (.m3u8) manualmente, FFmpeg los soporta de forma nativa
            if '.m3u8' not in final_url.lower() and 'audio/mpeg' not in content_type and 'audio/aac' not in content_type:
                is_playlist = True
                
        if is_playlist:
            # Leer el contenido del playlist
            content = r.content.decode('utf-8', errors='ignore')
            r.close()
            
            for line in content.splitlines():
                line = line.strip()
                if line.lower().startswith('file') and '=' in line:
                    parts = line.split('=', 1)
                    if len(parts) == 2 and parts[1].startswith('http'):
                        return resolve_stream_url(parts[1], depth + 1)
                elif line.startswith('http'):
                    return resolve_stream_url(line, depth + 1)
        
        r.close()
        return final_url
    except Exception as e:
        print(f"[API] Error resolviendo redirecciones para {url}: {e}")
        return url
