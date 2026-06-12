import os
import sys

# Agregar la carpeta local al PATH de DLLs para que encuentre mpv-2.dll
current_dir = os.path.abspath(os.path.dirname(__file__))
try:
    os.add_dll_directory(current_dir)
except AttributeError:
    pass # Python anterior a 3.8

os.environ["PATH"] = current_dir + os.pathsep + os.environ["PATH"]

import mpv

class RadioPlayer:
    def __init__(self):
        # Inicializar el reproductor MPV sin soporte de video ni YouTube-DL para máxima velocidad
        self.player = mpv.MPV(ytdl=False, video=False)
        self.current_station = None
        self.volume = 0.3 # Rango original 0.0 a 1.0 (interno de MPV es 0 a 100)
        self.player.volume = self.volume * 100
        self._is_playing = False
        
    def play(self, url, volume=0.3):
        """
        Inicia la reproducción de una URL de stream.
        """
        if self._is_playing:
            self.stop()
            
        self.volume = volume
        try:
            self.player.volume = self.volume * 100
            self.player.play(url)
            self._is_playing = True
            return True
        except Exception as e:
            print(f"[Player] Error al iniciar reproducción con MPV: {e}")
            return False
            
    def stop(self):
        """
        Detiene la reproducción.
        """
        if self._is_playing:
            self.player.stop()
            self._is_playing = False
            self.current_station = None
            
    def set_volume(self, volume):
        """
        Ajusta el volumen dinámicamente (0.0 a 1.0).
        """
        self.volume = volume
        self.player.volume = self.volume * 100
            
    def is_playing(self):
        return self._is_playing
