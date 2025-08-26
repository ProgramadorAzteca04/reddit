# app/services/reddit/interaction_service.py
import time
import pyautogui
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup
from typing import List
from .desktop_service import PathManager, HumanInteractionUtils

# Alinear la excepción
try:
    from pyscreeze import ImageNotFoundException
except ImportError:
    ImageNotFoundException = pyautogui.ImageNotFoundException

def analizar_post_html(post_html: BeautifulSoup):
    """Extrae la información relevante de un único post de Reddit a partir de su HTML."""
    titulo_tag = post_html.find('a', {'slot': 'title'})
    titulo = titulo_tag.text.strip() if titulo_tag else "No encontrado"
    subreddit_tag = post_html.find('a', {'data-testid': 'subreddit-name'})
    subreddit = subreddit_tag.text.strip() if subreddit_tag else "No encontrado"
    autor = post_html.get('author', 'No encontrado')
    score_tag = post_html.select_one('[slot="vote-arrows"] faceplate-number')
    score = score_tag['number'] if score_tag and score_tag.has_attr('number') else "0"
    try:
        score_value = int(score)
    except (ValueError, TypeError):
        score_value = 0
    comentarios_tag = post_html.select_one('a[data-post-click-location="comments-button"] faceplate-number')
    num_comentarios = comentarios_tag.get('number', '0') if comentarios_tag else '0'
    return {"subreddit": subreddit, "autor": autor, "titulo": titulo, "score": score_value, "comentarios": int(num_comentarios)}

class RedditInteractionService:
    """Servicio para interactuar con Reddit después del login."""
    def __init__(self, driver: webdriver.Chrome):
        self.driver = driver

    def _like_post_with_pyautogui(self) -> bool:
        """Busca y hace clic en la flecha de upvote usando PyAutoGUI como fallback."""
        print("👍 Intentando hacer 'upvote' con PyAutoGUI...")
        try:
            upvote_image_path = os.path.join(PathManager.get_img_folder(), "post_upvote_arrow.png")
            if not os.path.exists(upvote_image_path):
                print(f"   -> ❌ No se encontró el archivo de imagen: {upvote_image_path}")
                return False
            pos = pyautogui.locateCenterOnScreen(upvote_image_path, confidence=0.8)
            if pos:
                print("   -> ✅ Imagen de upvote encontrada.")
                HumanInteractionUtils.move_mouse_humanly(pos.x, pos.y)
                pyautogui.click()
                time.sleep(1)
                return True
            else:
                print("   -> ❌ No se encontró la imagen de upvote en la pantalla.")
                return False
        except (ImageNotFoundException, Exception) as e:
            print(f"   -> ⚠️ Error en PyAutoGUI durante el upvote: {e}")
            return False

    def prepare_page(self):
        """Refresca la página y la prepara para la interacción."""
        print("⏳ Esperando 10 segundos después del login...")
        time.sleep(10)
        print("🔄 Refrescando la página para asegurar carga completa...")
        self.driver.refresh()
        time.sleep(5)
        print("🔐 Enviando tecla 'Escape' para cerrar posibles pop-ups...")
        try:
            self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(1)
        except Exception as e:
            print(f"⚠️ No se pudo enviar la tecla Escape. Error: {e}")

    def scroll_page(self, direction: str = "down"):
        """Realiza scroll en la página usando JavaScript."""
        scroll_amount = 800 if direction == "down" else -800
        print(f"📜 Haciendo scroll (Selenium) {'hacia abajo' if direction == 'down' else 'hacia arriba'}...")
        self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")

    def like_random_post(self):
        """Intenta dar upvote a un post usando el método de PyAutoGUI."""
        if self._like_post_with_pyautogui():
            print("  (✅ ¡ÉXITO! Se dio 'upvote' con PyAutoGUI.)\n")
        else:
            print("  (❌ Falló el intento de 'upvote' con PyAutoGUI.)\n")
    
    def analizar_publicaciones_visibles(self) -> List[dict]:
        """Analiza todos los posts visibles en la página actual."""
        print("\n🔎 Analizando publicaciones en la vista actual...")
        posts = []
        try:
            soup = BeautifulSoup(self.driver.page_source, 'lxml')
            posts_html = soup.find_all('shreddit-post')
            for post_html in posts_html:
                post_data = analizar_post_html(post_html)
                post_data['id'] = post_html.get('id', 'No encontrado')
                posts.append(post_data)
            print(f"✅ Se analizaron {len(posts)} publicaciones.")
        except Exception as e:
            print(f"🚨 Error analizando publicaciones: {e}")
        return posts
        
    def logout(self):
        """Realiza el proceso de cierre de sesión."""
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