import wx
import os
import json
import threading
import win32con
import speech
import api
import player
import hooks
from constants import STANDARD_GENRES, GENRE_TAG_MAPPING

# Ruta de la app para guardar config
if getattr(wx.App, 'frozen', False):
    application_path = os.path.dirname(wx.App.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(application_path, 'config.json')

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
        self.current_stations = []
        self.favorite_stations = [] # TODO: Cargar de archivo
        self.translation_cache = {}
        
        # Cargar volumen guardado (por defecto 30)
        self.volume = self.load_volume()
        
        self.current_page = 0
        self.current_genre_page = 0
        self.current_search = ""
        self.current_genre = ""
        
        # UI
        self.init_ui()
        
        # Cargar servidores en segundo plano
        threading.Thread(target=self.load_servers, daemon=True).start()
        
        # Iniciar Hook de Windows
        self.hook = hooks.WindowsHook(self.on_key_down)
        self.hook.start()
        
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
        
        lbl = wx.StaticText(tab, label="Buscar emisoras por nombre:")
        sizer.Add(lbl, 0, wx.ALL, 5)
        
        self.txt_search = wx.TextCtrl(tab, style=wx.TE_PROCESS_ENTER)
        self.txt_search.Bind(wx.EVT_TEXT_ENTER, self.on_search_enter)
        sizer.Add(self.txt_search, 0, wx.EXPAND | wx.ALL, 5)
        
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
        
    def on_key_down(self, vk, mask):
        # Ctrl + R: Reproducir/Detener
        if vk == ord('R') and (mask & hooks.MOD_CTRL):
            wx.CallAfter(self.toggle_playback)
            return True
            
        # Ctrl + C: Copiar URL
        if vk == ord('C') and (mask & hooks.MOD_CTRL):
            wx.CallAfter(self.copy_current_url)
            return True
            
        # F8: Subir Volumen
        if vk == win32con.VK_F8:
            wx.CallAfter(self.adjust_volume, 5)
            return True
            
        # F7: Bajar Volumen
        if vk == win32con.VK_F7:
            wx.CallAfter(self.adjust_volume, -5)
            return True
            
        # Ctrl + Izquierda: Página Anterior
        if vk == win32con.VK_LEFT and (mask & hooks.MOD_CTRL):
            wx.CallAfter(self.on_prev_page, None)
            return True
            
        # Ctrl + Derecha: Página Siguiente
        if vk == win32con.VK_RIGHT and (mask & hooks.MOD_CTRL):
            wx.CallAfter(self.on_next_page, None)
            return True
            
        # Alt + 1, 2, 3, 4: Cambiar de pestaña
        if mask & hooks.MOD_ALT:
            if vk == ord('1'): wx.CallAfter(self.notebook.SetSelection, 0); return True
            if vk == ord('2'): wx.CallAfter(self.notebook.SetSelection, 1); return True
            if vk == ord('3'): wx.CallAfter(self.notebook.SetSelection, 2); return True
            if vk == ord('4'): wx.CallAfter(self.notebook.SetSelection, 3); return True
            
        return False
        
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
        
        station = self.current_stations[idx]
        
        menu = wx.Menu()
        item_fav = menu.Append(wx.ID_ANY, "Agregar/Quitar Favorito")
        item_copy = menu.Append(wx.ID_ANY, "Copiar URL")
        
        self.Bind(wx.EVT_MENU, lambda e: self.on_menu_fav(station), item_fav)
        self.Bind(wx.EVT_MENU, lambda e: self.on_menu_copy(station), item_copy)
        
        self.PopupMenu(menu)
        menu.Destroy()
        
    def on_menu_fav(self, station):
        speech.say("Función de favoritos no implementada aún en wxPython.")
        
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
        if idx != wx.NOT_FOUND and idx < len(self.current_stations):
            station = self.current_stations[idx]
            self.on_menu_copy(station)
        
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
    
    def load_servers(self):
        self.SetStatusText("Obteniendo servidores...")
        self.servers = api.get_radio_browser_servers()
        self.SetStatusText("Listo")
        self.load_recent_stations()
        
    def load_recent_stations(self, page=0):
        self.SetStatusText("Cargando estaciones recientes...")
        def _bg():
            stations = api.load_recent_stations(self.servers, page)
            for s in stations:
                s['country_es'] = api.translate_location(s.get('country', ''), self.translation_cache)
            wx.CallAfter(self.update_stations_list, stations)
        threading.Thread(target=_bg, daemon=True).start()
        
    def update_stations_list(self, stations):
        self.current_stations = stations
        self.lst_stations.Clear()
        for s in stations:
            name = s.get('name', 'Sin nombre')
            country = s.get('country_es', '')
            self.lst_stations.Append(f"{name} ({country})")
        self.SetStatusText("Listo")
        speech.say(f"Se cargaron {len(stations)} estaciones.")
        
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
                
        if idx < len(self.current_stations):
            station = self.current_stations[idx]
            
            current_playing = self.player.current_station
            
            if self.player.is_playing() and current_playing and current_playing.get('stationuuid') == station.get('stationuuid'):
                self.player.stop()
                self.btn_play.SetLabel("Reproducir")
                speech.say("Reproducción detenida.")
            else:
                url = station.get('url_resolved') or station.get('url')
                if url:
                    vol = self.slider_volume.GetValue() / 100.0
                    self.player.play(url, vol)
                    self.player.current_station = station
                    self.btn_play.SetLabel("Detener")
                    speech.say(f"Reproduciendo {station.get('name')}")
                else:
                    speech.say("No se encontró URL de stream.")
                    
    def get_active_list(self):
        sel = self.notebook.GetSelection()
        if sel == 0: return self.lst_stations
        if sel == 1: return self.lst_genre_stations
        if sel == 2: return self.lst_favorites
        return None
        
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
            def _bg():
                stations = api.search_stations(query, self.servers, 0)
                for s in stations:
                    s['country_es'] = api.translate_location(s.get('country', ''), self.translation_cache)
                wx.CallAfter(self.update_stations_list, stations)
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
        def _bg():
            if self.current_search:
                stations = api.search_stations(self.current_search, self.servers, page)
            else:
                stations = api.load_recent_stations(self.servers, page)
            for s in stations:
                s['country_es'] = api.translate_location(s.get('country', ''), self.translation_cache)
            wx.CallAfter(self.update_stations_list, stations)
        threading.Thread(target=_bg, daemon=True).start()
        
    def on_genre_load(self, event):
        idx = self.cmb_genre.GetSelection()
        if idx != wx.NOT_FOUND:
            genre = STANDARD_GENRES[idx]
            self.current_genre = genre
            self.current_genre_page = 0
            self.SetStatusText(f"Cargando género {genre}...")
            def _bg():
                stations = api.load_genre_stations(genre, self.servers, 0, GENRE_TAG_MAPPING)
                for s in stations:
                    s['country_es'] = api.translate_location(s.get('country', ''), self.translation_cache)
                wx.CallAfter(self.update_genre_list, stations)
            threading.Thread(target=_bg, daemon=True).start()
            
    def update_genre_list(self, stations):
        self.current_stations = stations
        self.lst_genre_stations.Clear()
        for s in stations:
            name = s.get('name', 'Sin nombre')
            country = s.get('country_es', '')
            self.lst_genre_stations.Append(f"{name} ({country})")
        self.SetStatusText("Listo")
        speech.say("Estaciones de género cargadas.")
        
    def on_genre_prev(self, event): pass
    def on_genre_next(self, event): pass
    
    def on_close(self, event):
        self.save_volume()
        self.hook.stop()
        event.Skip()

if __name__ == '__main__':
    app = RadioApp()
    app.MainLoop()
