# app/services/reddit/auth.py

from typing import List, Optional, Tuple
from pydantic import BaseModel, Field
from fastapi import HTTPException
import pygetwindow as gw
import subprocess
import pyautogui
import pyperclip
import secrets
import string
import random
import math
import time
import os

# Importaciones para Web Scraping y Automatización
from webdriver_manager.chrome import ChromeDriverManager
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup

# Alinear la excepción con la que realmente lanza PyScreeze
try:
    from pyscreeze import ImageNotFoundException # type: ignore
except Exception:
    try:
        ImageNotFoundException = pyautogui.ImageNotFoundException # type: ignore[attr-defined]
    except Exception:
        class ImageNotFoundException(Exception):
            pass

# ==============================================================================
# --- Modelos de Datos (Pydantic) ---
# ==============================================================================
class AutomationRequest(BaseModel):
    url: str = Field(..., example="https://www.reddit.com/register/")
    email: str = Field(..., example="tu.correo@ejemplo.com")

# --- MODELO MODIFICADO: Petición simplificada al máximo ---
class LoginRequest(BaseModel):
    url: str = Field(..., example="https://www.reddit.com/login")
    username: str
    password: str
    window_title: str = Field("Reddit", description="Título de la ventana para PyAutoGUI.")
    interaction_minutes: int = Field(5, description="Duración aproximada de la interacción en minutos.")


class ElementLocator(BaseModel):
    images: List[str]
    confidence: float = 0.85
    wait_time: int = 0
    attempts: int = 1

# ==============================================================================
# --- Lógica de Análisis de Posts (con BeautifulSoup) ---
# ==============================================================================
def analizar_post(post_html):
    """Extrae la información relevante de una única publicación de Reddit."""
    titulo_tag = post_html.find('a', {'slot': 'title'})
    titulo = titulo_tag.text.strip() if titulo_tag else "No encontrado"
    subreddit_tag = post_html.find('a', {'data-testid': 'subreddit-name'})
    subreddit = subreddit_tag.text.strip() if subreddit_tag else "No encontrado"
    autor = post_html.get('author', 'No encontrado')

    score = "0"
    vote_bar = post_html.select_one('[slot="vote-arrows"]')
    if vote_bar:
        score_tag = vote_bar.find('faceplate-number')
        if score_tag and score_tag.has_attr('number'):
            score = score_tag['number']

    score_value = 0
    try:
        score_value = int(score)
    except (ValueError, TypeError):
        score_value = 0 

    comentarios_tag = post_html.find('a', {'data-post-click-location': 'comments-button'})
    num_comentarios = "0"
    if comentarios_tag and comentarios_tag.find('faceplate-number'):
        num_comentarios = comentarios_tag.find('faceplate-number').get('number', '0')
    
    return {"subreddit": subreddit, "autor": autor, "titulo": titulo, "score": score_value, "comentarios": int(num_comentarios)}

