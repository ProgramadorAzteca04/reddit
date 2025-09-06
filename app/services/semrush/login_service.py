# app/services/semrush/login_service.py
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
from app.services.reddit.browser_service import BrowserManagerProxy
from selenium.webdriver.support import expected_conditions as EC
from app.services.reddit.proxy_service import ProxyManager
from selenium.webdriver.remote.webdriver import WebDriver
from app.models.semrush_models import Campaign, CredentialSemrush
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from app.db.database import get_db
import traceback
import time
import os


# --- ¡NUEVA FUNCIÓN DE LOGOUT AÑADIDA! ---
def _perform_logout(driver: "WebDriver", wait: "WebDriverWait"):
    """
    Realiza el proceso de cierre de sesión en Semrush.
    """
    print("\n   -> 👋 Iniciando proceso de cierre de sesión...")
    try:
        # 1. Hacer clic en el botón del menú de usuario
        print("      -> Buscando el botón del perfil de usuario...")
        user_menu_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-test="header-menu__user"]'))
        )
        
        # A veces un overlay puede interferir, usamos JavaScript como alternativa robusta
        try:
            user_menu_button.click()
        except ElementClickInterceptedException:
            print("      -> Clic interceptado. Intentando con JavaScript...")
            driver.execute_script("arguments[0].click();", user_menu_button)

        print("      -> ✅ Clic en el perfil realizado. Esperando el menú...")
        time.sleep(2) # Pausa para que el menú desplegable se muestre correctamente

        # 2. Hacer clic en el enlace de "Cerrar sesión"
        print("      -> Buscando el enlace de 'Cerrar sesión'...")
        logout_link = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'a[data-test="header-menu__user-logout"]'))
        )
        logout_link.click()
        print("      -> ✅ Clic en 'Cerrar sesión' realizado.")
        
        # Esperamos a que la página de login vuelva a aparecer como confirmación
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'input[name="email"]')))
        print("   -> 🎉 ¡Cierre de sesión completado exitosamente!")
        time.sleep(3)

    except TimeoutException:
        print("      -> 🚨 ERROR: No se pudo encontrar un elemento para el cierre de sesión.")
    except Exception as e:
        print(f"      -> 🚨 Ocurrió un error inesperado durante el logout: {e}")
# -----------------------------------------------


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

    finally:
        db.close()

    # --- 2. Configuración del Navegador ---
    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    URL = "https://es.semrush.com/login/"
    USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_dev_session")

    browser_manager = None
    driver = None
    
    try:
        # --- Lógica de Proxy Mejorada ---
        proxy_config = None
        if proxy_host and proxy_port:
            print(f"   -> Buscando credenciales para el proxy {proxy_host}:{proxy_port} en 'proxies.txt'...")
            proxy_manager = ProxyManager()
            proxy_config = proxy_manager.get_proxy_by_host_port(proxy_host, proxy_port)
            
            if proxy_config:
                print("      -> ✅ Credenciales del proxy encontradas.")
            else:
                raise ValueError(f"El proxy {proxy_host}:{proxy_port} de la BD no existe en proxies.txt")
        else:
            print("   -> ⚠️ No se utilizará proxy (no definido en la base de datos).")

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
        print("\n   -> 🎉 ¡Login exitoso! La sesión permanecerá abierta por 30 segundos.")
        time.sleep(30) # Reducido para pruebas más rápidas

        # --- ¡LLAMADA A LA NUEVA FUNCIÓN DE LOGOUT! ---
        _perform_logout(driver, wait)
        # ---------------------------------------------

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


