# app/services/reddit/interaction_service.py
import time
import pyautogui
import os
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from .desktop_service import PyAutoGuiService
from bs4 import BeautifulSoup
from typing import List, Set
from sqlalchemy.sql.expression import func
from sqlalchemy import not_
from .feed_service import FeedService, _user_prefixed
from app.services.openai.content_generator_service import select_best_post_title
from .desktop_service import PathManager, HumanInteractionUtils
from app.db.database import get_db_secondary
from app.models.reddit_models import Post, Credential

try:
    from pyscreeze import ImageNotFoundException
except ImportError:
    ImageNotFoundException = pyautogui.ImageNotFoundException

def analizar_post_html(post_html: BeautifulSoup):
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
    # --- INICIALIZADOR CORREGIDO ---
    def __init__(self, driver: webdriver.Chrome, username: str):
        self.driver = driver
        self.username = username
        self.credential_id = None

    def repost_best_post_from_feed(self):
        """
        Analiza el feed actual, usa la IA para seleccionar el mejor post y lo republica.
        """
        print("\n🤖 --- Iniciando Interacción: Republicar Mejor Post del Feed --- 🤖")
        try:
            # 1. Navegar al feed principal y analizarlo
            print("   -> Navegando al feed principal...")
            self.driver.get("https://www.reddit.com/")
            time.sleep(10)

            print("   -> Analizando el feed con IA...")
            feed_service = FeedService(self.driver.page_source)
            best_post = feed_service.get_best_post_by_ai()

            if not best_post:
                print("   -> No se pudo seleccionar una publicación. Abortando interacción.")
                return

            print("\n   🎯 MEJOR PUBLICACIÓN SELECCIONADA POR IA:")
            print(f"      -> Título: {best_post['title']}")
            print(f"      -> Enlace: {best_post['link']}")
            
            # 2. Navegar al post y realizar la secuencia de clics
            print(f"\n   -> 🚀 Navegando a la publicación seleccionada...")
            self.driver.get(best_post['link'])
            time.sleep(10)

            pyautogui_service = PyAutoGuiService()
            print("   -> 🖱️ Buscando 'compartir.png'...")
            if pyautogui_service.find_and_click_humanly(['compartir.png']):
                print("      -> ✅ Clic en Compartir. Esperando menú...")
                time.sleep(2)
                
                print("      -> 🖱️ Buscando 'republicar.png'...")
                if pyautogui_service.find_and_click_humanly(['republicar.png']):
                    print("         -> ✅ Clic en Republicar. Esperando vista de publicación...")
                    time.sleep(10)

                    # 3. Seleccionar comunidad y publicar
                    print("         -> 🖱️ Buscando 'select_community.png'...")
                    img_path = os.path.join(PathManager.get_img_folder(), "select_community.png")
                    community_button_pos = pyautogui.locateCenterOnScreen(img_path, confidence=0.8)

                    if community_button_pos:
                        pyautogui.click(community_button_pos)
                        print("            -> ✅ Clic en Seleccionar Comunidad. Escribiendo perfil...")
                        time.sleep(1.5)
                        target_profile = _user_prefixed(self.username) # Usamos el username del servicio
                        pyautogui.write(target_profile, interval=0.1)
                        time.sleep(2.5)

                        option_x = community_button_pos.x
                        option_y = community_button_pos.y + 60
                        
                        print(f"            -> 🖱️ Haciendo clic en la opción del perfil en ({option_x}, {option_y}).")
                        pyautogui.moveTo(option_x, option_y, duration=0.5)
                        pyautogui.click()
                        
                        time.sleep(2)
                        print("            -> 🖱️ Buscando 'publicar.png'...")
                        if pyautogui_service.find_and_click_humanly(["publicar.png"], confidence=0.8):
                            print("               -> ✅ ¡Post republicado exitosamente!")
                        else:
                            print("               -> ⚠️ No se encontró el botón final para publicar.")
                    else:
                        print("            -> ⚠️ No se encontró el botón para seleccionar comunidad.")
                else:
                    print("         -> ⚠️ No se encontró el botón de republicar.")
            else:
                print("      -> ⚠️ No se encontró el botón de compartir.")
            
            print("\n   -> ✅ Interacción completada. Volviendo al feed principal...")
            self.driver.get("https://www.reddit.com/")
            time.sleep(5)

        except Exception as e:
            print(f"   -> 🚨 Error durante la interacción de republicar desde el feed: {e}")
            self.driver.get("https://www.reddit.com/") # Volver a la página de inicio en caso de error

    def _get_credential_id(self, db) -> int | None:
        if self.credential_id:
            return self.credential_id
        
        credential = db.query(Credential).filter(Credential.username == self.username).first()
        if credential:
            self.credential_id = credential.id
            return self.credential_id
        return None

    def _like_post_with_pyautogui(self) -> bool:
        print("👍 Intentando hacer 'upvote' con PyAutoGUI...")
        try:
            upvote_image_path = os.path.join(PathManager.get_img_folder(), "post_upvote_arrow.png")
            if not os.path.exists(upvote_image_path): return False
            pos = pyautogui.locateCenterOnScreen(upvote_image_path, confidence=0.8)
            if pos:
                HumanInteractionUtils.move_mouse_humanly(pos.x, pos.y)
                pyautogui.click()
                time.sleep(1)
                return True
            return False
        except (ImageNotFoundException, Exception):
            return False

    def upvote_from_database(self, interacted_post_ids_session: Set[str]):
        print(f"\n--- 🎲 Iniciando interacción: Upvote desde BD para '{self.username}' ---")
        db = next(get_db_secondary())
        try:
            credential_id = self._get_credential_id(db)
            if not credential_id:
                print(f"   -> ⚠️ No se encontró la credencial para el usuario '{self.username}'.")
                return

            random_post = db.query(Post).filter(
                not_(Post.interacted_by_credential_ids.contains([credential_id])),
                not_(Post.id.in_(list(interacted_post_ids_session)))
            ).order_by(func.random()).first()
            
            if not random_post or not random_post.post_url:
                print("   -> ✅ No hay posts nuevos disponibles para esta cuenta.")
                return

            print(f"   -> 🎯 Post seleccionado (ID: {random_post.id}). Navegando...")
            self.driver.get(random_post.post_url)
            time.sleep(random.randint(5, 8))

            if self._like_post_with_pyautogui():
                print(f"   -> ✅ Upvote exitoso para el post ID: {random_post.id}")
                random_post.interacted_by_credential_ids.append(credential_id)
                db.commit()
                print("   -> 💾 Base de datos actualizada.")
            else:
                print(f"   -> ❌ Falló el upvote para el post ID: {random_post.id}")

            interacted_post_ids_session.add(random_post.id)
            
            time.sleep(2)
            self.driver.get("https://www.reddit.com/")
            time.sleep(random.randint(3, 5))

        except Exception as e:
            print(f"   -> 🚨 Error durante la interacción de upvote desde BD: {e}")
            db.rollback()
        finally:
            db.close()
    
    def prepare_page(self):
        print("⏳ Esperando 10 segundos después del login...")
        time.sleep(10)
        self.driver.refresh()
        time.sleep(5)
        try:
            self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(1)
        except Exception: pass

    def scroll_page(self, direction: str = "down"):
        scroll_amount = 800 if direction == "down" else -800
        self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")

    def like_random_post(self):
        if self._like_post_with_pyautogui(): print("  (✅ ¡ÉXITO! Se dio 'upvote' con PyAutoGUI.)\n")
        else: print("  (❌ Falló el intento de 'upvote' con PyAutoGUI.)\n")
    
    def analizar_publicaciones_visibles(self) -> List[dict]:
        posts = []
        try:
            soup = BeautifulSoup(self.driver.page_source, 'lxml')
            posts_html = soup.find_all('shreddit-post')
            for post_html in posts_html:
                post_data = analizar_post_html(post_html)
                post_data['id'] = post_html.get('id', 'No encontrado')
                posts.append(post_data)
        except Exception: pass
        return posts
        
    def logout(self):
        print("\n👋 Iniciando proceso de cierre de sesión...")
        try:
            self.driver.execute_script("document.getElementById('expand-user-drawer-button').click();")
            time.sleep(2)
            self.driver.execute_script("document.getElementById('logout-list-item').click();")
            time.sleep(3)
            print("✅ Cierre de sesión completado exitosamente.")
            print("   -> Cerrando la ventana del navegador con Ctrl+W...")
            pyautogui.hotkey('ctrl', 'w')
            time.sleep(1) # Pequeña pausa para que la ventana se cierre
        except Exception as e:
            print(f"🚨 Error durante el cierre de sesión: {e}")

    def logout_and_set_dark_mode(self):
        """
        Activa el modo oscuro y luego realiza el cierre de sesión.
        Diseñado para ser usado al final del flujo de registro.
        """
        print("\n👋 Iniciando proceso de cierre de sesión y activación de modo oscuro...")
        try:
            # 1. Abrir el menú de usuario
            print("   -> Abriendo el menú de usuario...")
            self.driver.execute_script("document.getElementById('expand-user-drawer-button').click();")
            time.sleep(2)

            # 2. Activar el modo oscuro
            print("   -> Activando modo oscuro...")
            self.driver.execute_script("document.getElementById('darkmode-list-item').click();")
            time.sleep(2) # Espera para que el tema cambie

            # 3. Volver a abrir el menú (puede que se cierre al cambiar de tema)
            print("   -> Re-abriendo el menú de usuario...")
            self.driver.execute_script("document.getElementById('expand-user-drawer-button').click();")
            time.sleep(2)

            # 4. Hacer clic en 'Cerrar Sesión'
            print("   -> Haciendo clic en 'Cerrar Sesión'...")
            self.driver.execute_script("document.getElementById('logout-list-item').click();")
            time.sleep(3)
            
            print("✅ Modo oscuro activado y cierre de sesión completado.")

            print("   -> Cerrando la ventana del navegador con Ctrl+W...")
            pyautogui.hotkey('ctrl', 'w')
            time.sleep(1) # Pequeña pausa para que la ventana se cierre
        except Exception as e:
            print(f"🚨 Error durante el logout especial: {e}")
            # Si algo falla, intenta un logout normal como fallback
            self.logout()