# app/services/github/login_service.py
import time
import os
import traceback
import random
from app.services.reddit.browser_service import BrowserManagerProxy
from app.services.reddit.proxy_service import ProxyManager
from app.services.reddit.desktop_service import DesktopUtils
from app.db.database import get_db_secondary
from app.models.git import Credential as GitCredential

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

# =======================================================
# Funciones de ayuda para interacciones humanas
# =======================================================
def _human_type_into(wait, driver, locator, text: str, label: str,
                       clear_first: bool = False,
                       click_first: bool = True,
                       per_char_delay: tuple[float, float] = (0.05, 0.16),
                       timeout: int = 20) -> bool:
    """
    Escribe texto en un campo simulando la escritura de una persona.
    """
    try:
        el = WebDriverWait(driver, timeout).until(EC.visibility_of_element_located(locator))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.5)

        if click_first:
            ActionChains(driver).move_to_element(el).pause(0.2).click(el).perform()
            time.sleep(0.2)

        if clear_first:
            try:
                el.clear(); time.sleep(0.1)
            except Exception:
                el.send_keys(Keys.CONTROL, 'a'); time.sleep(0.1)
                el.send_keys(Keys.DELETE); time.sleep(0.1)

        for ch in text:
            el.send_keys(ch)
            time.sleep(random.uniform(*per_char_delay))
        
        print(f"      -> ✅ Texto (humano) enviado a '{label}'.")
        time.sleep(0.5)
        return True
    except Exception as e:
        print(f"      -> ⏱️ Timeout/err tipeando en '{label}': {e}")
        return False

def _human_click(wait, driver, locator, label: str, timeout: int = 20) -> bool:
    """
    Realiza un clic simulando el comportamiento humano.
    """
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(locator))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.5)
        ActionChains(driver).move_to_element(el).pause(0.2).click(el).perform()
        print(f"      -> ✅ Click humano en '{label}'.")
        time.sleep(0.5)
        return True
    except Exception as e:
        print(f"      -> ❌ Falló click en '{label}': {e}")
        return False

def _click_signin_with_js(driver) -> bool:
    """
    Busca y hace clic en el botón 'Sign in' visible usando un script de JavaScript.
    """
    print("      -> Intentando clic con JavaScript...")
    js_script = """
    const elements = document.querySelectorAll("a[data-ga-click='Header, sign in']");
    let clicked = false;
    elements.forEach(el => {
        if (el.offsetParent !== null && !clicked) {
            el.click();
            clicked = true;
        }
    });
    return clicked;
    """
    try:
        result = driver.execute_script(js_script)
        if result:
            print("      -> ✅ Clic con JavaScript exitoso.")
            return True
        else:
            print("      -> ❌ El script de JavaScript no encontró un elemento visible para hacer clic.")
            return False
    except Exception as e:
        print(f"      -> ❌ Falló la ejecución del script de JavaScript: {e}")
        return False

# =======================================================
# Función reutilizable para cerrar sesión
# =======================================================
def _perform_github_logout(driver, wait) -> bool:
    """
    Realiza el proceso de cierre de sesión en GitHub, incluyendo la confirmación final.
    """
    try:
        # 1. Hacer clic en el botón de perfil/avatar para abrir el menú
        profile_button_locator = (By.CSS_SELECTOR, "button[aria-label='View profile and more']")
        if not _human_click(wait, driver, profile_button_locator, "botón de perfil (avatar)"):
            return False
        
        time.sleep(1) # Espera a que el menú desplegable aparezca

        # 2. Hacer clic en el botón de "Sign out"
        sign_out_locator = (By.XPATH, "//button[.//span[normalize-space()='Sign out']]")
        if not _human_click(wait, driver, sign_out_locator, "botón 'Sign out'"):
            return False
        
        # 3. NUEVO: Esperar y hacer clic en el botón de confirmación final
        print("   -> ⏳ Esperando la página de confirmación de cierre de sesión...")
        final_logout_locator = (By.CSS_SELECTOR, "input[type='submit'][value='Sign out from all accounts']")
        if not _human_click(wait, driver, final_logout_locator, "botón 'Sign out from all accounts'"):
            print("   -> ⚠️ No se pudo hacer clic en el botón de confirmación final.")
            return False
        
        time.sleep(10) # Espera a que el cierre de sesión se procese
            
        print("   -> ✅ Cierre de sesión completado y confirmado.")
        return True
    except Exception as e:
        print(f"   -> 🚨 Error durante el cierre de sesión: {e}")
        return False

