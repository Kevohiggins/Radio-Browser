from ffpyplayer.player import MediaPlayer

class RadioPlayer:
    def __init__(self):
        self.player = None
        self.current_station = None
        self.volume = 0.3 # Rango de 0.0 a 1.0 (por defecto 30%)
        
    def play(self, url, volume=0.3):
        """
        Inicia la reproducción de una URL de stream.
        """
        if self.player:
            self.stop()
            
        self.volume = volume
        player_options = {
            'an': None, # Deshabilitar video
            'sn': None, # Deshabilitar subtítulos
        }
        try:
            self.player = MediaPlayer(url, ff_opts=player_options)
            
            # Intento básico (si la librería quiere tomarlo)
            self.player.set_volume(self.volume)
            
            return True
        except Exception as e:
            print(f"[Player] Error al iniciar reproducción: {e}")
            return False
            
    def stop(self):
        """
        Detiene la reproducción.
        """
        if self.player:
            self.player.close_player()
            self.player = None
            self.current_station = None
            
    def set_volume(self, volume):
        """
        Ajusta el volumen dinámicamente (0.0 a 1.0).
        """
        self.volume = volume
        if self.player:
            self.player.set_volume(self.volume)
            
    def is_playing(self):
        return self.player is not None