# ==============================================================================
# --- Servicio de Automatización con PyAutoGUI (Para Login) ---
# ==============================================================================
class AutomationService:
    def __init__(self, chrome_path: str = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"):
        self.chrome_path = chrome_path
        self.user_data_dir = os.path.join(os.getcwd(), "chrome_dev_session")
        self.debugging_port = "9222"

    def open_chrome_incognito(self, url: str) -> None:
        command = [self.chrome_path, f"--remote-debugging-port={self.debugging_port}", f"--user-data-dir={self.user_data_dir}", url]
        try:
            subprocess.Popen(command)
            print(f"🌐 Chrome abierto en modo depuración en el puerto {self.debugging_port}")
        except FileNotFoundError:
            print(f"❌ No se encontró Chrome en la ruta: {self.chrome_path}")
            raise HTTPException(status_code=500, detail="No se encontró el ejecutable de Chrome.")

    def find_and_click_humanly(self, locator: ElementLocator) -> bool:
        for attempt in range(locator.attempts):
            for image in locator.images:
                try:
                    pos = pyautogui.locateCenterOnScreen(image, confidence=locator.confidence)
                    if pos:
                        print(f"✅ Elemento encontrado con {os.path.basename(image)}.")
                        self._move_mouse_humanly(pos.x, pos.y)
                        pyautogui.click()
                        time.sleep(1)
                        return True
                except ImageNotFoundException:
                    continue
                except Exception as e:
                    print(f"⚠️ Error inesperado en find_and_click_humanly: {e}")
                    continue
            if locator.wait_time > 0:
                print(f"⏳ Retraso de {locator.wait_time}s antes del siguiente intento.")
                time.sleep(locator.wait_time)
        print(f"❌ No se encontró el elemento con ninguna de las imágenes: {locator.images}")
        return False

    def _move_mouse_humanly(self, x_dest: int, y_dest: int) -> None:
        try:
            x_ini, y_ini = pyautogui.position()
            dist = math.hypot(x_dest - x_ini, y_dest - y_ini)
            duration = max(0.3, min(1.5, dist / 1000))
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
            print(f"Error en _move_mouse_humanly: {e}")

    def type_text_humanly(self, text: str) -> None:
        print("⌨️ Escribiendo texto de forma humana…")
        for char in text:
            if char.isupper() or char in '~!@#$%^&*()_+{}|:"<>?':
                pyautogui.keyDown('shift')
                pyautogui.press(char.lower())
                pyautogui.keyUp('shift')
            else:
                pyautogui.press(char)
            time.sleep(random.uniform(0.05, 0.2))

    def get_and_focus_window(self, title: str, attempts: int = 5, delay: int = 2) -> Optional[gw.Win32Window]:
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
                print(f"⚠️ Intento {attempt + 1} fallido con un error inesperado: {e}")
            if attempt < attempts - 1:
                print(f"Ventana no encontrada o no lista. Reintentando en {delay} segundos...")
                time.sleep(delay)
        print(f"❌ No se pudo encontrar y enfocar la ventana del navegador después de {attempts} intentos.")
        return None

# ==============================================================================
# --- Servicio de Navegación con Selenium (Para Interacción Post-Login) ---
# ==============================================================================
class SeleniumNavigationService:
    def __init__(self, port: str):
        self.port = port
        self.driver = None
    
    def _move_mouse_humanly(self, x_dest: int, y_dest: int) -> None:
        try:
            x_ini, y_ini = pyautogui.position()
            dist = math.hypot(x_dest - x_ini, y_dest - y_ini)
            duration = max(0.3, min(1.5, dist / 1000))
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
            print(f"Error en _move_mouse_humanly: {e}")

    def _click_upvote_with_pyautogui(self) -> bool:
        """
        Busca y hace clic en la primera flecha de upvote visible en la pantalla
        usando PyAutoGUI.
        """
        print("   -> Buscando 'post_upvote_arrow.png' en la pantalla...")
        try:
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.normpath(os.path.join(script_dir, '..', '..', '..'))
                img_folder = os.path.join(project_root, 'img')
                if not os.path.isdir(img_folder):
                    img_folder = "img"
            except NameError:
                img_folder = "img"
            
            upvote_image_path = os.path.join(img_folder, "post_upvote_arrow.png")
            if not os.path.exists(upvote_image_path):
                print(f"   -> ❌ No se encontró el archivo de imagen: {upvote_image_path}")
                return False

            pos = pyautogui.locateCenterOnScreen(upvote_image_path, confidence=0.8)
            if pos:
                print("   -> ✅ Imagen de upvote encontrada.")
                self._move_mouse_humanly(pos.x, pos.y)
                pyautogui.click()
                time.sleep(1)
                return True
            else:
                print("   -> ❌ No se encontró la imagen de upvote en la pantalla.")
                return False
        except ImageNotFoundException:
            print("   -> ❌ No se encontró la imagen de upvote en la pantalla (ImageNotFoundException).")
            return False
        except Exception as e:
            print(f"   -> ⚠️ Error inesperado en PyAutoGUI: {e}")
            return False

    def connect_to_browser(self):
        print("🔗 Conectando Selenium al navegador existente...")
        chrome_options = Options()
        chrome_options.add_experimental_option("debuggerAddress", f"127.0.0.1:{self.port}")
        service = ChromeService(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        print("✅ Selenium conectado exitosamente.")

    def refresh_page_and_prepare(self):
        if not self.driver: return
        print("⏳ Esperando 10 segundos después del login...")
        time.sleep(10)
        print("🔄 Refrescando la página para asegurar que todo el contenido cargue...")
        self.driver.refresh()
        time.sleep(5)
        print("🔐 Enviando tecla 'Escape' para cerrar posibles pop-ups post-recarga...")
        try:
            body = self.driver.find_element(By.TAG_NAME, 'body')
            body.send_keys(Keys.ESCAPE)
            time.sleep(1)
        except Exception as e:
            print(f"⚠️ No se pudo enviar la tecla Escape. Puede que no fuera necesario. Error: {e}")

    def scroll_page(self, direction: str = "down"):
        if not self.driver: return
        print(f"📜 Haciendo scroll (Selenium) hacia {'abajo' if direction == 'down' else 'arriba'}...")
        self.driver.execute_script(f"window.scrollBy(0, {'800' if direction == 'down' else '-800'});")

    def click_first_upvote(self):
        if not self.driver: return
        print("👍 Intentando hacer 'upvote' con PyAutoGUI...")
        if self._click_upvote_with_pyautogui():
            print("  (✅ ¡ÉXITO! Se dio 'upvote' con PyAutoGUI.)")
        else:
            print("  (❌ Falló el intento de 'upvote' con PyAutoGUI.)")

    def analizar_publicaciones_visibles(self):
        if not self.driver: return []
        print("\n🔎 Analizando TODAS las publicaciones en la vista actual (en bloque)...")
        page_source = self.driver.page_source
        soup = BeautifulSoup(page_source, 'lxml')
        posts_html = soup.find_all('shreddit-post')
        lista_de_posts = []

        for post in posts_html:
            post_data = analizar_post(post)
            post_data['id'] = post.get('id', 'No encontrado') 
            lista_de_posts.append(post_data)

        print(f"✅ Se analizaron {len(lista_de_posts)} publicaciones.")
        for i, post_data in enumerate(lista_de_posts):
            print(f"   - Post #{i+1} | ID: {post_data['id']} | {post_data['subreddit']} | u/{post_data['autor']} | Score: {post_data['score']}")
        print("")
        return lista_de_posts
    
    def analizar_posts_uno_por_uno(self):
        if not self.driver: return []
        print("\n🔎 Analizando publicaciones UNA POR UNA...")
        
        lista_completa = []
        try:
            wait = WebDriverWait(self.driver, 15)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "shreddit-post")))
            posts_elements: List[WebElement] = self.driver.find_elements(By.TAG_NAME, "shreddit-post")
            print(f"✅ Se encontraron {len(posts_elements)} publicaciones en la vista actual. Procesando...")
            for i, post_element in enumerate(posts_elements):
                try:
                    post_id = post_element.get_attribute('id') or "No encontrado"
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", post_element)
                    time.sleep(0.5)
                    post_html_str = post_element.get_attribute('outerHTML')
                    soup = BeautifulSoup(post_html_str, 'lxml')
                    post_tag = soup.find('shreddit-post')
                    
                    if post_tag:
                        post_data = analizar_post(post_tag)
                        post_data['id'] = post_id
                        lista_completa.append(post_data)
                        print(f"   [Post #{i+1}/{len(posts_elements)}] -> ID: {post_id} | {post_data['subreddit']} | Score: {post_data['score']} | Título: {post_data['titulo'][:40]}...")
                    else:
                        print(f"   [Post #{i+1}/{len(posts_elements)}] -> ID: {post_id} ⚠️ No se pudo parsear el HTML de este post.")
                    time.sleep(random.uniform(1.0, 2.5))
                except Exception as e:
                    print(f"   [Post #{i+1}/{len(posts_elements)}] -> 🚨 Error analizando este post: {e}")
                    continue
        except TimeoutException:
            print("🚨 Tiempo de espera agotado. No se encontró ningún post (<shreddit-post>) para analizar.")
        except Exception as e:
            print(f"🚨 Error Crítico durante el análisis uno por uno: {e}")

        print(f"\n✅ Análisis individual completado. Total de posts procesados: {len(lista_completa)}.\n")
        return lista_completa

    def like_random_post(self):
        if not self.driver: return
        print("\n💞 Intentando dar 'upvote' a una publicación con PyAutoGUI (acción 'like_random_post')...")
        if self._click_upvote_with_pyautogui():
            print("  (✅ ¡ÉXITO! Se dio 'upvote' con PyAutoGUI.)\n")
        else:
            print("  (❌ Falló el intento de 'upvote' con PyAutoGUI.)\n")

    def logout(self):
        if not self.driver: return
        print("\n👋 Iniciando proceso de cierre de sesión...")
        try:
            print("   -> Abriendo el menú de usuario...")
            self.driver.execute_script("document.getElementById('expand-user-drawer-button').click();")
            time.sleep(2)
            print("   -> Haciendo clic en 'Cerrar Sesión'...")
            self.driver.execute_script("document.getElementById('logout-list-item').click();")
            time.sleep(3)
            print("✅ Cierre de sesión completado exitosamente.")
        except Exception as e:
            print(f"🚨 Error durante el cierre de sesión: {e}")
            print("   -> No se pudo cerrar la sesión. El navegador permanecerá en la última página.")

    def close_connection(self):
        if self.driver:
            self.driver.quit()
            print("🚪 Conexión de Selenium cerrada (navegador finalizado).")

