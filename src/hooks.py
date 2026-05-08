import ctypes
from ctypes import wintypes
import win32con
import win32api
import threading

# Estructuras para el Hook de Windows
class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]

LRESULT = ctypes.c_longlong
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, ctypes.POINTER(KBDLLHOOKSTRUCT))

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Modificadores
MOD_SHIFT = 1
MOD_CTRL = 2
MOD_ALT = 4

class WindowsHook:
    def __init__(self, callback):
        self.callback = callback
        self._hook = None
        self._running = False
        self._thread = None
        self._callback_proc = HOOKPROC(self._hook_callback)
        
    def start(self):
        """
        Inicia el hook en un hilo separado.
        """
        if self._running:
            return
            
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        
    def _run(self):
        self._hook = user32.SetWindowsHookExW(13, self._callback_proc, kernel32.GetModuleHandleW(None), 0)
        if not self._hook:
            self._hook = user32.SetWindowsHookExW(13, self._callback_proc, None, 0)
            
        if not self._hook:
            print("[Hook] Error al instalar el hook.")
            self._running = False
            return
            
        print("[Hook] Hook de teclado instalado.")
        msg = wintypes.MSG()
        while self._running:
            while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
                if msg.message == win32con.WM_QUIT:
                    self._running = False
                    break
            threading.Event().wait(0.01)
            
        user32.UnhookWindowsHookEx(self._hook)
        print("[Hook] Hook de teclado desinstalado.")
        
    def stop(self):
        self._running = False
        if self._hook:
            user32.PostQuitMessage(0)
            
    def _get_current_mask(self):
        mask = 0
        if (win32api.GetKeyState(win32con.VK_SHIFT) & 0x8000): mask |= MOD_SHIFT
        if (win32api.GetKeyState(win32con.VK_CONTROL) & 0x8000): mask |= MOD_CTRL
        if (win32api.GetKeyState(win32con.VK_MENU) & 0x8000): mask |= MOD_ALT
        return mask
        
    def _hook_callback(self, nCode, wParam, lParam):
        if nCode >= 0 and wParam == win32con.WM_KEYDOWN:
            vk = lParam.contents.vkCode
            mask = self._get_current_mask()
            
            # Llamar al callback del usuario
            if self.callback(vk, mask):
                return 1 # Bloquear la tecla si el callback devuelve True
                
        return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)
