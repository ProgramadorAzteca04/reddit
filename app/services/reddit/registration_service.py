# app/services/reddit/registration_service.py
import time
import os
import traceback
import pyperclip
import pyautogui
from .desktop_service import PyAutoGuiService, HumanInteractionUtils, DesktopUtils
from .browser_service import BrowserManager
from .proxy_service import ProxyManager
from app.services.email_reader_service import get_latest_verification_code
from app.db.database import get_db_secondary
from app.models.reddit_models import Credential
from .interaction_service import RedditInteractionService

def run_registration_flow(email: str, url: str) -> bool:
    """
    Flujo principal que orquesta el registro usando un proxy aleatorio.
    Devuelve True si el registro fue exitoso, False si el correo es rechazado.
    """
    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    DEBUGGING_PORT = "9223"
    WINDOW_TITLE = "Reddit"
    USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_dev_session")
    
    proxy_manager = ProxyManager()
    proxy = proxy_manager.get_random_proxy()
    user_agent = proxy_manager.get_random_user_agent()

    browser_manager = BrowserManager(CHROME_PATH, USER_DATA_DIR, DEBUGGING_PORT, proxy=proxy, user_agent=user_agent)
    pyautogui_service = PyAutoGuiService()
    
    username = ""
    driver = None
    registration_successful = False

    try:
        browser_manager.open_chrome_with_debugging(url)
        time.sleep(15)
        
        if not DesktopUtils.get_and_focus_window(WINDOW_TITLE):
            raise RuntimeError("No se pudo encontrar y enfocar la ventana del navegador.")

        driver = browser_manager.connect_to_browser()
        if not driver:
            raise ConnectionError("No se pudo conectar Selenium al inicio del proceso.")

        print("\n--- Iniciando Proceso de Registro con PyAutoGUI ---")
        
        if not pyautogui_service.find_and_click_humanly(["correo_dark.png", "correo_ligh.png"], attempts=2):
            raise RuntimeError("No se encontró el campo de correo.")
        HumanInteractionUtils.type_text_humanly(email)

        continue_images = ["continuar1.png", "continuar1_ligh.png"]
        if not pyautogui_service.find_and_click_humanly(continue_images, attempts=5):
            raise RuntimeError("No se encontró el primer botón 'Continuar'.")
        
        time.sleep(2)

        verification_code = get_latest_verification_code(subject_keywords=["verification", "verificación"])
        if verification_code:
            pyautogui_service.find_and_click_humanly(["verification.png"], attempts=3, wait_time=2)
            HumanInteractionUtils.type_text_humanly(verification_code)
            pyautogui_service.find_and_click_humanly(continue_images)

        if not pyautogui_service.find_and_click_humanly(["usuario.png", "usuario_ligh.png"], attempts=5, wait_time=2):
            raise RuntimeError("No se encontró el campo de nombre de usuario.")
        pyautogui.hotkey('ctrl', 'a'); time.sleep(0.5)
        pyautogui.hotkey('ctrl', 'c')
        username = pyperclip.paste()
        print(f"📋 Nombre de usuario capturado: '{username}'")

        if not pyautogui_service.find_and_click_humanly(["password_dark.png", "password_ligh.png"]):
            raise RuntimeError("No se encontró el campo de contraseña.")
        password = HumanInteractionUtils.generate_password()
        HumanInteractionUtils.type_text_humanly(password)

        if not pyautogui_service.find_and_click_humanly(continue_images):
            raise RuntimeError("No se encontró el segundo botón 'Continuar'.")
        time.sleep(5)

        if pyautogui_service.find_and_click_humanly(["gender.png"], attempts=5):
            time.sleep(2)
        if pyautogui_service.find_and_click_humanly(["interes14.png"], attempts=10, scroll_on_fail=True):
            pyautogui_service.find_and_click_humanly(continue_images)

        print("✅ Registro con PyAutoGUI completado.")
        
        db = next(get_db_secondary())
        try:
            db.add(Credential(username=username, password=password, email=email))
            db.commit()
            print("✅ Credenciales guardadas exitosamente.")
            registration_successful = True
        except Exception as db_error:
            print(f"🚨 ERROR al guardar credenciales: {db_error}")
            db.rollback()
        finally:
            db.close()

    except Exception as e:
        print(f"\n🚨 ERROR FATAL durante el flujo de registro: {e}")
        print("   -> Intentando cerrar la ventana del navegador con Ctrl+W...")
        pyautogui.hotkey('ctrl', 'w')
        time.sleep(1)
        traceback.print_exc()

    finally:
        if registration_successful and driver:
            print("\n--- Finalizando sesión de registro ---")
            time.sleep(10)
            driver.refresh()
            time.sleep(5)
            
            try:
                interaction_service = RedditInteractionService(driver, username)
                interaction_service.logout_and_set_dark_mode()
            except Exception as final_e:
                print(f"   -> ⚠️ Error durante el proceso de cierre final: {final_e}")
        
        if browser_manager:
            browser_manager.quit_driver()
        
        print("\nℹ️  El script de registro ha finalizado.")
        return registration_successful