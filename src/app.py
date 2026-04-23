import time
import sys
import os
import json
import random
import socket
import threading
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QLineEdit, QListWidget, QPushButton, QComboBox, QLabel, QTextEdit,
    QMessageBox, QSlider, QMenu
)
from PyQt6.QtCore import pyqtSignal, QObject, QThread, QUrl, Qt
from PyQt6.QtGui import QDesktopServices, QAction, QIcon
from ffpyplayer.player import MediaPlayer
from accessible_output2.outputs.auto import Auto
import requests


# --- Constants and Global Functions ---

STANDARD_GENRES = [
    "Pop", "Rock", "Jazz", "Electrónica", "Hip Hop", "Clásica", "Country", "Blues",
    "R&B", "Metal", "Folk", "Música del mundo", "Latina", "Reggae", "Dance",
    "Alternativa", "Indie", "Gospel", "Banda sonora", "Infantil"
]

GENRE_TAG_MAPPING = {
    "Pop": ["pop", "top40", "hits"],
    "Rock": ["rock", "classic rock", "hard rock", "alternative rock", "indie rock"],
    "Jazz": ["jazz", "smooth jazz", "blues jazz"],
    "Electrónica": ["electronic", "dance", "techno", "house", "trance", "edm"],
    "Hip Hop": ["hip hop", "rap", "rnb"],
    "Clásica": ["classical", "orchestra", "opera"],
    "Country": ["country", "nashville"],
    "Blues": ["blues"],
    "R&B": ["rnb", "soul"],
    "Metal": ["metal", "heavy metal", "death metal"],
    "Folk": ["folk", "acoustic"],
    "Música del mundo": ["world", "ethnic", "international"],
    "Latina": ["latin", "salsa", "merengue", "bachata", "reggaeton"],
    "Reggae": ["reggae", "dub"],
    "Dance": ["dance", "club", "house"],
    "Alternativa": ["alternative", "indie"],
    "Indie": ["indie", "alternative"],
    "Gospel": ["gospel"],
    "Banda sonora": ["soundtrack", "movie scores"],
    "Infantil": ["children", "kids"],
}

PAGE_SIZE = 20

if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

FAVORITOS_FILE = os.path.join(application_path, 'favoritos.json')
TRANSLATION_CACHE_FILE = os.path.join(application_path, 'translations_cache.json')


def load_translation_cache():
    try:
        with open(TRANSLATION_CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        with open(TRANSLATION_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)
        return {}

def save_translation_cache(cache_data):
    with open(TRANSLATION_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=4)



class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)
    station_loaded = pyqtSignal(QListWidget, list)
    status_update = pyqtSignal(str)
    announce = pyqtSignal(str)
    progress_update = pyqtSignal(int, int)

