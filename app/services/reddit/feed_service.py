# app/services/reddit/feed_service.py
import time
import pyautogui
from bs4 import BeautifulSoup
from typing import List, Dict, Optional

# Importaciones de otros módulos de tu proyecto
from app.services.openai.content_generator_service import select_best_post_title
from .desktop_service import PyAutoGuiService, PathManager
from app.models.reddit_models import Credential
import os

# --- Helper para normalizar el prefijo "u/" ---
def _user_prefixed(username: str) -> str:
    u = (username or "").strip()
    if not u: return "u/"
    if u.lower().startswith("u/"): return "u/" + u.split("/", 1)[1]
    return "u/" + u

class FeedService:
    def __init__(self, page_source: str):
        self.soup = BeautifulSoup(page_source, 'lxml')

    def get_best_post_by_ai(self) -> Optional[Dict[str, str]]:
        posts_articles = self.soup.find_all('shreddit-post')
        print(f"✅ Se encontraron {len(posts_articles)} publicaciones en el feed para analizar.")
        all_posts = []
        for post in posts_articles:
            permalink = post.get('permalink', '')
            post_link = f"https://www.reddit.com{permalink}" if permalink else None
            title_element = post.find('a', {'slot': 'title'})
            post_title = title_element.get_text(strip=True) if title_element else None
            if post_title and post_link:
                all_posts.append({"title": post_title, "link": post_link})
        if not all_posts:
            print("   -> No se encontraron publicaciones válidas para enviar a la IA.")
            return None
        titles = [post['title'] for post in all_posts]
        best_title = select_best_post_title(titles)
        if not best_title:
            print("   -> La IA no seleccionó ningún título.")
            return None
        for post in all_posts:
            if post['title'] == best_title:
                return post
        print(f"   -> ⚠️ No se encontró coincidencia para '{best_title}'. Usando el primer post.")
        return all_posts[0] if all_posts else None


# --- FUNCIÓN ORQUESTADORA PRINCIPAL (CON LA SOLUCIÓN FINAL) ---
def run_repost_from_feed_flow(credential: Credential):
    """
    Orquesta el flujo completo, incluyendo el regreso a la página principal al final.
    """
    # Solución: Importación local para romper el ciclo de dependencias.
    from .login_service import perform_login_and_setup

    print(f"Iniciando flujo de republicación para el usuario: {credential.username}...")

    driver = None
    browser_manager = None
    try:
        pyautogui_service = PyAutoGuiService()
        driver, browser_manager = perform_login_and_setup(
            username=credential.username,
            password=credential.password,
            url="https://www.reddit.com/",
            window_title="Reddit"
        )

        if not driver or not browser_manager:
            raise RuntimeError("Falló el proceso de login y configuración del navegador.")

        print("Sesión iniciada. Esperando 10 segundos a que el feed cargue...")
        time.sleep(10)

        print("\nIniciando análisis del feed con IA...")
        feed_service = FeedService(driver.page_source)
        best_post = feed_service.get_best_post_by_ai()

        if not best_post:
            print("No se pudo seleccionar una publicación del feed. Finalizando flujo.")
            return

        print("\n<------------------------------------------------------------>")
        print(f"🎯 MEJOR PUBLICACIÓN SELECCIONADA POR IA:")
        print(f"   -> Título: {best_post['title']}")
        print(f"   -> Enlace: {best_post['link']}")
        print("<------------------------------------------------------------>")

        print(f"\n🚀 Navegando a la publicación seleccionada...")
        driver.get(best_post['link'])

        print("   -> Esperando 10 segundos en la página del post...")
        time.sleep(10)

        print("   -> 🖱️ Buscando y haciendo clic en 'compartir.png'...")
        if pyautogui_service.find_and_click_humanly(['compartir.png']):
            print("   -> ✅ Botón de compartir encontrado y presionado.")
            print("      -> Esperando 2 segundos para que aparezca el menú...")
            time.sleep(2)
            print("      -> 🖱️ Buscando y haciendo clic en 'republicar.png'...")
            if pyautogui_service.find_and_click_humanly(['republicar.png']):
                print("      -> ✅ Botón de republicar encontrado y presionado.")
                print("         -> Esperando 10 segundos para que cargue la vista de republicación...")
                time.sleep(10)

                img_path = os.path.join(PathManager.get_img_folder(), "select_community.png")
                community_button_pos = pyautogui.locateCenterOnScreen(img_path, confidence=0.8)

                if community_button_pos:
                    pyautogui.click(community_button_pos)
                    print("            -> ✅ Botón de comunidad encontrado y presionado.")
                    time.sleep(1.5)

                    target_profile = _user_prefixed(credential.username)
                    pyautogui.write(target_profile, interval=0.1)
                    time.sleep(2.5)

                    option_x = community_button_pos.x
                    option_y = community_button_pos.y + 60

                    print(f"            -> Moviendo el ratón a la posición estimada ({option_x}, {option_y}) y haciendo clic.")
                    pyautogui.moveTo(option_x, option_y, duration=0.5)
                    pyautogui.click()
                    print("            -> ✅ Perfil de usuario seleccionado mediante clic directo.")

                    time.sleep(2)
                    print("         -> 🖱️ Buscando el botón final para publicar...")
                    if pyautogui_service.find_and_click_humanly(["publicar.png"], confidence=0.8):
                        print("            -> ✅ ¡Post republicado exitosamente!")
                    else:
                        print("            -> ⚠️ No se encontró el botón final para publicar.")
                else:
                    print("         -> ⚠️ No se encontró el botón para seleccionar comunidad.")
            else:
                print("      -> ⚠️ No se encontró el botón de republicar.")
        else:
            print("   -> ⚠️ No se encontró el botón de compartir en la pantalla.")

        print("\n   -> ✅ Flujo completado. Volviendo a la página principal de Reddit...")
        driver.get("https://www.reddit.com/")
        print("   -> Esperando 10 segundos para visualización final...")
        time.sleep(10)

    except Exception as e:
        print(f"🚨 Ocurrió un error fatal durante el flujo de republicación: {e}")
    finally:
        if browser_manager:
            browser_manager.quit_driver()
        print("Navegador cerrado. Fin del proceso.")