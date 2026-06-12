import wx
import os
import json
import threading
import speech
import api
import player
from constants import STANDARD_GENRES, GENRE_TAG_MAPPING

# Ruta de la app para guardar config
if getattr(wx.App, 'frozen', False):
    application_path = os.path.dirname(wx.App.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(application_path, 'config.json')
FAVORITES_FILE = os.path.join(application_path, 'favorites.json')

class RadioApp(wx.App):
    def OnInit(self):
        self.frame = MainFrame(None, title="RadioBrowser")
        self.frame.Show()
        return True

class MainFrame(wx.Frame):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        
        self.SetSize((800, 600))
        
        # Inicializar componentes
        self.player = player.RadioPlayer()
        self.servers = []
        self.home_stations = []
        self.genre_stations = []
        self.favorite_stations = self.load_favorites()
        self.translation_cache = self.load_cache('cache_translations.json') or {}
        
        # Cargar volumen guardado (por defecto 30)
        self.volume = self.load_volume()
        
        self.current_page = 0
        self.current_genre_page = 0
        self.current_search = ""
        self.current_genre = ""
        self.current_request_id = 0
        
        # UI
        self.init_ui()
        self.update_favorites_list()
        
        # Pre-cargar interfaz "Offline-First"
        cached_home = self.load_cache('cache_home.json')
        if cached_home:
            self.home_stations = cached_home
            self.update_stations_list(cached_home, force_ui_only=True)
            
        cached_servers = self.load_cache('cache_servers.json')
        if cached_servers:
            self.servers = cached_servers
            self.load_recent_stations()
            threading.Thread(target=self.update_servers_bg, daemon=True).start()
        else:
            threading.Thread(target=self.load_servers, daemon=True).start()
        
        # Configurar atajos de teclado locales
        self.setup_accelerators()
        
        self.Bind(wx.EVT_CLOSE, self.on_close)
        
        speech.say("Radio Browser iniciado.")
        
    def init_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Cuaderno de pestañas
        self.notebook = wx.Notebook(panel)
        sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)
        
        # Crear pestañas
        self.create_home_tab()
        self.create_genres_tab()
        self.create_favorites_tab()
        self.create_about_tab()
        
        # Controles globales (abajo)
        controls_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.btn_play = wx.Button(panel, label="Reproducir")
        self.btn_play.Bind(wx.EVT_BUTTON, self.on_play_click)
        controls_sizer.Add(self.btn_play, 0, wx.ALL, 5)
        
        self.lbl_volume = wx.StaticText(panel, label=f"Volumen: {self.volume}%")
        controls_sizer.Add(self.lbl_volume, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        
        self.slider_volume = wx.Slider(panel, value=self.volume, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
        self.slider_volume.Bind(wx.EVT_SLIDER, self.on_volume_change)
        controls_sizer.Add(self.slider_volume, 1, wx.EXPAND | wx.ALL, 5)
        
        sizer.Add(controls_sizer, 0, wx.EXPAND)
        
        # Barra de estado
        self.CreateStatusBar()
        self.SetStatusText("Listo")
        
        panel.SetSizer(sizer)
        
    def create_home_tab(self):
        tab = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Sizer horizontal para búsqueda y proveedor
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        lbl_search = wx.StaticText(tab, label="Buscar emisoras por nombre:")
        search_sizer.Add(lbl_search, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        
        self.txt_search = wx.TextCtrl(tab, style=wx.TE_PROCESS_ENTER)
        self.txt_search.Bind(wx.EVT_TEXT_ENTER, self.on_search_enter)
        search_sizer.Add(self.txt_search, 1, wx.EXPAND | wx.ALL, 5)
        
        lbl_prov = wx.StaticText(tab, label="Proveedor:")
        search_sizer.Add(lbl_prov, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        
        self.choice_provider = wx.Choice(tab, choices=["Radio-Browser", "TuneIn"])
        self.choice_provider.SetSelection(0)
        self.choice_provider.Bind(wx.EVT_CHOICE, self.on_provider_change)
        search_sizer.Add(self.choice_provider, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        
        sizer.Add(search_sizer, 0, wx.EXPAND)
        
        self.lst_stations = wx.ListBox(tab)
        self.lst_stations.Bind(wx.EVT_LISTBOX_DCLICK, self.on_station_dclick)
        self.lst_stations.Bind(wx.EVT_KEY_DOWN, self.on_list_key_down)
        self.lst_stations.Bind(wx.EVT_CONTEXT_MENU, self.on_context_menu)
        sizer.Add(self.lst_stations, 1, wx.EXPAND | wx.ALL, 5)
        
        # Paginación
        pag_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_prev = wx.Button(tab, label="< Anterior")
        self.btn_next = wx.Button(tab, label="Siguiente >")
        self.btn_prev.Bind(wx.EVT_BUTTON, self.on_prev_page)
        self.btn_next.Bind(wx.EVT_BUTTON, self.on_next_page)
        pag_sizer.Add(self.btn_prev, 1, wx.EXPAND | wx.ALL, 5)
        pag_sizer.Add(self.btn_next, 1, wx.EXPAND | wx.ALL, 5)
        
        sizer.Add(pag_sizer, 0, wx.EXPAND)
        
        tab.SetSizer(sizer)
        self.notebook.AddPage(tab, "Inicio")
        
    def create_genres_tab(self):
        tab = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        lbl = wx.StaticText(tab, label="Elige un género:")
        sizer.Add(lbl, 0, wx.ALL, 5)
        
        self.cmb_genre = wx.ComboBox(tab, choices=STANDARD_GENRES, style=wx.CB_READONLY)
        sizer.Add(self.cmb_genre, 0, wx.EXPAND | wx.ALL, 5)
        
        btn_load = wx.Button(tab, label="Cargar Género")
        btn_load.Bind(wx.EVT_BUTTON, self.on_genre_load)
        sizer.Add(btn_load, 0, wx.EXPAND | wx.ALL, 5)
        
        self.lst_genre_stations = wx.ListBox(tab)
        self.lst_genre_stations.Bind(wx.EVT_LISTBOX_DCLICK, self.on_station_dclick)
        self.lst_genre_stations.Bind(wx.EVT_KEY_DOWN, self.on_list_key_down)
        self.lst_genre_stations.Bind(wx.EVT_CONTEXT_MENU, self.on_context_menu)
        sizer.Add(self.lst_genre_stations, 1, wx.EXPAND | wx.ALL, 5)
        
        # Paginación Géneros
        pag_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_genre_prev = wx.Button(tab, label="< Anterior")
        self.btn_genre_next = wx.Button(tab, label="Siguiente >")
        self.btn_genre_prev.Bind(wx.EVT_BUTTON, self.on_genre_prev)
        self.btn_genre_next.Bind(wx.EVT_BUTTON, self.on_genre_next)
        pag_sizer.Add(self.btn_genre_prev, 1, wx.EXPAND | wx.ALL, 5)
        pag_sizer.Add(self.btn_genre_next, 1, wx.EXPAND | wx.ALL, 5)
        
        sizer.Add(pag_sizer, 0, wx.EXPAND)
        
        tab.SetSizer(sizer)
        self.notebook.AddPage(tab, "Géneros")
        
    def create_favorites_tab(self):
        tab = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        lbl = wx.StaticText(tab, label="Tus Favoritos:")
        sizer.Add(lbl, 0, wx.ALL, 5)
        
        self.lst_favorites = wx.ListBox(tab)
        self.lst_favorites.Bind(wx.EVT_LISTBOX_DCLICK, self.on_station_dclick)
        self.lst_favorites.Bind(wx.EVT_KEY_DOWN, self.on_list_key_down)
        self.lst_favorites.Bind(wx.EVT_CONTEXT_MENU, self.on_context_menu)
        sizer.Add(self.lst_favorites, 1, wx.EXPAND | wx.ALL, 5)
        
        tab.SetSizer(sizer)
        self.notebook.AddPage(tab, "Favoritos")
        
    def create_about_tab(self):
        tab = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        about_text = """Radio Browser - Versión wxPython\n
Pensado para ser liviano y accesible.\n
Usa la base de datos pública de Radio Browser.\n
¡Apoya el proyecto invitando una cerveza!"""
        
        txt = wx.TextCtrl(tab, value=about_text, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_CENTRE)
        sizer.Add(txt, 1, wx.EXPAND | wx.ALL, 10)
        
        tab.SetSizer(sizer)
        self.notebook.AddPage(tab, "Acerca de")
        
    def setup_accelerators(self):
        id_play = wx.NewIdRef()
        id_copy = wx.NewIdRef()
        id_vol_up = wx.NewIdRef()
        id_vol_down = wx.NewIdRef()
        id_prev = wx.NewIdRef()
        id_next = wx.NewIdRef()
        id_tab_1 = wx.NewIdRef()
        id_tab_2 = wx.NewIdRef()
        id_tab_3 = wx.NewIdRef()
        id_tab_4 = wx.NewIdRef()

        self.Bind(wx.EVT_MENU, lambda e: self.toggle_playback(), id=id_play)
        self.Bind(wx.EVT_MENU, lambda e: self.copy_current_url(), id=id_copy)
        self.Bind(wx.EVT_MENU, lambda e: self.adjust_volume(5), id=id_vol_up)
        self.Bind(wx.EVT_MENU, lambda e: self.adjust_volume(-5), id=id_vol_down)
        self.Bind(wx.EVT_MENU, lambda e: self.on_prev_page(None), id=id_prev)
        self.Bind(wx.EVT_MENU, lambda e: self.on_next_page(None), id=id_next)
        self.Bind(wx.EVT_MENU, lambda e: self.notebook.SetSelection(0), id=id_tab_1)
        self.Bind(wx.EVT_MENU, lambda e: self.notebook.SetSelection(1), id=id_tab_2)
        self.Bind(wx.EVT_MENU, lambda e: self.notebook.SetSelection(2), id=id_tab_3)
        self.Bind(wx.EVT_MENU, lambda e: self.notebook.SetSelection(3), id=id_tab_4)

        accel_tbl = wx.AcceleratorTable([
            (wx.ACCEL_CTRL, ord('R'), id_play),
            (wx.ACCEL_CTRL, ord('C'), id_copy),
            (wx.ACCEL_NORMAL, wx.WXK_F8, id_vol_up),
            (wx.ACCEL_NORMAL, wx.WXK_F7, id_vol_down),
            (wx.ACCEL_CTRL, wx.WXK_LEFT, id_prev),
            (wx.ACCEL_CTRL, wx.WXK_RIGHT, id_next),
            (wx.ACCEL_ALT, ord('1'), id_tab_1),
            (wx.ACCEL_ALT, ord('2'), id_tab_2),
            (wx.ACCEL_ALT, ord('3'), id_tab_3),
            (wx.ACCEL_ALT, ord('4'), id_tab_4)
        ])
        self.SetAcceleratorTable(accel_tbl)
        
    def on_list_key_down(self, event):
        keycode = event.GetKeyCode()
        if keycode in [wx.WXK_RETURN, wx.WXK_SPACE]:
            self.toggle_playback()
        else:
            event.Skip()
            
    def on_context_menu(self, event):
        active_list = self.get_active_list()
        if not active_list: return
        
        idx = active_list.GetSelection()
        if idx == wx.NOT_FOUND: return
        
        stations = self.get_active_stations()
        if idx >= len(stations): return
        station = stations[idx]
        
        menu = wx.Menu()
        item_fav = menu.Append(wx.ID_ANY, "Agregar/Quitar Favorito")
        item_copy = menu.Append(wx.ID_ANY, "Copiar URL")
        
        self.Bind(wx.EVT_MENU, lambda e: self.on_menu_fav(station), item_fav)
        self.Bind(wx.EVT_MENU, lambda e: self.on_menu_copy(station), item_copy)
        
        self.PopupMenu(menu)
        menu.Destroy()
        
    def on_menu_fav(self, station):
        uuid = station.get('stationuuid')
        found_idx = -1
        for idx, fav in enumerate(self.favorite_stations):
            if fav.get('stationuuid') == uuid:
                found_idx = idx
                break
                
        if found_idx != -1:
            self.favorite_stations.pop(found_idx)
            self.save_favorites()
            self.update_favorites_list()
            speech.say(f"Quitada de favoritos: {station.get('name')}")
            self.SetStatusText(f"Quitada de favoritos: {station.get('name')}")
        else:
            if 'provider' not in station:
                station['provider'] = 'radio-browser'
            self.favorite_stations.append(station)
            self.save_favorites()
            self.update_favorites_list()
            speech.say(f"Agregada a favoritos: {station.get('name')}")
            self.SetStatusText(f"Agregada a favoritos: {station.get('name')}")
        
    def on_menu_copy(self, station):
        url = station.get('url_resolved') or station.get('url')
        if url:
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(url))
                wx.TheClipboard.Close()
                speech.say("URL copiada al portapapeles.")
            else:
                speech.say("No se pudo abrir el portapapeles.")
        else:
            speech.say("No hay URL disponible para copiar.")
            
    def copy_current_url(self):
        active_list = self.get_active_list()
        if not active_list: return
        idx = active_list.GetSelection()
        stations = self.get_active_stations()
        if idx != wx.NOT_FOUND and idx < len(stations):
            station = stations[idx]
            self.on_menu_copy(station)

    def load_favorites(self):
        try:
            if os.path.exists(FAVORITES_FILE):
                with open(FAVORITES_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error al cargar favoritos: {e}")
        return []
        
    def save_favorites(self):
        try:
            with open(FAVORITES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.favorite_stations, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error al guardar favoritos: {e}")

    def update_favorites_list(self):
        self.lst_favorites.Clear()
        for s in self.favorite_stations:
            name = s.get('name', 'Sin nombre')
            country = s.get('country_es', '')
            provider = s.get('provider', 'radio-browser')
            prov_lbl = "TuneIn" if provider == 'tunein' else "RadioBrowser"
            self.lst_favorites.Append(f"{name} ({country}) [{prov_lbl}]")
        
    # --- Lógica ---
    
    def load_volume(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    return config.get('volume', 30)
        except Exception:
            pass
        return 30
        
    def save_volume(self):
        try:
            config = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
            
            config['volume'] = self.volume
            
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Error al guardar config: {e}")
    
    def load_cache(self, filename):
        try:
            path = os.path.join(application_path, filename)
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def save_cache(self, filename, data):
        try:
            path = os.path.join(application_path, filename)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception:
            pass
            
    def update_servers_bg(self):
        new_servers = api.get_radio_browser_servers()
        if new_servers:
            self.servers = new_servers
            self.save_cache('cache_servers.json', new_servers)

    def load_servers(self):
        self.SetStatusText("Obteniendo servidores...")
        self.servers = api.get_radio_browser_servers()
        if self.servers:
            self.save_cache('cache_servers.json', self.servers)
        self.SetStatusText("Listo")
        self.load_recent_stations()
        
    def on_provider_change(self, event):
        self.current_search = ""
        self.current_page = 0
        self.load_recent_stations()

    def load_recent_stations(self, page=0):
        sel = 0
        if hasattr(self, 'choice_provider'):
            sel = self.choice_provider.GetSelection()

        if sel == 1:
            self.SetStatusText("Cargando emisoras de TuneIn...")
        else:
            self.SetStatusText("Cargando estaciones recientes/populares...")
            
        self.current_request_id += 1
        req_id = self.current_request_id
            
        def _bg():
            if sel == 1:
                stations = api.load_tunein_local_stations()
            else:
                stations = api.load_recent_stations(self.servers, page)
                for s in stations:
                    s['country_es'] = api.translate_location(s.get('country', ''), self.translation_cache)
                    s['provider'] = 'radio-browser'
                
            wx.CallAfter(self.update_stations_list, stations, req_id, True)
        threading.Thread(target=_bg, daemon=True).start()
        
    def update_stations_list(self, stations, req_id=None, save_to_cache=False, force_ui_only=False):
        if req_id is not None and req_id != self.current_request_id:
            return
            
        self.home_stations = stations
        self.lst_stations.Clear()
        for s in stations:
            name = s.get('name', 'Sin nombre')
            country = s.get('country_es', '')
            provider = s.get('provider', 'radio-browser')
            prov_lbl = "TuneIn" if provider == 'tunein' else "RadioBrowser"
            self.lst_stations.Append(f"{name} ({country}) [{prov_lbl}]")
            
        if not force_ui_only:
            self.SetStatusText("Listo")
            speech.say(f"Se cargaron {len(stations)} estaciones.")
            self.resolve_tunein_bg(self.home_stations)
            
        if save_to_cache:
            self.save_cache('cache_home.json', stations)
            self.save_cache('cache_translations.json', self.translation_cache)
        
    def on_play_click(self, event):
        self.toggle_playback()
        
    def toggle_playback(self):
        active_list = self.get_active_list()
        if not active_list:
            speech.say("No hay lista activa.")
            return
            
        idx = active_list.GetSelection()
        if idx == wx.NOT_FOUND:
            if active_list.GetCount() > 0:
                idx = 0
                active_list.SetSelection(0)
            else:
                speech.say("No hay estaciones en la lista.")
                return
                
        stations = self.get_active_stations()
        if idx < len(stations):
            station = stations[idx]
            
            current_playing = self.player.current_station
            
            if self.player.is_playing() and current_playing and current_playing.get('stationuuid') == station.get('stationuuid'):
                self.player.stop()
                self.btn_play.SetLabel("Reproducir")
                speech.say("Reproducción detenida.")
            else:
                self.SetStatusText("Preparando reproducción...")
                speech.say("Preparando reproducción...")
                def _bg():
                    provider = station.get('provider', 'radio-browser')
                    url = None
                    error_msg = None
                    
                    if provider == 'tunein':
                        if not station.get('url_resolved'):
                            resolved = api.resolve_tunein_stream(station.get('url'))
                            if resolved:
                                station['url_resolved'] = resolved
                        url = station.get('url_resolved')
                        
                        if url:
                            url = api.resolve_stream_url(url)
                            station['url_resolved'] = url
                    else:
                        url = station.get('url_resolved') or station.get('url')
                        
                    if url and ("notcompatible" in url or "georestricted" in url):
                        url = None
                        error_msg = "La estación no es compatible o está restringida."

                    if url:
                        wx.CallAfter(self.do_play, station, url)
                    else:
                        wx.CallAfter(self.do_play_error, station, error_msg)
                threading.Thread(target=_bg, daemon=True).start()

    def do_play(self, station, url):
        vol = self.slider_volume.GetValue() / 100.0
        if self.player.play(url, vol):
            self.player.current_station = station
            self.btn_play.SetLabel("Detener")
            self.SetStatusText(f"Reproduciendo: {station.get('name')}")
            speech.say(f"Reproduciendo {station.get('name')}")
        else:
            self.SetStatusText("Error al iniciar reproducción")
            speech.say("Error al iniciar reproducción.")

    def do_play_error(self, station, error_msg=None):
        msg = error_msg if error_msg else "No se pudo obtener la URL de stream."
        self.SetStatusText(msg)
        speech.say(msg)
                    
    def get_active_list(self):
        sel = self.notebook.GetSelection()
        if sel == 0: return self.lst_stations
        if sel == 1: return self.lst_genre_stations
        if sel == 2: return self.lst_favorites
        return None

    def get_active_stations(self):
        sel = self.notebook.GetSelection()
        if sel == 0: return self.home_stations
        if sel == 1: return self.genre_stations
        if sel == 2: return self.favorite_stations
        return []
        
    def on_volume_change(self, event):
        self.volume = self.slider_volume.GetValue()
        self.lbl_volume.SetLabel(f"Volumen: {self.volume}%")
        self.player.set_volume(self.volume / 100.0)
        
    def adjust_volume(self, delta):
        self.volume = max(0, min(100, self.volume + delta))
        self.slider_volume.SetValue(self.volume)
        self.lbl_volume.SetLabel(f"Volumen: {self.volume}%")
        self.player.set_volume(self.volume / 100.0)
        speech.say(f"Volumen {self.volume} por ciento")
        
    def on_search_enter(self, event):
        query = self.txt_search.GetValue()
        if query:
            self.current_search = query
            self.current_page = 0
            self.SetStatusText(f"Buscando '{query}'...")
            
            sel = 0
            if hasattr(self, 'choice_provider'):
                sel = self.choice_provider.GetSelection()
                    
            self.current_request_id += 1
            req_id = self.current_request_id
            
            def _bg():
                if sel == 1:
                    stations = api.search_tunein_stations(query)
                else:
                    stations = api.search_stations(query, self.servers, 0)
                    for s in stations:
                        s['country_es'] = api.translate_location(s.get('country', ''), self.translation_cache)
                        s['provider'] = 'radio-browser'
                wx.CallAfter(self.update_stations_list, stations, req_id)
            threading.Thread(target=_bg, daemon=True).start()
            
    def on_station_dclick(self, event):
        self.toggle_playback()
        
    def on_prev_page(self, event):
        if self.current_page > 0:
            self.current_page -= 1
            self.load_page()
            
    def on_next_page(self, event):
        self.current_page += 1
        self.load_page()
        
    def load_page(self):
        page = self.current_page
        self.SetStatusText(f"Cargando página {page + 1}...")
        
        sel = 0
        if hasattr(self, 'choice_provider'):
            sel = self.choice_provider.GetSelection()
                
        self.current_request_id += 1
        req_id = self.current_request_id
        
        def _bg():
            if self.current_search:
                if sel == 1:
                    stations = api.search_tunein_stations(self.current_search)
                else:
                    stations = api.search_stations(self.current_search, self.servers, page)
            else:
                if sel == 1:
                    stations = api.load_tunein_local_stations() if page == 0 else []
                else:
                    stations = api.load_recent_stations(self.servers, page)
                    
            if sel != 1:
                for s in stations:
                    s['country_es'] = api.translate_location(s.get('country', ''), self.translation_cache)
                    s['provider'] = 'radio-browser'
            wx.CallAfter(self.update_stations_list, stations, req_id)
        threading.Thread(target=_bg, daemon=True).start()
        
    def on_genre_load(self, event):
        idx = self.cmb_genre.GetSelection()
        if idx != wx.NOT_FOUND:
            genre = STANDARD_GENRES[idx]
            self.current_genre = genre
            self.current_genre_page = 0
            self.SetStatusText(f"Cargando género {genre}...")
            self.current_request_id += 1
            req_id = self.current_request_id
            
            def _bg():
                stations = api.load_genre_stations(genre, self.servers, 0, GENRE_TAG_MAPPING)
                for s in stations:
                    s['country_es'] = api.translate_location(s.get('country', ''), self.translation_cache)
                    s['provider'] = 'radio-browser'
                wx.CallAfter(self.update_genre_list, stations, req_id, True)
            threading.Thread(target=_bg, daemon=True).start()
            
    def update_genre_list(self, stations, req_id=None, save_to_cache=False):
        if req_id is not None and req_id != self.current_request_id:
            return
            
        self.genre_stations = stations
        self.lst_genre_stations.Clear()
        for s in stations:
            name = s.get('name', 'Sin nombre')
            country = s.get('country_es', '')
            self.lst_genre_stations.Append(f"{name} ({country})")
        self.SetStatusText("Listo")
        speech.say("Estaciones de género cargadas.")
        self.resolve_tunein_bg(self.genre_stations)
        
        if save_to_cache:
            self.save_cache('cache_genres.json', stations)
            self.save_cache('cache_translations.json', self.translation_cache)
        
    def on_genre_prev(self, event):
        if self.current_genre_page > 0:
            self.current_genre_page -= 1
            self.load_genre_page()
            
    def on_genre_next(self, event):
        self.current_genre_page += 1
        self.load_genre_page()
        
    def load_genre_page(self):
        genre = self.current_genre
        page = self.current_genre_page
        if not genre: return
        self.SetStatusText(f"Cargando página {page + 1} de género {genre}...")
        self.current_request_id += 1
        req_id = self.current_request_id
        
        def _bg():
            stations = api.load_genre_stations(genre, self.servers, page, GENRE_TAG_MAPPING)
            for s in stations:
                s['country_es'] = api.translate_location(s.get('country', ''), self.translation_cache)
                s['provider'] = 'radio-browser'
            wx.CallAfter(self.update_genre_list, stations, req_id, True)
        threading.Thread(target=_bg, daemon=True).start()
    
    def resolve_tunein_bg(self, stations):
        def _bg():
            from concurrent.futures import ThreadPoolExecutor
            def resolve_station(s):
                if s.get('provider') == 'tunein' and not s.get('url_resolved'):
                    try:
                        resolved = api.resolve_tunein_stream(s.get('url'))
                        if resolved:
                            s['url_resolved'] = api.resolve_stream_url(resolved)
                    except Exception:
                        pass
            with ThreadPoolExecutor(max_workers=5) as executor:
                executor.map(resolve_station, stations)
        threading.Thread(target=_bg, daemon=True).start()
        
    def on_close(self, event):
        self.save_volume()
        event.Skip()

if __name__ == '__main__':
    app = RadioApp()
    app.MainLoop()
