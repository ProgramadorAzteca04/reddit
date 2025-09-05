# app/services/semrush/login_service.py
import time
import os
import traceback
from app.services.reddit.browser_service import BrowserManagerProxy
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# --- Importaciones para la Base de Datos ---
from app.db.database import get_db
from app.models.semrush_models import CredentialSemrush

def run_semrush_login_flow(credential_id: int):
    """
    Orquesta el flujo de inicio de sesión en Semrush para una credencial específica.
    """
    print("\n" + "="*60)
    print(f"🚀 INICIANDO FLUJO: Login en Semrush para la credencial ID #{credential_id}.")
    print("="*60)

    # --- 1. Obtener Credenciales de la Base de Datos ---
    db = next(get_db())
    try:
        credential = db.query(CredentialSemrush).filter(CredentialSemrush.id == credential_id).first()
        if not credential:
            print(f"   -> 🚨 ERROR: No se encontró la credencial de Semrush con ID: {credential_id}")
            return
        
        email = credential.email
        password = credential.password
        proxy_host = credential.proxy
        proxy_port = credential.port
        
        print(f"   -> ✅ Credenciales encontradas para el correo: '{email}'")
        if proxy_host and proxy_port:
            print(f"   -> Usando el proxy: {proxy_host}:{proxy_port}")
        else:
            print("   -> ⚠️ No se utilizará proxy (no definido en la base de datos).")

    finally:
        db.close()

    # --- 2. Configuración del Navegador ---
    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    URL = "https://es.semrush.com/login/"
    USER_DATA_DIR = os.path.join(os.getcwd(), f"chrome_session_semrush_{credential_id}")

    browser_manager = None
    driver = None
    
    try:
        # Preparamos la configuración del proxy si existe
        proxy_config = None
        if proxy_host and proxy_port:
            # Asumimos que el proxy no tiene user/pass ya que no está en la tabla
            proxy_config = {
                "host": proxy_host,
                "port": proxy_port,
                "user": "",
                "pass": ""
            }

        browser_manager = BrowserManagerProxy(
            chrome_path=CHROME_PATH, 
            user_data_dir=USER_DATA_DIR, 
            port="",
            proxy=proxy_config
        )
        
        driver = browser_manager.get_configured_driver(URL)
        if not driver:
            raise RuntimeError("No se pudo iniciar el driver de Selenium-Wire.")

        print("\n   -> Esperando 20 segundos para que la página de login cargue...")
        time.sleep(20)
        
        wait = WebDriverWait(driver, 30)

        # --- 3. Llenado del Formulario de Login ---
        print("   -> 📧 Buscando el campo de email...")
        email_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[name="email"]')))
        email_field.click(); time.sleep(1)
        email_field.send_keys(email)
        print("      -> Email introducido.")

        print("   -> 🔒 Buscando el campo de contraseña...")
        password_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[name="password"]')))
        password_field.click(); time.sleep(1)
        password_field.send_keys(password)
        print("      -> Contraseña introducida.")
        
        print("   -> 🚪 Buscando el botón de 'Iniciar sesión'...")
        login_button = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[.//span[text()="Iniciar sesión"]]')))
        login_button.click()
        print("      -> ✅ Clic en 'Iniciar sesión' realizado.")

        # Esperamos a que la URL cambie como señal de un login exitoso
        wait.until(EC.url_contains("projects"))
        print("\n   -> 🎉 ¡Login exitoso! La sesión permanecerá abierta por 60 segundos.")
        time.sleep(60)

    except TimeoutException:
        print("\n   -> 🚨 ERROR: El login falló. Un elemento no fue encontrado a tiempo o la URL no cambió.")
        print("      -> La ventana permanecerá abierta 20 segundos para inspección.")
        time.sleep(20)
    except Exception as e:
        print(f"\n🚨 ERROR FATAL durante el flujo de login de Semrush: {e}")
        traceback.print_exc()
    finally:
        if browser_manager:
            browser_manager.quit_driver()
        print("\n" + "="*60)
        print("✅ SERVICIO FINALIZADO: Flujo de login de Semrush.")
        print("="*60 + "\n")