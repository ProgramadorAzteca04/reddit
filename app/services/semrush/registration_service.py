# app/services/semrush/registration_service.py
import time
import os
import traceback
from app.services.reddit.browser_service import BrowserManager
from app.services.reddit.proxy_service import ProxyManager
from app.services.reddit.desktop_service import DesktopUtils, HumanInteractionUtils
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

def run_semrush_signup_flow():
    """
    Orquesta el flujo de registro en Semrush: navega, rellena los campos
    y hace clic en el botón para crear la cuenta.
    """
    print("\n" + "="*60)
    print("🚀 INICIANDO FLUJO: Registro en Semrush.")
    print("="*60)

    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    URL = "https://es.semrush.com/signup/"
    WINDOW_TITLE = "Semrush"
    DEBUGGING_PORT = "9225"
    USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_dev_session")

    browser_manager = None
    driver = None
    try:
        proxy_manager = ProxyManager()
        proxy = proxy_manager.get_random_proxy()
        user_agent = proxy_manager.get_random_user_agent()

        browser_manager = BrowserManager(
            chrome_path=CHROME_PATH,
            user_data_dir=USER_DATA_DIR,
            port=DEBUGGING_PORT,
            proxy=proxy,
            user_agent=user_agent
        )

        browser_manager.open_chrome_with_debugging(URL)
        
        print("\n   -> Esperando 20 segundos para que la página cargue...")
        time.sleep(20)

        DesktopUtils.get_and_focus_window(WINDOW_TITLE)
        
        print("\n   -> Conectando Selenium para interactuar con la página...")
        driver = browser_manager.connect_to_browser()
        if not driver:
            raise ConnectionError("No se pudo conectar Selenium al navegador.")

        wait = WebDriverWait(driver, 20)
        
        # 1. Obtener y escribir el correo
        email_to_use = HumanInteractionUtils.get_random_email_from_file()
        if not email_to_use:
            raise ValueError("No se pudo obtener un correo del archivo correos.txt.")
        
        print(f"   -> Usando el correo: {email_to_use}")
        email_field = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-test="signup-page__input-email"]'))
        )
        email_field.click()
        time.sleep(1)
        email_field.send_keys(email_to_use)
        print("   -> ✅ Correo electrónico escrito exitosamente.")

        # 2. Generar y escribir la contraseña
        password_to_use = HumanInteractionUtils.generate_password(length=14)
        
        password_field = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-test="signup-page__input-password"]'))
        )
        password_field.click()
        time.sleep(1)
        password_field.send_keys(password_to_use)
        print("   -> ✅ Contraseña escrita exitosamente.")

        # --- 3. HACER CLIC EN EL BOTÓN DE CREAR CUENTA (NUEVO PASO) ---
        print("   -> Buscando el botón 'Crear una cuenta'...")
        
        create_account_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-test="signup-page__btn-signup"]'))
        )
        create_account_button.click()
        
        print("   -> ✅ Clic exitoso en 'Crear una cuenta'.")
        # -----------------------------------------------------------
        
        print("\n   -> Proceso de registro enviado. La ventana permanecerá abierta por 45 segundos para observar el resultado.")
        time.sleep(45)

    except TimeoutException as e:
        print(f"   -> 🚨 ERROR: Tiempo de espera agotado. No se pudo encontrar un elemento: {e}")
    except Exception as e:
        print(f"\n🚨 ERROR FATAL durante el flujo de Semrush: {e}")
        traceback.print_exc()
    finally:
        if browser_manager:
            browser_manager.quit_driver()
        print("\n" + "="*60)
        print("✅ SERVICIO FINALIZADO: Flujo de Semrush.")
        print("="*60 + "\n")