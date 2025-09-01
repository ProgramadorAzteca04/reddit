# app/services/reddit/interaction_service.py
import time
import pyautogui
import os
import random
import pyperclip
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from .desktop_service import PyAutoGuiService
from bs4 import BeautifulSoup
from typing import List, Set, Optional, Dict
from sqlalchemy.sql.expression import func
from sqlalchemy import not_
from .feed_service import FeedService, _user_prefixed
from app.services.openai.content_generator_service import generate_comment_for_post
from .desktop_service import PathManager, HumanInteractionUtils
from app.db.database import get_db_secondary
from app.models.reddit_models import Post, Credential
from sqlalchemy.orm import Session

try:
    from pyscreeze import ImageNotFoundException
except ImportError:
    ImageNotFoundException = pyautogui.ImageNotFoundException

COMMENT_TRIGGER_JS = """
function deepQuerySelector(root, selector) {
    const el = root.querySelector(selector);
    if (el) { return el; }
    const children = root.querySelectorAll("*");
    for (const child of children) {
        if (child.shadowRoot) {
            const found = deepQuerySelector(child.shadowRoot, selector);
            if (found) { return found; }
        }
    }
    return null;
}
const triggerButton = deepQuerySelector(document, 'button[name="comments-action-button"]');
if (triggerButton) {
    console.log("✅ Botón de acción de comentario encontrado, haciendo clic...");
    triggerButton.click();
} else {
    console.log("❌ No se encontró el botón de acción de comentario.");
}
"""

COMMENT_FOCUS_JS = """
function deepQuerySelector(root, selector) {
    const el = root.querySelector(selector);
    if (el) return el;
    for (const child of root.querySelectorAll("*")) {
        if (child.shadowRoot) {
            const found = deepQuerySelector(child.shadowRoot, selector);
            if (found) return found;
        }
    }
    return null;
}
const editor = deepQuerySelector(document, 'div[contenteditable="true"]');
if (editor) {
    editor.focus();
}
"""