# =======================================================
# Función reutilizable para iniciar sesión
# =======================================================
def perform_github_login(driver, wait, login_identifier, password) -> bool:
    """
    Realiza el proceso de inicio de sesión en GitHub.
    """
    # 1. Clic en el botón "Sign in" de la página principal
    print("\n   -> 🖱️  Intentando hacer clic en 'Sign in' con un comando de script...")
    time.sleep(5)
    if not _click_signin_with_js(driver):
        print("   -> ❌ No se pudo hacer clic en el botón de 'Sign in' inicial. Abortando.")
        return False

    # 2. Rellenar formulario de login
    print("\n   -> 📝 Rellenando formulario de inicio de sesión...")
    
    login_locator = (By.ID, "login_field")
    if not _human_type_into(wait, driver, login_locator, login_identifier, "campo de usuario/email"):
        return False

    password_locator = (By.ID, "password")
    if not _human_type_into(wait, driver, password_locator, password, "campo de contraseña"):
        return False

    signin_button_locator = (By.NAME, "commit")
    if not _human_click(wait, driver, signin_button_locator, "botón 'Sign in' final"):
        return False
    
    print("   -> ✅ Formulario de login enviado.")
    return True

# =======================================================
# Flujo principal que orquesta todo el proceso
# =======================================================
def run_github_login_flow(credential_id: int):
    """
    Orquesta el flujo completo de login y logout en GitHub para una credencial.
    """
    print("\n" + "="*60)
    print(f"🚀 INICIANDO FLUJO: Login y Logout en GitHub para la credencial ID #{credential_id}.")
    print("="*60)

    # --- 1. Obtener credenciales ---
    db = next(get_db_secondary())
    try:
        credential = db.query(GitCredential).filter(GitCredential.id == credential_id).first()
        if not credential:
            print(f"   -> 🚨 ERROR: No se encontró la credencial de GitHub con ID: {credential_id}")
            return
        
        login_identifier = credential.username
        password = credential.password
        proxy_host = credential.proxy
        proxy_port = credential.port
        
        print(f"   -> ✅ Credenciales encontradas para el usuario: '{login_identifier}'")
    finally:
        db.close()

    # --- 2. Configuración del navegador ---
    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    URL = "https://gist.github.com/starred"
    USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_dev_session_github_login")
    WINDOW_TITLE = "GitHub"

    browser_manager = None
    driver = None

    try:
        # --- 3. Iniciar Navegador ---
        proxy_manager = ProxyManager()
        proxy_config = proxy_manager.get_proxy_by_host_port(proxy_host, proxy_port)
        if not proxy_config:
            print(f"   -> ⚠️ Proxy no encontrado. Usando un proxy aleatorio.")
            proxy_config = proxy_manager.get_random_proxy()

        user_agent = proxy_manager.get_random_user_agent()

        browser_manager = BrowserManagerProxy(
            chrome_path=CHROME_PATH,
            user_data_dir=USER_DATA_DIR,
            port="",
            proxy=proxy_config,
            user_agent=user_agent
        )
        
        driver = browser_manager.get_configured_driver(URL)
        if not driver:
            return

        print(f"\n   -> ✅ Navegador abierto en: {URL}")
        
        time.sleep(5)
        DesktopUtils.get_and_focus_window(WINDOW_TITLE)
        
        wait = WebDriverWait(driver, 30)

        # --- 4. Ejecutar Login ---
        if not perform_github_login(driver, wait, login_identifier, password):
            raise Exception("El proceso de inicio de sesión falló.")
        
        print("\n   -> 🎉 ¡Login completado! Esperando 20 segundos antes de cerrar sesión.")
        time.sleep(20)

        # --- 5. Ejecutar Logout ---
        print("\n   -> 👋 Iniciando proceso de cierre de sesión...")
        if not _perform_github_logout(driver, wait):
            print("   -> ⚠️ El proceso de cierre de sesión no pudo completarse.")

    except Exception as e:
        print(f"\n🚨 ERROR FATAL durante el flujo de GitHub: {e}")
        traceback.print_exc()
    finally:
        if browser_manager:
            browser_manager.quit_driver()
        print("\n" + "="*60)
        print("✅ SERVICIO FINALIZADO: Flujo de GitHub.")
        print("="*60 + "\n")