class RadioBrowserWorkerObject(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    station_loaded = pyqtSignal(QListWidget, list)
    status_update = pyqtSignal(str)
    announce = pyqtSignal(str)

    def __init__(self, endpoint, list_widget, main_window, page):
        super().__init__()
        self.endpoint = endpoint
        self.list_widget = list_widget
        self.main_window = main_window
        self.page = page
        self._stop_flag = threading.Event()

    def stop(self):
        self._stop_flag.set()

    def run(self):
        if not self.main_window.radio_browser_servers:
            self.error.emit(("Error de Red", "No hay servidores de Radio Browser disponibles."))
            self.status_update.emit("Error: Sin servidores")
            self.announce.emit("Error al cargar estaciones, no hay servidores disponibles")
            self.finished.emit()
            return

        offset = self.page * PAGE_SIZE
        connector = '&' if '?' in self.endpoint else '?'
        endpoint_url = f"{self.endpoint}{connector}offset={offset}&limit={PAGE_SIZE}&hidebroken=true"
        headers = {'User-Agent': 'MyRadioBrowserApp/1.0'}

        for base_url in self.main_window.radio_browser_servers:
            if self._stop_flag.is_set():
                self.finished.emit()
                return
            try:
                api_url = f"{base_url}{endpoint_url}"
                response = requests.get(api_url, headers=headers, timeout=10)
                response.raise_for_status()
                stations = response.json()
                
                if self._stop_flag.is_set():
                    self.finished.emit()
                    return

                if stations:
                    self._process_stations(stations)
                else:
                    self.status_update.emit("No se encontraron más estaciones.")
                    self.announce.emit("No se encontraron más estaciones.")
                self.finished.emit()
                return
            except requests.exceptions.RequestException as e:
                continue
        
        self.error.emit(("Error de Red", "No se pudieron cargar estaciones de ningún servidor de Radio Browser."))
        self.status_update.emit("Error al cargar estaciones")
        self.announce.emit("Error al cargar estaciones")
        self.finished.emit()

    def _process_stations(self, stations):
        self.main_window.stations[self.list_widget] = stations
        station_names = [
            f"{station.get('name', 'Nombre desconocido')} - {self.main_window.translate_location(station.get('state', ''))}, {self.main_window.translate_location(station.get('country', ''))}"
            for station in stations
        ]
        self.station_loaded.emit(self.list_widget, station_names)
        self.status_update.emit("Listo")
        self.announce.emit("Estaciones cargadas")

class RadioBrowserWorker(QThread):
    def __init__(self, endpoint, list_widget, main_window, page, parent=None):
        super().__init__(parent)
        self.worker_object = RadioBrowserWorkerObject(endpoint, list_widget, main_window, page)
        self.worker_object.moveToThread(self)
        self.started.connect(self.worker_object.run)

        # Forward signals from worker_object
        self.worker_object.finished.connect(self.quit)
        self.worker_object.finished.connect(self.deleteLater)
        self.worker_object.error.connect(self.signals.error)
        self.worker_object.station_loaded.connect(self.signals.station_loaded)
        self.worker_object.status_update.connect(self.signals.status_update)
        self.worker_object.announce.connect(self.signals.announce)

    def stop(self):
        self.worker_object.stop()

    # WorkerSignals is still needed for MainWindow to connect to
    signals = WorkerSignals()



# --- Main Application Window ---

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RadioBrowser")
        self.setGeometry(100, 100, 800, 600)

        self.speaker = Auto()
        self.translation_cache = load_translation_cache()

        self.stations = {}
        self.favorite_stations = self.load_favorites()
        self.media_player = None
        self.current_station = None
        self.volume = 100
        self.radio_browser_servers = []
        self.recent_page = 0
        self.genre_page = 0
        self.current_search_query = ""
        self.current_genre = ""

        self.play_stop_button = None
        self.volume_label = None
        self.volume_slider = None

        self.active_workers = []

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)

        # Create Tabs
        self.create_home_tab()
        self.create_genres_tab()
        self.create_favorites_tab()
        self.create_about_tab()

        self.play_stop_button = QPushButton("Reproducir")
        self.play_stop_button.clicked.connect(self.on_play_stop_toggle)
        self.layout.addWidget(self.play_stop_button)

        self.volume_label = QLabel(f"Volumen: {self.volume}%")
        self.layout.addWidget(self.volume_label)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.volume)
        self.volume_slider.valueChanged.connect(self.on_volume_slider_changed)
        self.layout.addWidget(self.volume_slider)
        self.volume_label.setBuddy(self.volume_slider)

        # Conectar la señal currentChanged a la función on_tab_changed
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.get_radio_browser_servers()
        self.update_favorites_list()
        self.setup_accelerators()
        self.announce("Aplicación de radio iniciada")
        self._update_volume_display_and_player()

        self.start_loading_data()

    def start_loading_data(self):
        self.recent_stations_list.clear()
        self.announce("Cargando estaciones")

        # Load initial page (page 0)
        self._load_recent_stations_page(0)



    def create_home_tab(self):
        self.home_tab = QWidget()
        self.tabs.addTab(self.home_tab, "&Inicio")
        layout = QVBoxLayout(self.home_tab)

        self.search_ctrl = QLineEdit()
        self.search_ctrl.setPlaceholderText("Buscar emisoras por nombre...")
        self.search_ctrl.returnPressed.connect(self.on_search)
        layout.addWidget(self.search_ctrl)

        recent_stations_label = QLabel("Emisoras:")
        layout.addWidget(recent_stations_label)

        self.recent_stations_list = QListWidget()
        self.recent_stations_list.setAccessibleName("Emisoras")
        self.recent_stations_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.recent_stations_list.customContextMenuRequested.connect(self.on_context_menu)
        self.recent_stations_list.itemDoubleClicked.connect(self.on_station_double_clicked)
        self.recent_stations_list.setMinimumHeight(200)
        layout.addWidget(self.recent_stations_list)

        pagination_layout = QVBoxLayout()
        self.recent_prev_button = QPushButton("< Anterior")
        self.recent_next_button = QPushButton("Siguiente >")
        self.recent_prev_button.clicked.connect(self.on_recent_prev)
        self.recent_next_button.clicked.connect(self.on_recent_next)
        pagination_layout.addWidget(self.recent_prev_button)
        pagination_layout.addWidget(self.recent_next_button)
        layout.addLayout(pagination_layout)

    def create_genres_tab(self):
        self.genres_tab = QWidget()
        self.tabs.addTab(self.genres_tab, "&Géneros")
        layout = QVBoxLayout(self.genres_tab)

        genre_label = QLabel("Elige un género:")
        layout.addWidget(genre_label)

        self.genre_combo = QComboBox()
        self.genre_combo.setAccessibleName("Elige un género")
        self.genre_combo.addItems(STANDARD_GENRES)
        layout.addWidget(self.genre_combo)

        self.load_genre_button = QPushButton("Cargar Género")
        self.load_genre_button.clicked.connect(self.on_genre_selected)
        layout.addWidget(self.load_genre_button)

        genre_stations_label = QLabel("Emisoras:")
        layout.addWidget(genre_stations_label)

        self.genre_stations_list = QListWidget()
        self.genre_stations_list.setAccessibleName("Emisoras")
        self.genre_stations_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.genre_stations_list.customContextMenuRequested.connect(self.on_context_menu)
        self.genre_stations_list.itemDoubleClicked.connect(self.on_station_double_clicked)
        self.genre_stations_list.setMinimumHeight(200)
        layout.addWidget(self.genre_stations_list)

        pagination_layout = QVBoxLayout()
        self.genre_prev_button = QPushButton("< Anterior")
        self.genre_next_button = QPushButton("Siguiente >")
        self.genre_prev_button.clicked.connect(self.on_genre_prev)
        self.genre_next_button.clicked.connect(self.on_genre_next)
        pagination_layout.addWidget(self.genre_prev_button)
        pagination_layout.addWidget(self.genre_next_button)
        layout.addLayout(pagination_layout)

    def create_favorites_tab(self):
        self.favorites_tab = QWidget()
        self.tabs.addTab(self.favorites_tab, "&Favoritos")
        layout = QVBoxLayout(self.favorites_tab)

        favorites_label = QLabel("Favoritos:")
        layout.addWidget(favorites_label)

        self.favorites_list = QListWidget()
        self.favorites_list.setAccessibleName("Favoritos")
        self.favorites_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.favorites_list.customContextMenuRequested.connect(self.on_context_menu)
        self.favorites_list.itemDoubleClicked.connect(self.on_station_double_clicked)
        self.favorites_list.setMinimumHeight(200)
        layout.addWidget(self.favorites_list)

    def create_about_tab(self):
        self.about_tab = QWidget()
        self.tabs.addTab(self.about_tab, "&Acerca de")
        layout = QVBoxLayout(self.about_tab)

        about_label = QLabel("Acerca de:")
        layout.addWidget(about_label)

        about_text = """Este programa fue desarrollado por Gemini.\n
Ideas, pruebas, prompts y mantenimiento a cargo de Kevin O'Higgins.\n
Si tenés errores, sugerencias, o si formás parte de la población femenina, podés contactarme a ohigginsk460@gmail.com.\n
Si querés que me pueda comprar una cerveza este fin de semana, agradecería enormemente una donación."""
        self.about_text_ctrl = QTextEdit()
        self.about_text_ctrl.setReadOnly(True)
        self.about_text_ctrl.setPlainText(about_text)
        self.about_text_ctrl.setAccessibleName("Acerca de")
        self.about_text_ctrl.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.about_text_ctrl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByKeyboard | Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextBrowserInteraction)
        layout.addWidget(self.about_text_ctrl)

        self.paypal_button = QPushButton("Donar por &PayPal")
        self.mercadopago_button = QPushButton("Donar por &Mercado Pago (Argentina)")
        self.paypal_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://www.paypal.com/paypalme/KevOHiggins")))
        self.mercadopago_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://link.mercadopago.com.ar/kevohiggins")))
        layout.addWidget(self.paypal_button)
        layout.addWidget(self.mercadopago_button)

    def announce(self, message):
        try:
            self.speaker.speak(message, interrupt=True)
        except Exception as e:
            print(f"Error announcing message: {e}. Falling back to console output.")
            print(f"ANUNCIO: {message}")

    def load_favorites(self):
        try:
            with open(FAVORITOS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            with open(FAVORITOS_FILE, 'w', encoding='utf-8') as f:
                json.dump([], f)
            return []

    def save_favorites(self):
        with open(FAVORITOS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.favorite_stations, f, ensure_ascii=False, indent=4)

    def get_radio_browser_servers(self):
        try:
            ip_addresses = [res[4][0] for res in socket.getaddrinfo("all.api.radio-browser.info", 80, type=socket.SOCK_STREAM)]
            server_names = []
            for ip in ip_addresses:
                try:
                    hostname = socket.gethostbyaddr(ip)[0]
                    server_names.append(hostname)
                except socket.herror:
                    pass
            self.radio_browser_servers = [f"https://{name}" for name in server_names]
            random.shuffle(self.radio_browser_servers)
        except socket.gaierror as e:
            error_message = f"Error de DNS al obtener servidores de radio: {e}"
            self.announce(error_message)
            self.radio_browser_servers = ["https://nl1.api.radio-browser.info", "https://de1.api.radio-browser.info"]
        except Exception as e:
            error_message = f"Error inesperado al obtener servidores de radio: {e}"
            self.announce(error_message)
            self.radio_browser_servers = ["https://nl1.api.radio-browser.info", "https://de1.api.radio-browser.info"]

        # Load initial page (page 0)
        self._load_recent_stations_page(0)



    def update_station_list(self, list_widget, station_names):
        list_widget.clear()
        list_widget.addItems(station_names)
        


    def show_error(self, error_data):
        title, message = error_data
        QMessageBox.critical(self, title, message)

    def set_status_text(self, text):
        self.statusBar().showMessage(text)

    def on_search(self):
        query = self.search_ctrl.text()
        if query:
            self.recent_page = 0
            self.current_search_query = query
            self.set_status_text(f"Buscando '{query}'...")
            self.announce(f"Buscando {query}")

            self._load_search_stations_page(query, 0)


    def on_recent_prev(self):
        if self.recent_page > 0:
            self.recent_page -= 1
            self.set_status_text(f"Cargando página {self.recent_page + 1} de estaciones recientes...")
            self.announce(f"Página {self.recent_page + 1}")

            self._load_recent_stations_page(self.recent_page)



    def on_recent_next(self):
        self.recent_page += 1
        self.set_status_text(f"Cargando página {self.recent_page + 1} de estaciones recientes...")
        self.announce(f"Página {self.recent_page + 1}")

        self._load_recent_stations_page(self.recent_page)


    def on_genre_selected(self):
        index = self.genre_combo.currentIndex()
        self.genre_stations_list.clear()
        genre = self.genre_combo.itemText(index)
        if genre:
            self.genre_page = 0
            self.current_genre = genre
            self.set_status_text(f"Cargando género '{genre}'...")
            self.announce(f"Cargando {genre}")

            self._load_genre_stations_page(genre, 0)


    def on_genre_prev(self):
        if self.genre_page > 0:
            self.genre_page -= 1
            self.set_status_text(f"Cargando página {self.genre_page + 1} de estaciones por género...")
            self.announce(f"Página {self.genre_page + 1}")

            if self.current_genre:
                self._load_genre_stations_page(self.current_genre, self.genre_page)



    def on_genre_next(self):
        self.genre_page += 1
        self.set_status_text(f"Cargando página {self.genre_page + 1} de estaciones por género...")
        self.announce(f"Página {self.genre_page + 1}")

        if self.current_genre:
            self._load_genre_stations_page(self.current_genre, self.genre_page)


    def play_station(self, station, announce_playback=False):
        if not station:
            return
        
        stream_url = station.get("url_resolved") or station.get("url")
        if stream_url:
            if self.media_player:
                self.on_stop() # Stop current playback before starting a new one

            self.current_station = station
            self.set_status_text(f"Reproduciendo: {station['name']}...")
            if announce_playback:
                self.announce(f"Intentando reproducir {station['name']}")
            
            player_options = {
                'an': None,
                'sn': None,
                'volume': self.volume / 100.0,
            }
            try:
                self.media_player = MediaPlayer(stream_url, ff_opts=player_options)
                self.update_play_stop_button_text()
            except Exception as e:
                self.show_error(("Error de Reproducción", f"Error al iniciar la reproducción: {e}"))
                self.announce("Error al iniciar la reproducción")
                self.on_stop() # Ensure player state is reset on error
        else:
            self.show_error(("Error de Reproducción", "No se encontró URL de streaming para esta estación."))
            self.announce("No se encontró URL de streaming para esta estación.")



    def on_stop(self, announce_playback=False):
        if self.media_player:
            self.media_player.close_player()
            self.media_player = None
        self.current_station = None
        self.set_status_text("Reproducción detenida.")
        if announce_playback:
            self.announce("Reproducción detenida")
        self.update_play_stop_button_text()

    def on_station_double_clicked(self, item):
        list_widget = self.sender()
        selection = list_widget.currentRow()
        station = self.get_station_from_list(list_widget, selection)
        if station:
            self.play_station(station)

    def on_context_menu(self, pos):
        list_widget = self.sender()
        item = list_widget.itemAt(pos)

        if not item:
            return

        selection = list_widget.row(item)
        station = self.get_station_from_list(list_widget, selection)
        if not station:
            return

        menu = QMenu()
        
        play_stop_action = QAction("Reproducir/Detener", self)
        play_stop_action.triggered.connect(lambda: self.on_context_play_stop(station))
        menu.addAction(play_stop_action)

        menu.addSeparator()

        is_favorite = any(fav['stationuuid'] == station['stationuuid'] for fav in self.favorite_stations)
        fav_action = QAction("Quitar de favoritos" if is_favorite else "Añadir a favoritos", self)
        fav_action.triggered.connect(lambda: self.on_context_toggle_favorite(station))
        menu.addAction(fav_action)

        copy_url_action = QAction("Copiar enlace de stream", self)
        copy_url_action.triggered.connect(lambda: self.on_context_copy_url(station))
        menu.addAction(copy_url_action)

        menu.exec(list_widget.mapToGlobal(pos))

    def on_context_play_stop(self, station):
        if self.media_player and self.current_station and self.current_station['stationuuid'] == station['stationuuid']:
            self.on_stop()
        else:
            self.play_station(station)

    def on_context_toggle_favorite(self, station):
        is_favorite = any(fav['stationuuid'] == station['stationuuid'] for fav in self.favorite_stations)
        if is_favorite:
            self.favorite_stations = [fav for fav in self.favorite_stations if fav['stationuuid'] != station['stationuuid']]
            self.set_status_text(f"'{station['name']}' quitado de favoritos.")
            self.announce("Quitado de favoritos")
        else:
            self.favorite_stations.append(station)
            self.set_status_text(f"'{station['name']}' añadido a favoritos.")
            self.announce("Añadido a favoritos")
        self.update_favorites_list()
        self.save_favorites()

    def on_context_copy_url(self, station):
        stream_url = station.get("url_resolved") or station.get("url")
        if stream_url:
            QApplication.clipboard().setText(stream_url)
            self.set_status_text(f"Enlace copiado: {stream_url}")
            self.announce("Enlace copiado")
        else:
            self.set_status_text("Esta estación no tiene un enlace de stream.")
            self.announce("Esta estación no tiene enlace")

    def update_favorites_list(self):
        self.favorites_list.clear()
        fav_names = [
            f"{station.get('name', 'Nombre desconocido')} - {self.translate_location(station.get('state', ''))}, {self.translate_location(station.get('country', ''))}"
            for station in self.favorite_stations
        ]
        self.favorites_list.addItems(fav_names)

    def get_station_from_list(self, list_widget, selection):
        if list_widget == self.favorites_list:
            if 0 <= selection < len(self.favorite_stations):
                return self.favorite_stations[selection]
        else:
            station_list = self.stations.get(list_widget, [])
            if 0 <= selection < len(station_list):
                return station_list[selection]
        return None

    def translate_location(self, text):
        if not text or not text.strip():
            return text
        if text in self.translation_cache:
            return self.translation_cache[text]
        try:
            if text.isnumeric() or len(text) <= 2:
                return text
            url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=es&dt=t&q=" + text
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=5)
            response.raise_for_status()
            data = response.json()
            translated_text = data[0][0][0]
            self.translation_cache[text] = translated_text
            return translated_text
        except Exception:
            pass

    def get_current_list_widget(self):
        """Devuelve el QListWidget activo según la pestaña actual."""
        index = self.tabs.currentIndex()
        if index == 0:
            return self.recent_stations_list
        elif index == 1:
            return self.genre_stations_list
        elif index == 2:
            return self.favorites_list
        return None

    def get_selected_station(self):
        """Devuelve la estación seleccionada de la pestaña activa."""
        list_widget = self.get_current_list_widget()
        if list_widget:
            selection = list_widget.currentRow()
            if selection != -1:
                return self.get_station_from_list(list_widget, selection)
        return None



    def _load_recent_stations_page(self, page_number):
        endpoint = "/json/stations/lastchange"
        worker = RadioBrowserWorker(endpoint, self.recent_stations_list, self, page_number, parent=self)
        self.active_workers.append(worker)
        worker.signals.station_loaded.connect(self.update_station_list)
        worker.signals.error.connect(self.show_error)
        worker.signals.finished.connect(lambda: self.active_workers.remove(worker))
        worker.signals.announce.connect(self.announce)
        worker.start()



    def _load_search_stations_page(self, query, page_number):
        endpoint = f"/json/stations/search?name={query}"
        worker = RadioBrowserWorker(endpoint, self.recent_stations_list, self, page_number, parent=self)
        self.active_workers.append(worker)
        worker.signals.station_loaded.connect(self.update_station_list)
        worker.signals.error.connect(self.show_error)
        worker.signals.finished.connect(lambda: self.active_workers.remove(worker))
        worker.signals.announce.connect(self.announce)
        worker.start()



    def _load_genre_stations_page(self, genre, page_number):
        mapped_tags = GENRE_TAG_MAPPING.get(genre, [genre.lower()])
        tag_params = "&".join([f"tag={tag}" for tag in mapped_tags])
        endpoint = f"/json/stations/search?{tag_params}"
        worker = RadioBrowserWorker(endpoint, self.genre_stations_list, self, page_number, parent=self)
        self.active_workers.append(worker)
        worker.signals.station_loaded.connect(self.update_station_list)
        worker.signals.error.connect(self.show_error)
        worker.signals.finished.connect(lambda: self.active_workers.remove(worker))
        worker.signals.announce.connect(self.announce)
        worker.start()



    def closeEvent(self, event):
        self.save_favorites()
        save_translation_cache(self.translation_cache)

        if self.media_player:
            self.media_player.close_player()
            self.media_player = None

        # No need to explicitly stop other workers here, as they should be managed by their own lifecycle
        # and the main application exit will handle their termination.
        self.active_workers.clear() # Explicitly clear the list

        super().closeEvent(event)

    def setup_accelerators(self):
        # Play/Stop
        play_stop_action = QAction("Reproducir/Detener", self)
        play_stop_action.setShortcut("Ctrl+R")
        play_stop_action.triggered.connect(self.on_accel_play_stop)
        self.addAction(play_stop_action)

        # Next Page
        next_page_action = QAction("Página Siguiente", self)
        next_page_action.setShortcut("Ctrl+Right")
        next_page_action.triggered.connect(self.on_accel_next_page)
        self.addAction(next_page_action)

        # Previous Page
        prev_page_action = QAction("Página Anterior", self)
        prev_page_action.setShortcut("Ctrl+Left")
        prev_page_action.triggered.connect(self.on_accel_prev_page)
        self.addAction(prev_page_action)

        # Toggle Favorite
        toggle_favorite_action = QAction("Añadir/Quitar Favorito", self)
        toggle_favorite_action.setShortcut("Ctrl+F")
        toggle_favorite_action.triggered.connect(self.on_accel_toggle_favorite)
        self.addAction(toggle_favorite_action)

        # Copy URL
        copy_url_action = QAction("Copiar URL", self)
        copy_url_action.setShortcut("Ctrl+C")
        copy_url_action.triggered.connect(self.on_accel_copy_url)
        self.addAction(copy_url_action)

        # Volume Up
        vol_up_action = QAction("Subir Volumen", self)
        vol_up_action.setShortcut("F8")
        vol_up_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        vol_up_action.triggered.connect(self.on_accel_vol_up)
        self.addAction(vol_up_action)

        # Volume Down
        vol_down_action = QAction("Bajar Volumen", self)
        vol_down_action.setShortcut("F7")
        vol_down_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        vol_down_action.triggered.connect(self.on_accel_vol_down)
        self.addAction(vol_down_action)

        # Tab Navigation (Alt+1, Alt+2, etc.)
        tab1_action = QAction("Ir a Inicio", self)
        tab1_action.setShortcut("Alt+1")
        tab1_action.triggered.connect(lambda: self.tabs.setCurrentIndex(0))
        self.addAction(tab1_action)

        tab2_action = QAction("Ir a Géneros", self)
        tab2_action.setShortcut("Alt+2")
        tab2_action.triggered.connect(lambda: self.tabs.setCurrentIndex(1))
        self.addAction(tab2_action)

        tab3_action = QAction("Ir a Favoritos", self)
        tab3_action.setShortcut("Alt+3")
        tab3_action.triggered.connect(lambda: self.tabs.setCurrentIndex(2))
        self.addAction(tab3_action)

        tab4_action = QAction("Ir a Acerca de", self)
        tab4_action.setShortcut("Alt+4")
        tab4_action.triggered.connect(lambda: self.tabs.setCurrentIndex(3))
        self.addAction(tab4_action)

    def on_accel_play_stop(self):
        station = self.get_selected_station()
        if station:
            if self.media_player and self.current_station and self.current_station['stationuuid'] == station['stationuuid']:
                self.on_stop(announce_playback=True)
            else:
                self.play_station(station, announce_playback=True)

    def on_accel_next_page(self):
        current_tab_index = self.tabs.currentIndex()
        if current_tab_index == 0:
            self.on_recent_next()
        elif current_tab_index == 1:
            self.on_genre_next()

    def on_accel_prev_page(self):
        current_tab_index = self.tabs.currentIndex()
        if current_tab_index == 0:
            self.on_recent_prev()
        elif current_tab_index == 1:
            self.on_genre_prev()

    def on_accel_toggle_favorite(self):
        station = self.get_selected_station()
        if station:
            self.on_context_toggle_favorite(station)

    def on_accel_copy_url(self):
        station = self.get_selected_station()
        if station:
            self.on_context_copy_url(station)

    def on_accel_vol_up(self):
        self.volume = min(100, self.volume + 5)
        if self.media_player:
            self.media_player.set_volume(self.volume / 100.0)
        self._update_volume_display_and_player(announce_percentage=True)

    def on_accel_vol_down(self):
        self.volume = max(0, self.volume - 5)
        if self.media_player:
            self.media_player.set_volume(self.volume / 100.0)
        self._update_volume_display_and_player(announce_percentage=True)

    def _update_volume_display_and_player(self, announce_percentage=False):
        self.volume_label.setText(f"Volumen: {self.volume}%")
        self.volume_slider.setValue(self.volume)
        self.set_status_text(f"Volumen: {self.volume}%")
        if announce_percentage:
            self.announce(f"Volumen {self.volume} por ciento")

    def on_volume_slider_changed(self, value):
        self.volume = value
        if self.media_player:
            self.media_player.set_volume(self.volume / 100.0)
        self._update_volume_display_and_player()

    def on_play_stop_toggle(self):
        if self.media_player:
            self.on_stop()
        else:
            station = self.get_selected_station()
            if station:
                self.play_station(station)

    def update_play_stop_button_text(self):
        if self.media_player:
            self.play_stop_button.setText("Detener")
        else:
            self.play_stop_button.setText("Reproducir")

    def on_tab_changed(self, index):
        if self.play_stop_button and self.volume_label and self.volume_slider:
            if index == 3: # "Acerca de" tab
                self.play_stop_button.hide()
                self.volume_label.hide()
                self.volume_slider.hide()
            else:
                self.play_stop_button.show()
                self.volume_label.show()
                self.volume_slider.show()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_win = MainWindow()
    main_win.show()
    sys.exit(app.exec())