COMMENT_SUBMIT_JS = """
// Script corregido para usar un selector más específico para el botón de publicar.
function deepQuerySelector(root, selector) {
    const el = root.querySelector(selector);
    if (el) return el;
    for (const child of root.querySelectorAll("*")) {
        if (child.shadowRoot) {
            const found = deepQuerySelector(child.shadowRoot, selector);
            if (found) return found;
        }
    }
    return null;
}
const submitButton = deepQuerySelector(document, 'button[slot="submit-button"][type="submit"]');
if (submitButton) {
    console.log("✅ Botón 'Comentar' (submit) encontrado, haciendo clic...");
    submitButton.click();
} else {
    console.log("❌ No se encontró el botón 'Comentar' (submit).");
}
"""

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
    """
    Servicio refactorizado para interactuar con Reddit después del login.
    Los métodos largos han sido divididos en funciones privadas más pequeñas y reutilizables.
    """
    def __init__(self, driver: webdriver.Chrome, username: str):
        self.driver = driver
        self.username = username
        self.credential_id: Optional[int] = None
        self.pyautogui_service = PyAutoGuiService()

    def comment_on_best_post_from_feed(self):
        print("\n🤖 --- Iniciando Interacción: Comentar en el Mejor Post del Feed --- 🤖")
        try:
            best_post = self._select_best_post_from_feed()
            if not best_post:
                return

            comment_text = generate_comment_for_post(best_post['title'])
            
            if self._execute_comment_paste_sequence(best_post['link'], comment_text):
                print("   -> ✅ Interacción de comentario completada exitosamente.")
            else:
                print("   -> ⚠️  La interacción de comentario no pudo completarse.")

            print("   -> Volviendo al feed principal...")
            self.driver.get("https://www.reddit.com/")
            time.sleep(5)

        except Exception as e:
            print(f"   -> 🚨 Error durante la interacción de comentar desde el feed: {e}")
            self.driver.get("https://www.reddit.com/")

    def _execute_comment_paste_sequence(self, post_link: str, comment: str) -> bool:
        print(f"\n   -> 🚀 Navegando a la publicación para comentar...")
        self.driver.get(post_link)
        time.sleep(10)

        print("   -> 🖱️ Habilitando el campo de comentario con JS...")
        self.driver.execute_script(COMMENT_TRIGGER_JS)
        time.sleep(2) # Pausa para que el editor aparezca

        print("   -> 📋 Copiando comentario al portapapeles...")
        pyperclip.copy(comment)

        print("   -> ✍️ Enfocando editor de comentarios con JS...")
        self.driver.execute_script(COMMENT_FOCUS_JS)
        
        print(f"      -> ✅ Editor enfocado. Pegando comentario: '{comment}'")
        time.sleep(1)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(3)

        print("   -> 🖱️ Publicando comentario con Selenium/JS...")
        self.driver.execute_script(COMMENT_SUBMIT_JS)
            
        print("      -> ✅ ¡Comentario publicado exitosamente!")
        time.sleep(5)
        return True

    # --- Flujo Principal de Republicación ---
    def repost_best_post_from_feed(self):
        """
        Orquesta el flujo de análisis del feed y republicación del mejor post.
        """
        print("\n🤖 --- Iniciando Interacción: Republicar Mejor Post del Feed --- 🤖")
        try:
            best_post = self._select_best_post_from_feed()
            if not best_post:
                return # El método _select_best_post_from_feed ya imprime el error.

            self._execute_repost_pyautogui_sequence(best_post['link'])
            
            print("\n   -> ✅ Interacción completada. Volviendo al feed principal...")
            self.driver.get("https://www.reddit.com/")
            time.sleep(5)

        except Exception as e:
            print(f"   -> 🚨 Error durante la interacción de republicar desde el feed: {e}")
            self.driver.get("https://www.reddit.com/")

    def _select_best_post_from_feed(self) -> Optional[Dict[str, str]]:
        """
        Navega al feed, lo analiza con la IA y devuelve el mejor post.
        """
        print("   -> Navegando al feed principal...")
        self.driver.get("https://www.reddit.com/")
        time.sleep(10)

        print("   -> Analizando el feed con IA...")
        feed_service = FeedService(self.driver.page_source)
        best_post = feed_service.get_best_post_by_ai()

        if not best_post:
            print("   -> No se pudo seleccionar una publicación. Abortando interacción.")
            return None

        print("\n   🎯 MEJOR PUBLICACIÓN SELECCIONADA POR IA:")
        print(f"      -> Título: {best_post['title']}")
        print(f"      -> Enlace: {best_post['link']}")
        return best_post

    def _execute_repost_pyautogui_sequence(self, post_link: str) -> bool:
        """
        Ejecuta la secuencia de clics con PyAutoGUI para republicar un post.
        """
        print(f"\n   -> 🚀 Navegando a la publicación seleccionada...")
        self.driver.get(post_link)
        time.sleep(10)

        print("   -> 🖱️ Buscando 'compartir.png'...")
        if not self.pyautogui_service.find_and_click_humanly(['compartir.png']):
            print("      -> ⚠️ No se encontró el botón de compartir.")
            return False
        
        print("      -> ✅ Clic en Compartir. Esperando menú...")
        time.sleep(2)
        
        print("      -> 🖱️ Buscando 'republicar.png'...")
        if not self.pyautogui_service.find_and_click_humanly(['republicar.png']):
            print("         -> ⚠️ No se encontró el botón de republicar.")
            return False

        print("         -> ✅ Clic en Republicar. Esperando vista de publicación...")
        time.sleep(10)

        if not self._select_community_and_publish():
            return False
        
        return True

    def _select_community_and_publish(self) -> bool:
        """
        Busca 'select_community.png', escribe el nombre de usuario y publica.
        """
        print("         -> 🖱️ Buscando 'select_community.png'...")
        img_path = os.path.join(PathManager.get_img_folder(), "select_community.png")
        community_button_pos = pyautogui.locateCenterOnScreen(img_path, confidence=0.8)

        if not community_button_pos:
            print("            -> ⚠️ No se encontró el botón para seleccionar comunidad.")
            return False

        pyautogui.click(community_button_pos)
        print("            -> ✅ Clic en Seleccionar Comunidad. Escribiendo perfil...")
        time.sleep(1.5)
        
        target_profile = _user_prefixed(self.username)
        pyautogui.write(target_profile, interval=0.1)
        time.sleep(2.5)

        option_x, option_y = community_button_pos.x, community_button_pos.y + 60
        print(f"            -> 🖱️ Haciendo clic en la opción del perfil en ({option_x}, {option_y}).")
        pyautogui.moveTo(option_x, option_y, duration=0.5)
        pyautogui.click()
        time.sleep(2)
        
        print("            -> 🖱️ Buscando 'publicar.png'...")
        if self.pyautogui_service.find_and_click_humanly(["publicar.png"], confidence=0.8):
            print("               -> ✅ ¡Post republicado exitosamente!")
            print("                  -> ⏳ Esperando 10 segundos a que la página del nuevo post cargue...")
            time.sleep(10)
            print("                  -> 🚪 Cerrando la ventana/pestaña de republicación...")
            pyautogui.hotkey('ctrl', 'w')
            time.sleep(2)
            return True
        else:
            print("               -> ⚠️ No se encontró el botón final para publicar.")
            return False

    # --- Flujo Principal de Upvote desde BD ---
    def upvote_from_database(self, interacted_post_ids_session: Set[str]):
        """
        Orquesta el flujo para dar upvote a un post aleatorio de la base de datos.
        """
        print(f"\n--- 🎲 Iniciando interacción: Upvote desde BD para '{self.username}' ---")
        db = next(get_db_secondary())
        try:
            credential_id = self._get_credential_id(db)
            if not credential_id:
                print(f"   -> ⚠️ No se encontró la credencial para el usuario '{self.username}'.")
                return

            random_post = self._get_random_post_from_db(db, credential_id, interacted_post_ids_session)
            if not random_post:
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

    def _get_credential_id(self, db: Session) -> Optional[int]:
        if self.credential_id:
            return self.credential_id
        
        credential = db.query(Credential).filter(Credential.username == self.username).first()
        if credential:
            self.credential_id = credential.id
            return self.credential_id
        return None
    
    def _get_random_post_from_db(self, db: Session, cred_id: int, session_ids: Set[str]) -> Optional[Post]:
        """
        Consulta la base de datos y devuelve un post aleatorio que no ha sido interactuado.
        """
        return db.query(Post).filter(
            not_(Post.interacted_by_credential_ids.contains([cred_id])),
            not_(Post.id.in_(list(session_ids)))
        ).order_by(func.random()).first()

    # --- Acciones de Interacción Simples ---
    def _like_post_with_pyautogui(self) -> bool:
        """Intenta dar upvote a un post usando PyAutoGUI."""
        print("👍 Intentando hacer 'upvote' con PyAutoGUI...")
        try:
            upvote_image_path = os.path.join(PathManager.get_img_folder(), "post_upvote_arrow.png")
            pos = pyautogui.locateCenterOnScreen(upvote_image_path, confidence=0.8)
            if pos:
                HumanInteractionUtils.move_mouse_humanly(pos.x, pos.y)
                pyautogui.click()
                time.sleep(1)
                return True
            return False
        except (ImageNotFoundException, Exception):
            return False

    def prepare_page(self):
        """Prepara la página después del login (refresca, escapa pop-ups)."""
        print("⏳ Esperando 10 segundos después del login...")
        time.sleep(10)
        self.driver.refresh()
        time.sleep(5)
        try:
            self.driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(1)
        except Exception: pass

    def scroll_page(self, direction: str = "down"):
        """Hace scroll en la página."""
        scroll_amount = 800 if direction == "down" else -800
        self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")

    def like_random_post(self):
        """Wrapper para dar like a un post."""
        if self._like_post_with_pyautogui():
            print("  (✅ ¡ÉXITO! Se dio 'upvote' con PyAutoGUI.)\n")
        else:
            print("  (❌ Falló el intento de 'upvote' con PyAutoGUI.)\n")
    
    def analizar_publicaciones_visibles(self) -> List[dict]:
        """Analiza los posts visibles en la pantalla actual."""
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

    # --- Flujos de Cierre de Sesión ---
    def logout(self):
        """Realiza un cierre de sesión estándar."""
        print("\n👋 Iniciando proceso de cierre de sesión...")
        try:
            self.driver.execute_script("document.getElementById('expand-user-drawer-button').click();")
            time.sleep(2)
            self.driver.execute_script("document.getElementById('logout-list-item').click();")
            time.sleep(3)
            print("✅ Cierre de sesión completado exitosamente.")
            print("   -> Cerrando la ventana del navegador con Ctrl+W...")
            pyautogui.hotkey('ctrl', 'w')
            time.sleep(1)
        except Exception as e:
            print(f"🚨 Error durante el cierre de sesión: {e}")

    def logout_and_set_dark_mode(self):
        """Activa el modo oscuro y luego cierra la sesión."""
        print("\n👋 Iniciando proceso de cierre de sesión y activación de modo oscuro...")
        try:
            self.driver.execute_script("document.getElementById('expand-user-drawer-button').click();")
            time.sleep(2)
            self.driver.execute_script("document.getElementById('darkmode-list-item').click();")
            time.sleep(2)
            self.driver.execute_script("document.getElementById('expand-user-drawer-button').click();")
            time.sleep(2)
            self.driver.execute_script("document.getElementById('logout-list-item').click();")
            time.sleep(3)
            print("✅ Modo oscuro activado y cierre de sesión completado.")
            print("   -> Cerrando la ventana del navegador con Ctrl+W...")
            pyautogui.hotkey('ctrl', 'w')
            time.sleep(1)
        except Exception as e:
            print(f"🚨 Error durante el logout especial: {e}")
            self.logout()