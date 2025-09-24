# app/services/github/config_service.py
import time
import os
import traceback
from app.services.reddit.browser_service import BrowserManagerProxy
from app.services.reddit.proxy_service import ProxyManager
from app.services.reddit.desktop_service import DesktopUtils
from app.db.database import get_db_secondary
from app.models.git import Credential as GitCredential

# Reutilizando las funciones y helpers del servicio de login
from .login_service import perform_github_login, _perform_github_logout, _human_click

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By

def run_github_config_flow(credential_id: int):
    """
    Orquesta un flujo de configuración de cuenta:
    1. Inicia sesión.
    2. Navega al perfil del usuario.
    3. Cierra sesión.
    """
    print("\n" + "="*60)
    print(f"🚀 INICIANDO FLUJO: Configuración de cuenta en GitHub para la credencial ID #{credential_id}.")
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
    USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_dev_session_github_config")
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

        # --- 4. Reutilizar Login ---
        if not perform_github_login(driver, wait, login_identifier, password):
            raise Exception("El proceso de inicio de sesión falló.")
        
        print("\n   -> 🎉 ¡Login completado! Procediendo a la configuración del perfil.")
        time.sleep(5)

        # --- 5. Navegar al Perfil ---
        print("\n   -> 👤 Navegando a la página de perfil...")

        # a. Clic en el botón del avatar
        profile_button_locator = (By.CSS_SELECTOR, "button[aria-label='View profile and more']")
        if not _human_click(wait, driver, profile_button_locator, "botón de perfil (avatar)"):
            raise Exception("No se pudo hacer clic en el botón de perfil.")
        
        time.sleep(1)

        # b. Clic en "Your GitHub profile"
        your_profile_locator = (By.XPATH, "//a[@role='menuitem' and .//span[normalize-space()='Your GitHub profile']]")
        if not _human_click(wait, driver, your_profile_locator, "enlace 'Your GitHub profile'"):
            raise Exception("No se pudo hacer clic en el enlace del perfil.")
            
        print("   -> ✅ Navegación al perfil exitosa. Esperando 30 segundos.")
        time.sleep(30)

        # --- 6. Reutilizar Logout ---
        print("\n   -> 👋 Iniciando proceso de cierre de sesión...")
        if not _perform_github_logout(driver, wait):
            print("   -> ⚠️ El proceso de cierre de sesión no pudo completarse.")

    except Exception as e:
        print(f"\n🚨 ERROR FATAL durante el flujo de configuración de GitHub: {e}")
        traceback.print_exc()
    finally:
        if browser_manager:
            browser_manager.quit_driver()
        print("\n" + "="*60)
        print("✅ SERVICIO FINALIZADO: Flujo de configuración de GitHub.")
        print("="*60 + "\n")