# ==============================================================================
# --- Orquestadores de Flujo ---
# ==============================================================================
def run_registration_flow(email: str, url: str):
    pass

# --- FUNCIÓN MODIFICADA: Ahora calcula las interacciones automáticamente ---
def run_selenium_navigation(interaction_minutes: int):
    """
    🚀 VERSIÓN OPTIMIZADA 🚀
    Navega de forma dinámica sin generar una lista de acciones fija.
    Usa el análisis en bloque para mayor velocidad.
    """
    service = None
    start_time = time.time()
    
    # Acciones con "peso" para controlar la probabilidad.
    action_pool = ["scroll_down"] * 5 + ["like_random_post"] * 2 + ["analizar_posts_visibles"] * 1
    
    print("\n" + "="*50)
    print("🤖 INICIANDO NAVEGACIÓN DINÁMICA 🤖")
    print(f"OBJETIVO: Navegar durante {interaction_minutes} minutos.")
    print("ACCIONES: Se elegirán aleatoriamente sobre la marcha.")
    print("="*50 + "\n")

    try:
        service = SeleniumNavigationService(port="9222")
        service.connect_to_browser()
        service.refresh_page_and_prepare()
        
        print("\n--- 🚀 INICIANDO EJECUCIÓN ---")

        # Bucle principal que se ejecuta hasta que se cumple el tiempo
        while (time.time() - start_time) / 60 < interaction_minutes:
            
            # 1. Elige una acción aleatoria del pool
            action = random.choice(action_pool)
            print(f"\nPróxima acción: {action}")

            # 2. Ejecuta la acción
            if action == "scroll_down":
                service.scroll_page(direction="down")
            elif action == "like_random_post":
                service.like_random_post() # Esta función ya llama a la nueva _click_upvote_with_pyautogui
            
            # --- CAMBIO IMPORTANTE ---
            # Usamos el análisis rápido en lugar del lento uno por uno
            elif action == "analizar_posts_visibles":
                service.analizar_publicaciones_visibles() 
            
            # 3. Espera un tiempo aleatorio antes de la siguiente acción
            wait_time = random.randint(5, 12)
            print(f"⏳ Esperando por {wait_time} segundos...")
            time.sleep(wait_time)

        print(f"✅ Tiempo límite de {interaction_minutes} minutos alcanzado. Finalizando.")

    except Exception as e:
        import traceback
        print(f"\n🚨 ERROR FATAL en el flujo de Selenium: {e}")
        traceback.print_exc()
        
    finally:
        if service and service.driver:
            service.logout()
        print("\nℹ️  El script ha finalizado. Se ha ejecutado el intento de cierre de sesión.")

