"""
Módulo de accesibilidad híbrido (Voz).
Utiliza accessible_output2 para conectarse a lectores de pantalla nativos (NVDA, JAWS) o SAPI5,
garantizando lectura no bloqueante nativa.
"""

# Intentamos cargar auto de accessible_output2 de forma tolerante a fallos
try:
    from accessible_output2.outputs.auto import Auto
    _speaker = Auto()
except Exception as e:
    print(f"Alerta: No se pudo iniciar accessible_output2. Fallback a print. ({e})")
    _speaker = None

def play_sound(sound_type):
    """
    Función desactivada por pedido del usuario (no queremos beeps en esta app).
    """
    pass

def play_startup_sound():
    pass

def play_shutdown_sound():
    pass

def say(text, interrupt=True):
    """
    Habla usando accessible_output2. Se gestiona en el hardware de voz de forma asíncrona.
    """
    if _speaker:
        _speaker.output(text, interrupt)
    else:
        print(f"VOZ (fallback): {text}")
