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