# --- FUNCIÓN MODIFICADA: Adaptada a la nueva petición simplificada ---
def run_login_flow(
    username: str, 
    password: str, 
    url: str, 
    window_title: str,
    interaction_minutes: int
):
    service = AutomationService()
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.normpath(os.path.join(script_dir, '..', '..', '..'))
        img_folder = os.path.join(project_root, 'img')
        if not os.path.isdir(img_folder):
             img_folder = "img"
             if not os.path.isdir(img_folder):
                    raise FileNotFoundError("La carpeta 'img' no se encuentra en la raíz del proyecto ni en la ruta actual.")
    except NameError:
        img_folder = "img"
        if not os.path.isdir(img_folder):
            raise FileNotFoundError("Asegúrate de que la carpeta 'img' está en el directorio actual.")

    print(f"✅ Usando carpeta de imágenes: {os.path.abspath(img_folder)}")
    try:
        service.open_chrome_incognito(url)
        time.sleep(5)
        if not service.get_and_focus_window(window_title):
            raise RuntimeError("No se pudo encontrar la ventana del navegador.")
        print("\n--- Iniciando Proceso de Login con PyAutoGUI---")
        user_locator = ElementLocator(images=[os.path.join(img_folder, "user.png"), os.path.join(img_folder, "username.png")], confidence=0.7)
        if not service.find_and_click_humanly(user_locator): raise RuntimeError("No se encontró el campo de usuario.")
        service.type_text_humanly(username)
        password_locator = ElementLocator(images=[os.path.join(img_folder, "password_dark.png"), os.path.join(img_folder, "password_light.png")])
        if not service.find_and_click_humanly(password_locator): raise RuntimeError("No se encontró el campo de contraseña.")
        service.type_text_humanly(password)
        login_locator = ElementLocator(images=[os.path.join(img_folder, "start_dark.png"), os.path.join(img_folder, "start_light.png")])
        if not service.find_and_click_humanly(login_locator): raise RuntimeError("No se encontró el botón de login.")
        
        print("✅ Login con PyAutoGUI completado.")
        
        run_selenium_navigation(interaction_minutes)

    except Exception as e:
        import traceback
        print(f"\n🚨 ERROR FATAL en el flujo de PyAutoGUI: {e}")
        traceback.print_exc()
        print("\nProceso abortado.")