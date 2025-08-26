# app/services/reddit/desktop_service.py
import pyautogui
import time
import random
import math
import os
import pyperclip
import secrets
import string
import pygetwindow as gw
from typing import List, Optional

# Alinear la excepción con la que realmente lanza PyScreeze
try:
    from pyscreeze import ImageNotFoundException # type: ignore
except ImportError:
    ImageNotFoundException = pyautogui.ImageNotFoundException # type: ignore

class PathManager:
    """Gestiona las rutas de los directorios para evitar lógica de rutas repetida."""
    _img_folder = None

    @staticmethod
    def get_img_folder() -> str:
        """Encuentra y cachea la ruta a la carpeta 'img'."""
        if PathManager._img_folder:
            return PathManager._img_folder
        try:
            # Navegar tres niveles arriba desde el archivo actual para llegar a la raíz del proyecto
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.normpath(os.path.join(script_dir, '..', '..', '..'))
            img_folder = os.path.join(project_root, 'img')
        except NameError:
            # Fallback para entornos donde __file__ no está definido
            img_folder = "img"
        
        if os.path.isdir(img_folder):
            PathManager._img_folder = img_folder
            print(f"✅ Usando carpeta de imágenes: {os.path.abspath(img_folder)}")
            return img_folder

        # Fallback a una carpeta local si la ruta construida no funciona
        local_img_folder = "img"
        if os.path.isdir(local_img_folder):
            PathManager._img_folder = local_img_folder
            print(f"✅ Usando carpeta de imágenes local: {os.path.abspath(local_img_folder)}")
            return local_img_folder

        raise FileNotFoundError("La carpeta 'img' no se encuentra en la raíz del proyecto.")


class HumanInteractionUtils:
    """Centraliza los métodos para simular interacciones humanas."""
    @staticmethod
    def move_mouse_humanly(x_dest: int, y_dest: int) -> None:
        """Mueve el ratón a un punto de destino usando una curva de Bézier."""
        try:
            x_ini, y_ini = pyautogui.position()
            dist = math.hypot(x_dest - x_ini, y_dest - y_ini)
            duration = max(0.3, min(1.5, dist / 1000))  # Duración basada en la distancia
            offset = random.randint(-100, 100)
            ctrl_x = (x_ini + x_dest) / 2 + offset
            ctrl_y = (y_ini + y_dest) / 2 - offset
            steps = max(10, int(dist / 25))
            for i in range(steps + 1):
                t = i / steps
                x = (1 - t) ** 2 * x_ini + 2 * (1 - t) * t * ctrl_x + t ** 2 * x_dest
                y = (1 - t) ** 2 * y_ini + 2 * (1 - t) * t * ctrl_y + t ** 2 * y_dest
                pyautogui.moveTo(x, y, duration=(duration / steps))
        except Exception as e:
            print(f"Error en move_mouse_humanly: {e}")

    @staticmethod
    def type_text_humanly(text: str) -> None:
        """Escribe texto simulando la escritura de un humano, con manejo especial para '@'."""
        print(f"⌨️ Escribiendo: '{text}'")
        for char in text:
            if char == '@':
                pyautogui.keyDown('ctrl')
                pyautogui.keyDown('alt')
                pyautogui.press('q')
                pyautogui.keyUp('alt')
                pyautogui.keyUp('ctrl')
            elif char.isupper() or char in '~!#$%^&*()_+{}|:"<>?':
                pyautogui.keyDown('shift')
                pyautogui.press(char.lower())
                pyautogui.keyUp('shift')
            else:
                pyautogui.press(char)
            time.sleep(random.uniform(0.05, 0.2))

    @staticmethod
    def generate_password(length: int = 12) -> str:
        """Genera una contraseña segura y aleatoria."""
        characters = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
        password = ''.join(secrets.choice(characters) for _ in range(length))
        print(f"🔒 Contraseña generada: {'*' * length}")
        return password


class DesktopUtils:
    """Gestiona interacciones con el escritorio, como el manejo de ventanas."""
    @staticmethod
    def get_and_focus_window(title: str, attempts: int = 5, delay: int = 2) -> Optional[gw.Win32Window]:
        """Busca una ventana por su título, la maximiza y la pone en foco."""
        print(f"🔍 Buscando ventana con el título '{title}'…")
        for attempt in range(attempts):
            try:
                windows = gw.getWindowsWithTitle(title)
                if windows:
                    window = windows[0]
                    if window.isMinimized:
                        window.restore()
                        time.sleep(0.5)
                    window.maximize()
                    window.activate()
                    time.sleep(1)
                    if not window.isMinimized:
                        print("✅ Ventana encontrada y enfocada.")
                        return window
            except Exception as e:
                print(f"⚠️ Intento {attempt + 1} fallido: {e}")
            if attempt < attempts - 1:
                print(f"Ventana no encontrada. Reintentando en {delay} segundos...")
                time.sleep(delay)
        print(f"❌ No se pudo encontrar la ventana '{title}' después de {attempts} intentos.")
        return None

class PyAutoGuiService:
    """Servicio con funcionalidades comunes de PyAutoGUI."""
    def find_and_click_humanly(self, images: List[str], confidence: float = 0.85, attempts: int = 1, wait_time: int = 0, scroll_on_fail: bool = False) -> bool:
        """Busca un elemento usando una lista de imágenes y hace clic de forma humana."""
        img_folder = PathManager.get_img_folder()
        image_paths = [os.path.join(img_folder, img) for img in images]

        for attempt in range(attempts):
            for image_path in image_paths:
                try:
                    pos = pyautogui.locateCenterOnScreen(image_path, confidence=confidence)
                    if pos:
                        print(f"✅ Elemento encontrado con {os.path.basename(image_path)}.")
                        HumanInteractionUtils.move_mouse_humanly(pos.x, pos.y)
                        pyautogui.click()
                        time.sleep(1)
                        return True
                except ImageNotFoundException:
                    continue 
                except Exception as e:
                    print(f"⚠️ Error inesperado en find_and_click_humanly: {e}")
            
            print(f"❌ Intento {attempt + 1}/{attempts}: No se encontró el elemento con: {images}")
            if wait_time > 0 and attempt < attempts - 1:
                print(f"⏳ Esperando {wait_time}s...")
                time.sleep(wait_time)
            if scroll_on_fail and attempt < attempts - 1:
                print("📜 Elemento no encontrado, haciendo scroll...")
                pyautogui.scroll(-300)
                time.sleep(1)
        return False