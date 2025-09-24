# app/services/github/login_service.py
import time
import os
import traceback
from app.services.reddit.browser_service import BrowserManagerProxy
from app.services.reddit.proxy_service import ProxyManager
from app.services.reddit.desktop_service import DesktopUtils
from app.db.database import get_db_secondary
from app.models.git import Credential as GitCredential

def run_github_login_flow(credential_id: int):
    """
    Orquesta el flujo de inicio de sesión en GitHub para una credencial específica.
    Utiliza el mismo protocolo de navegador que Semrush.
    """
    print("\n" + "="*60)
    print(f"🚀 INICIANDO FLUJO: Login en GitHub para la credencial ID #{credential_id}.")
    print("="*60)

    # --- 1. Obtener credenciales de la base de datos ---
    db = next(get_db_secondary())
    try:
        credential = db.query(GitCredential).filter(GitCredential.id == credential_id).first()
        if not credential:
            print(f"   -> 🚨 ERROR: No se encontró la credencial de GitHub con ID: {credential_id}")
            return
        
        email = credential.email
        password = credential.password
        proxy_host = credential.proxy
        proxy_port = credential.port
        
        print(f"   -> ✅ Credenciales encontradas para el correo: '{email}'")
    finally:
        db.close()

    # --- 2. Configuración del navegador ---
    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    URL = "https://gist.github.com/starred"
    # Usar un directorio de datos de usuario separado para no interferir con otros flujos
    USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_dev_session")
    WINDOW_TITLE = "GitHub"

    browser_manager = None
    driver = None

    try:
        proxy_manager = ProxyManager()
        # Lógica para obtener el proxy (igual que en tus otros servicios)
        proxy_config = proxy_manager.get_proxy_by_host_port(proxy_host, proxy_port)
        if not proxy_config:
            print(f"   -> ⚠️ Proxy {proxy_host}:{proxy_port} no encontrado en proxies.txt o no definido. Usando un proxy aleatorio.")
            proxy_config = proxy_manager.get_random_proxy()

        user_agent = proxy_manager.get_random_user_agent()

        # --- Usar BrowserManagerProxy para consistencia ---
        browser_manager = BrowserManagerProxy(
            chrome_path=CHROME_PATH,
            user_data_dir=USER_DATA_DIR,
            port="",
            proxy=proxy_config,
            user_agent=user_agent
        )
        
        driver = browser_manager.get_configured_driver(URL)
        if not driver:
            print("   -> ❌ No se pudo iniciar el driver de Selenium-Wire.")
            return

        print(f"\n   -> ✅ Navegador abierto en: {URL}")
        print("   -> ⏳ El navegador permanecerá abierto por 60 segundos para verificación.")
        
        # Enfocar la ventana para asegurar que esté visible
        time.sleep(5)
        DesktopUtils.get_and_focus_window(WINDOW_TITLE)

        time.sleep(60)
        
        print("\n   -> ✅ Tarea completada.")

    except Exception as e:
        print(f"\n🚨 ERROR FATAL durante el flujo de login de GitHub: {e}")
        traceback.print_exc()
    finally:
        if browser_manager:
            browser_manager.quit_driver()
        print("\n" + "="*60)
        print("✅ SERVICIO FINALIZADO: Flujo de login de GitHub.")
        print("="*60 + "\n")