def run_semrush_config_account_flow(id_campaign: int, city: str):
    """
    Busca una cuenta de Semrush sin campaña, realiza el login, configura el proyecto
    con la web de la campaña y, solo si tiene éxito, actualiza la base de datos.
    """
    print("\n" + "="*60)
    print(f"🚀 INICIANDO FLUJO: Configuración de cuenta para Campaña ID #{id_campaign} en {city}.")
    print("="*60)

    # Paso 1: Buscar credencial y campaña sin modificar la BD
    db = next(get_db())
    try:
        print("   -> 🔍 Buscando una credencial disponible en la base de datos...")
        credential_to_use = db.query(CredentialSemrush).filter(CredentialSemrush.id_campaigns == None).first()
        if not credential_to_use:
            raise ValueError("No se encontró ninguna credencial con 'id_campaigns' vacío.")
        print(f"   -> ✅ Credencial encontrada (ID: {credential_to_use.id}), email: '{credential_to_use.email}'.")

        print(f"   -> 🔍 Buscando la campaña con ID: {id_campaign}...")
        campaign = db.query(Campaign).filter(Campaign.id == id_campaign).first()
        if not campaign:
            raise ValueError(f"No se encontró ninguna campaña con el ID: {id_campaign}")
        if not campaign.web:
            raise ValueError(f"La campaña con ID {id_campaign} no tiene una URL web definida.")
        print(f"   -> ✅ Campaña encontrada. Web a configurar: '{campaign.web}'")
        
        web_url = campaign.web
        email = credential_to_use.email
        password = credential_to_use.password
        proxy_host = credential_to_use.proxy
        proxy_port = credential_to_use.port

    except Exception as e:
        print(f"   -> 🚨 ERROR en la preparación: {e}")
        return
    finally:
        db.close()

    # Paso 2: Configuración del navegador y login
    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    URL = "https://es.semrush.com/login/"
    USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_dev_session")
    browser_manager = None
    
    try:
        proxy_config = None
        if proxy_host and proxy_port:
            proxy_manager = ProxyManager()
            proxy_config = proxy_manager.get_proxy_by_host_port(proxy_host, proxy_port)
            if not proxy_config:
                raise ValueError(f"El proxy {proxy_host}:{proxy_port} de la BD no existe en proxies.txt")
        
        browser_manager = BrowserManagerProxy(
            chrome_path=CHROME_PATH, user_data_dir=USER_DATA_DIR, port="", proxy=proxy_config
        )
        driver = browser_manager.get_configured_driver(URL)
        if not driver:
            raise RuntimeError("No se pudo iniciar el driver de Selenium-Wire.")

        print("\n   -> Esperando para que la página de login cargue...")
        time.sleep(20)
        wait = WebDriverWait(driver, 30)

        # Llenado del formulario de login
        email_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[name="email"]')))
        email_field.click(); time.sleep(1); email_field.send_keys(email)

        password_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[name="password"]')))
        password_field.click(); time.sleep(1); password_field.send_keys(password)
        
        login_button = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[.//span[text()="Iniciar sesión"]]')))
        login_button.click()
        print("      -> ✅ Clic en 'Iniciar sesión' realizado.")

        # Paso 3: Configurar el proyecto con la web
        print("\n   -> 🌐 Esperando a la página de creación de proyecto...")
        web_input_selector = 'input[data-ui-name="Input.Value"][placeholder="Indica el nombre de tu sitio web"]'
        web_input = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, web_input_selector)))
        
        print(f"   -> ✍️  Introduciendo la web '{web_url}' en el campo del proyecto...")
        web_input.send_keys(web_url)
        time.sleep(2)
        
        # --- ¡NUEVO BLOQUE DE CÓDIGO AÑADIDO! ---
        print("\n   -> 🛠️  Buscando el botón 'Configurar' de seguimiento de posición...")
        # Este XPath busca el div con el data-path específico y luego el botón que contiene el texto 'Configurar'
        config_button_xpath = '//div[@data-path="position_tracking"]//button[.//div[text()="Configurar"]]'
        
        config_button = wait.until(EC.element_to_be_clickable((By.XPATH, config_button_xpath)))
        
        config_button.click()
        print("   -> ✅ Clic en el botón 'Configurar' realizado.")
        # -----------------------------------------------

        # Paso 4: SOLO SI TODO LO ANTERIOR ES CORRECTO, actualizar la BD
        print("\n   -> 💾 Proceso de automatización exitoso. Actualizando la base de datos...")
        db = next(get_db())
        try:
            credential_to_update = db.query(CredentialSemrush).filter(CredentialSemrush.id == credential_to_use.id).first()
            if credential_to_update:
                credential_to_update.id_campaigns = id_campaign
                db.commit()
                print("   -> ✅ ¡Base de datos actualizada! La campaña ha sido asignada a la credencial.")
            else:
                print("   -> 🚨 ERROR: No se encontró la credencial para actualizar al final del proceso.")
        except Exception as db_error:
            print(f"   -> 🚨 ERROR al actualizar la base de datos al final: {db_error}")
            db.rollback()
        finally:
            db.close()

        print("\n   -> 🎉 ¡Configuración completada! La sesión permanecerá abierta por 20 segundos.")
        time.sleep(20)
        _perform_logout(driver, wait)

    except Exception as e:
        print(f"\n🚨 ERROR FATAL durante el flujo de configuración: {e}")
        traceback.print_exc()
        print("   -> ❌ Como el proceso falló, NO se ha realizado ninguna modificación en la base de datos.")
    finally:
        if browser_manager:
            browser_manager.quit_driver()
        print("\n" + "="*60)
        print("✅ SERVICIO FINALIZADO: Flujo de configuración de cuenta Semrush.")
        print("="*60 + "\n")