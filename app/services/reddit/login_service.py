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

def perform_login_and_setup(username: str, password: str, url: str, window_title: str) -> Tuple[Optional[webdriver.Chrome], Optional[BrowserManager]]:
    """Abre el navegador, realiza el login con PyAutoGUI y conecta Selenium."""
    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_dev_session")
    DEBUGGING_PORT = "9222"

    browser_manager = BrowserManager(CHROME_PATH, USER_DATA_DIR, DEBUGGING_PORT)
    pyautogui_service = PyAutoGuiService()

    try:
        browser_manager.open_chrome_with_debugging(url)
        time.sleep(5)

        if not DesktopUtils.get_and_focus_window(window_title):
            raise RuntimeError("No se pudo encontrar y enfocar la ventana del navegador.")

        print("\n--- Iniciando Proceso de Login con PyAutoGUI---")
        
        # Ingresar nombre de usuario
        user_images = ["user.png", "username.png"]
        if not pyautogui_service.find_and_click_humanly(user_images, confidence=0.7):
            raise RuntimeError("No se encontró el campo de usuario.")
        HumanInteractionUtils.type_text_humanly(username)

        # Ingresar contraseña
        password_images = ["password_dark.png", "password_light.png"]
        if not pyautogui_service.find_and_click_humanly(password_images, confidence=0.7):
            raise RuntimeError("No se encontró el campo de contraseña.")
        HumanInteractionUtils.type_text_humanly(password)

        # Clic en el botón de login
        login_images = ["start_dark.png", "start_light.png"]
        if not pyautogui_service.find_and_click_humanly(login_images):
            raise RuntimeError("No se encontró el botón de login.")
        
        print("✅ Login con PyAutoGUI completado.")
        
        driver = browser_manager.connect_to_browser()
        if not driver:
            raise ConnectionError("No se pudo conectar Selenium al navegador.")
        
        return driver, browser_manager

    except Exception as e:
        print(f"\n🚨 ERROR FATAL durante el login y setup: {e}")
        traceback.print_exc()
        # Asegurarse de cerrar el driver si algo falla
        if browser_manager:
            browser_manager.quit_driver()
        return None, None

def run_interaction_loop(service: RedditInteractionService, duration_minutes: int):
    """Ejecuta un bucle de interacciones aleatorias durante un tiempo determinado."""
    start_time = time.time()
    action_map = {
        "scroll_page": service.scroll_page,
        "like_random_post": service.like_random_post,
        "analizar_publicaciones_visibles": service.analizar_publicaciones_visibles
    }
    action_pool = ["scroll_page"] * 5 + ["like_random_post"] * 2 + ["analizar_publicaciones_visibles"] * 1
    
    print("\n" + "="*50)
    print("🤖 INICIANDO NAVEGACIÓN DINÁMICA 🤖")
    print(f"OBJETIVO: Navegar durante {duration_minutes} minutos.")
    print("="*50 + "\n")
    
    service.prepare_page()
    
    while (time.time() - start_time) / 60 < duration_minutes:
        action_name = random.choice(action_pool)
        print(f"\nPróxima acción: {action_name}")
        action_to_run = action_map.get(action_name)
        if action_to_run:
            action_to_run()
        else:
            print(f"⚠️ Acción '{action_name}' no reconocida.")
        
        wait_time = random.randint(5, 12)
        print(f"⏳ Esperando por {wait_time} segundos...")
        time.sleep(wait_time)
        
    print(f"✅ Tiempo límite de {duration_minutes} minutos alcanzado. Finalizando.")


def run_login_flow(username: str, password: str, url: str, window_title: str, interaction_minutes: int):
    """Flujo principal que orquesta el login y la posterior interacción."""
    interaction_service: Optional[RedditInteractionService] = None
    browser_manager: Optional[BrowserManager] = None
    try:
        driver, browser_manager = perform_login_and_setup(username, password, url, window_title)
        if driver and browser_manager:
            interaction_service = RedditInteractionService(driver)
            run_interaction_loop(interaction_service, interaction_minutes)
    except Exception as e:
        print(f"\n🚨 ERROR FATAL en el flujo principal: {e}")
        traceback.print_exc()
        print("\nProceso abortado.")
    finally:
        if interaction_service:
            interaction_service.logout()
        if browser_manager:
            browser_manager.quit_driver()
        print("\nℹ️  El script ha finalizado. Se ha ejecutado el intento de cierre de sesión.")