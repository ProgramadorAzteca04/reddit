# app/services/reddit/login_service.py
import time
import os
import traceback
import random
from typing import Optional, Tuple
from selenium import webdriver
from .desktop_service import PyAutoGuiService, DesktopUtils, HumanInteractionUtils
from .browser_service import BrowserManager
from .interaction_service import RedditInteractionService
from app.db.database import get_db_secondary
from app.models.reddit_models import Credential

def perform_login_and_setup(username: str, password: str, url: str, window_title: str) -> Tuple[Optional[webdriver.Chrome], Optional[BrowserManager]]:
    """Abre el navegador, realiza el login con PyAutoGUI y conecta Selenium."""
    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_dev_session")
    DEBUGGING_PORT = "9222"

    browser_manager = BrowserManager(CHROME_PATH, USER_DATA_DIR, DEBUGGING_PORT)
    pyautogui_service = PyAutoGuiService()

    try:
        browser_manager.open_chrome_with_debugging(url)
        time.sleep(15)

        if not DesktopUtils.get_and_focus_window(window_title):
            raise RuntimeError("No se pudo encontrar y enfocar la ventana del navegador.")

        print("   -> 🔗 Conectando Selenium al navegador...")
        driver = browser_manager.connect_to_browser()
        if not driver:
            raise ConnectionError("No se pudo conectar Selenium al inicio del proceso.")
        print("   -> ✅ Selenium conectado exitosamente.")

        print("\n--- Iniciando Proceso de Login con PyAutoGUI---")
        
        user_images = ["user.png", "username.png"]
        if not pyautogui_service.find_and_click_humanly(user_images, confidence=0.7):
            raise RuntimeError("No se encontró el campo de usuario.")
        HumanInteractionUtils.type_text_humanly(username)

        password_images = ["password_dark.png", "password_light.png"]
        if not pyautogui_service.find_and_click_humanly(password_images, confidence=0.7):
            raise RuntimeError("No se encontró el campo de contraseña.")
        HumanInteractionUtils.type_text_humanly(password)

        login_images = ["start_dark.png", "start_light.png"]
        if not pyautogui_service.find_and_click_humanly(login_images):
            raise RuntimeError("No se encontró el botón de login.")
        
        print("✅ Login con PyAutoGUI completado.")
        
        return driver, browser_manager

    except Exception as e:
        print(f"\n🚨 ERROR FATAL durante el login y setup: {e}")
        traceback.print_exc()
        if browser_manager:
            browser_manager.quit_driver()
        return None, None

def run_interaction_loop(service: RedditInteractionService, duration_minutes: int, upvote_from_database_enabled: bool, repost_from_feed_enabled: bool):
    """
    Ejecuta un bucle de interacciones aleatorias...
    """
    start_time = time.time()
    
    interacted_post_ids_this_session = set()
    upvote_from_db_has_run = False
    
    action_map = {
        "scroll_page": service.scroll_page,
        "like_random_post": service.like_random_post,
        "analizar_publicaciones_visibles": service.analizar_publicaciones_visibles,
        "upvote_from_database": lambda: service.upvote_from_database(interacted_post_ids_this_session),
        "repost_best_post_from_feed": service.repost_best_post_from_feed
    }
    
    action_pool = ["scroll_page"] * 5 + ["like_random_post"] * 2

    if upvote_from_database_enabled:
        action_pool += ["upvote_from_database"] * 3
        print("   -> Interacción 'upvote_from_database' HABILITADA.")
    
    if repost_from_feed_enabled:
        action_pool += ["repost_best_post_from_feed"] * 2
        print("   -> Interacción 'repost_best_post_from_feed' HABILITADA.")
    
    print("\n" + "="*50)
    print(f"🤖 INICIANDO NAVEGACIÓN DINÁMICA para '{service.username}' 🤖")
    print(f"OBJETIVO: Navegar durante {duration_minutes} minutos.")
    print("="*50 + "\n")
    
    service.prepare_page()
    
    while (time.time() - start_time) / 60 < duration_minutes:
        if not action_pool:
            print("   -> No hay más acciones disponibles.")
            break

        action_name = random.choice(action_pool)
        print(f"\nPróxima acción: {action_name}")

        if action_name == 'upvote_from_database':
            if not upvote_from_db_has_run:
                print("   -> Ejecutando 'upvote_from_database' por única vez en esta sesión.")
                action_to_run = action_map.get(action_name)
                if action_to_run:
                    action_to_run()
                
                upvote_from_db_has_run = True
                action_pool = [action for action in action_pool if action != 'upvote_from_database']
            else:
                print("   -> 'upvote_from_database' ya fue ejecutada, eligiendo otra acción.")
                continue
        else:
            action_to_run = action_map.get(action_name)
            if action_to_run:
                action_to_run()
        
        wait_time = random.randint(5, 12)
        print(f"⏳ Esperando por {wait_time} segundos...")
        time.sleep(wait_time)
        
    print(f"✅ Tiempo límite de {duration_minutes} minutos alcanzado. Finalizando.")


def run_login_flow(
    credential_id: int, 
    url: str, 
    window_title: str, 
    interaction_minutes: int,
    upvote_from_database_enabled: bool,
    repost_from_feed_enabled: bool  # <-- PARÁMETRO AÑADIDO
):
    """
    Orquesta el login y la interacción para una cuenta, obteniendo sus
    credenciales desde la base de datos a través de su ID.
    """
    interaction_service: Optional[RedditInteractionService] = None
    browser_manager: Optional[BrowserManager] = None
    
    db = next(get_db_secondary())
    try:
        credential = db.query(Credential).filter(Credential.id == credential_id).first()
        if not credential:
            print(f"🚨 ERROR: No se encontró ninguna credencial con el ID: {credential_id}")
            return
        
        username = credential.username
        password = credential.password
        
        print(f"\n--- Iniciando login para la cuenta ID #{credential_id} ({username}) ---")

    finally:
        db.close()

    try:
        driver, browser_manager = perform_login_and_setup(username, password, url, window_title)
        if driver and browser_manager:
            interaction_service = RedditInteractionService(driver, username)
            # Pasamos el nuevo parámetro a la función de interacción
            run_interaction_loop(
                interaction_service, 
                interaction_minutes, 
                upvote_from_database_enabled,
                repost_from_feed_enabled  # <-- PARÁMETRO PASADO
            )
    except Exception as e:
        print(f"\n🚨 ERROR FATAL en el flujo principal para '{username}': {e}")
        traceback.print_exc()
    finally:
        if interaction_service:
            interaction_service.logout()
        if browser_manager:
            browser_manager.quit_driver()
        print(f"\nℹ️  Fin del script para la cuenta '{username}'.")