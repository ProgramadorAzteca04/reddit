# app/services/semrush/login_service.py
from app.api.v1.endpoints.drive_campaign import (
    build_drive_client,
    get_campaign_phrases_by_city,
)
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
    WebDriverException,
)
from app.services.reddit.browser_service import BrowserManagerProxy
from app.models.semrush_models import Campaign, CredentialSemrush
from selenium.webdriver.support import expected_conditions as EC
from app.services.reddit.proxy_service import ProxyManager
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from typing import List, Optional, Set, Dict, Tuple
from app.db.database import get_db
from sqlalchemy import asc
from app.api.v1.endpoints.drive_campaign import (
    build_drive_client,
    list_accessible_campaign_ids,
    get_campaign_cities,
    get_campaign_phrases_by_city,
)

import traceback
import time
import os


# ───────────────────────────────────────────────────────────────────────────────
# Helpers de resiliencia (no alteran la lógica, solo la endurecen)
# ───────────────────────────────────────────────────────────────────────────────

DEFAULT_STEP_TIMEOUT = 30
LOGOUT_TIMEOUT = 20
DEFAULT_RETRIES = 2


def _sleep(s: float):
    try:
        time.sleep(s)
    except Exception:
        pass


def _wait_clickable(wait: "WebDriverWait", driver: "WebDriver", locator, label: str, timeout: int | None = None):
    """Espera un elemento clickable con timeout opcional. Retorna el elemento o None (no lanza)."""
    try:
        local_wait = wait if timeout is None else WebDriverWait(driver, timeout)
        el = local_wait.until(EC.element_to_be_clickable(locator))
        return el
    except TimeoutException:
        print(f"      -> ⏱️ Timeout esperando '{label}'.")
        return None
    except Exception as e:
        print(f"      -> ⚠️ Error esperando '{label}': {e}")
        return None


def _click_with_fallback(driver: "WebDriver", element, label: str) -> bool:
    """Intenta click normal; si es interceptado u obsoleto, intenta scroll + JS click."""
    if element is None:
        return False
    try:
        element.click()
        return True
    except ElementClickInterceptedException:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
            _sleep(0.2)
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception as e2:
            print(f"      -> ⚠️ Fallback JS click falló en '{label}': {e2}")
            return False
    except StaleElementReferenceException:
        print(f"      -> ⚠️ Elemento obsoleto al hacer click en '{label}'.")
        return False
    except WebDriverException as e:
        print(f"      -> ⚠️ WebDriverException al hacer click en '{label}': {e}")
        return False


def _wait_and_click(wait: "WebDriverWait", driver: "WebDriver", locator, label: str,
                    retries: int = DEFAULT_RETRIES, timeout: int | None = None) -> bool:
    """Espera y hace click con reintentos y fallback. No lanza excepciones."""
    for attempt in range(1, retries + 1):
        el = _wait_clickable(wait, driver, locator, label, timeout=timeout)
        if _click_with_fallback(driver, el, label):
            print(f"      -> ✅ Click en '{label}' (intento {attempt}).")
            return True
        print(f"      -> 🔁 Reintentando click en '{label}' (intento {attempt}/{retries})...")
        _sleep(1.0)
    print(f"      -> ❌ No se pudo hacer click en '{label}' tras {retries} intentos.")
    return False


def _send_text_to_input(wait: "WebDriverWait", driver: "WebDriver", locator, text: str,
                        label: str, clear_first: bool = True, timeout: int | None = None) -> bool:
    """Foco, limpiar (si aplica) y send_keys; silencioso en errores."""
    el = _wait_clickable(wait, driver, locator, label, timeout=timeout)
    if el is None:
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        _sleep(0.2)
    except Exception:
        pass
    try:
        el.click()
        _sleep(0.2)
        if clear_first:
            try:
                el.clear()
            except Exception:
                el.send_keys(Keys.CONTROL, 'a')
                _sleep(0.1)
                el.send_keys(Keys.DELETE)
                _sleep(0.1)
        if text:
            el.send_keys(text)
        print(f"      -> ✅ Texto enviado a '{label}'.")
        return True
    except Exception as e:
        print(f"      -> ⚠️ No se pudo escribir en '{label}': {e}")
        return False


def _wait_visible(wait: "WebDriverWait", driver: "WebDriver", locator, label: str, timeout: int | None = None) -> bool:
    """Espera visibilidad; retorna True/False sin lanzar excepción."""
    try:
        local_wait = wait if timeout is None else WebDriverWait(driver, timeout)
        local_wait.until(EC.visibility_of_element_located(locator))
        print(f"      -> 👀 Visible: '{label}'.")
        return True
    except TimeoutException:
        print(f"      -> ⏱️ Timeout de visibilidad en '{label}'.")
        return False
    except Exception as e:
        print(f"      -> ⚠️ Error de visibilidad en '{label}': {e}")
        return False


def _press_first_suggestion(el, label: str) -> bool:
    """Flecha abajo + Enter, con esperas suaves."""
    try:
        el.send_keys(Keys.ARROW_DOWN)
        _sleep(0.4)
        el.send_keys(Keys.ENTER)
        print(f"      -> ✅ Primera sugerencia confirmada en '{label}'.")
        return True
    except Exception as e:
        print(f"      -> ⚠️ No se pudo seleccionar sugerencia en '{label}': {e}")
        return False


def _best_effort_logout(driver: "WebDriver", wait: "WebDriverWait"):
    """Intenta cerrar sesión sin romper si falla."""
    try:
        _perform_logout(driver, wait)
    except Exception as e:
        print(f"   -> ⚠️ Logout best-effort falló: {e}")


# ───────────────────────────────────────────────────────────────────────────────
# Logout robusto (prioriza los selectores exactos proporcionados por el usuario)
# ───────────────────────────────────────────────────────────────────────────────

def _open_home(driver: WebDriver):
    """Asegura que el header esté presente antes de intentar el logout."""
    try:
        driver.get("https://es.semrush.com/")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
    except Exception:
        pass


def _is_logged_out(driver: WebDriver) -> bool:
    """
    Heurística rápida: presencia de botones/links 'Log in'/'Iniciar sesión'
    o ausencia clara de avatar de usuario.
    """
    try:
        login_candidates = [
            (By.CSS_SELECTOR, '[data-test="login-button"]'),
            (By.XPATH, "//a[contains(., 'Iniciar sesión') or contains(., 'Log in')]"),
            (By.XPATH, "//button[contains(., 'Iniciar sesión') or contains(., 'Log in')]"),
        ]
        for by, sel in login_candidates:
            if driver.find_elements(by, sel):
                return True

        avatar_candidates = [
            (By.CSS_SELECTOR, 'button[data-test="header-menu__user"]'),
            (By.CSS_SELECTOR, '[data-test="header-user-menu"]'),
            (By.CSS_SELECTOR, 'button[aria-label*="User" i]'),
            (By.CSS_SELECTOR, 'button[aria-label*="Cuenta" i]'),
            (By.CSS_SELECTOR, 'img[alt*="avatar" i]'),
        ]
        has_avatar = any(driver.find_elements(by, sel) for by, sel in avatar_candidates)
        return not has_avatar
    except Exception:
        return False


def _click(driver: WebDriver, wait: WebDriverWait, locator: tuple, label: str, timeout: int = 8) -> bool:
    """Click robusto con fallback a JS click y pequeño scroll."""
    end = time.time() + timeout
    last_err = None
    while time.time() < end:
        try:
            el = WebDriverWait(driver, 3).until(EC.element_to_be_clickable(locator))
            try:
                el.click()
            except Exception:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                _sleep(0.1)
                driver.execute_script("arguments[0].click();", el)
            return True
        except Exception as e:
            last_err = e
            _sleep(0.25)
    if last_err:
        print(f"      -> ⚠️ No se pudo hacer click en {label}: {last_err}")
    return False


def _perform_logout(driver: WebDriver, wait: WebDriverWait) -> bool:
    """
    Cierra sesión en Semrush de forma robusta y en el orden indicado:
      1) Click en botón de usuario (PRIORIDAD: selector exacto entregado por el usuario).
      2) Click en enlace de logout (PRIORIDAD: selector exacto entregado por el usuario).
      3) Confirmar estado de logout.
    Fallbacks: reintentar desde home, endpoints /logout y limpieza de cookies.
    """
    try:
        # 1) Idempotencia
        if _is_logged_out(driver):
            print("   -> 🔓 Ya estás deslogueado (detectado).")
            return True

        # Asegurar header visible
        _open_home(driver)

        # 2) Abrir menú de usuario (avatar) — PRIORIDAD selector exacto
        user_menu_primary = (
            By.CSS_SELECTOR,
            'button.srf-header__menu-link.srf-header__has-submenu-link.srf-header__menu-link--user[data-test="header-menu__user"]',
        )
        if not _click(driver, wait, user_menu_primary, "menú de usuario (principal)", timeout=10):
            # Alternos razonables por si cambian clases/atributos
            alternates = [
                (By.CSS_SELECTOR, 'button[data-test="header-menu__user"]'),
                (By.CSS_SELECTOR, '[data-test="header-user-menu"]'),
                (By.CSS_SELECTOR, 'button[aria-haspopup="true"][aria-label*="perfil" i]'),
            ]
            opened = False
            for alt in alternates:
                if _click(driver, wait, alt, "menú de usuario (alterno)", timeout=6):
                    opened = True
                    break
            if not opened:
                print("   -> ⚠️ No se pudo abrir el menú de usuario.")
                try:
                    btn = driver.find_element(*user_menu_primary)
                    btn.send_keys("\n")
                except Exception:
                    pass

        _sleep(0.4)

        # 3) Click en "Cerrar sesión" — PRIORIDAD selector exacto
        logout_primary = (
            By.CSS_SELECTOR,
            'a.srf-header__submenu-link[data-test="header-menu__user-logout"][href="/sso/logout"]',
        )
        if not _click(driver, wait, logout_primary, "Cerrar sesión (principal)", timeout=10):
            logout_alternates = [
                (By.CSS_SELECTOR, 'a[data-test="header-menu__user-logout"]'),
                (By.XPATH, "//a[contains(@href,'/sso/logout')]"),
                (By.XPATH, "//a[contains(., 'Cerrar sesión') or contains(., 'Sign out') or contains(., 'Log out')]"),
                (By.CSS_SELECTOR, '[data-test="header-sign-out"], a[data-test="header-sign-out"]'),
            ]
            clicked = False
            for alt in logout_alternates:
                if _click(driver, wait, alt, "Cerrar sesión (alterno)", timeout=6):
                    clicked = True
                    break
            if not clicked:
                # Fallback: volver a home y reintentar una vez
                print("   -> ⚠️ Reintentando logout desde home…")
                _open_home(driver)
                _sleep(0.5)
                if _click(driver, wait, user_menu_primary, "menú de usuario (reintento)", timeout=6):
                    if not _click(driver, wait, logout_primary, "Cerrar sesión (reintento)", timeout=6):
                        for alt in logout_alternates:
                            if _click(driver, wait, alt, "Cerrar sesión (reintento alterno)", timeout=5):
                                break

        _sleep(1.0)

        # 4) Confirmar estado de deslogueo
        if _is_logged_out(driver):
            print("   -> ✅ Logout exitoso.")
            return True

        # Endpoints directos
        for url in [
            "https://es.semrush.com/sso/logout",
            "https://www.semrush.com/sso/logout",
            "https://es.semrush.com/logout",
            "https://www.semrush.com/logout",
            "https://es.semrush.com/auth/logout",
            "https://www.semrush.com/auth/logout",
        ]:
            try:
                driver.get(url)
                WebDriverWait(driver, 6).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
                _sleep(0.6)
                if _is_logged_out(driver):
                    print(f"   -> ✅ Logout vía endpoint: {url}")
                    return True
            except Exception:
                pass

        # Limpieza de cookies como último recurso
        try:
            driver.delete_all_cookies()
            _open_home(driver)
            if _is_logged_out(driver):
                print("   -> ✅ Logout por limpieza de cookies.")
                return True
        except WebDriverException:
            pass

        print("   -> ❌ No se pudo confirmar logout. Continuo (best-effort).")
        return False

    except Exception as e:
        print(f"   -> 🚨 Error en _perform_logout: {e}")
        return False
    
def _persist_proxy_choice(credential_id: int, host: str, port: str) -> bool:
    """
    Actualiza en BD el proxy y el port de la credencial indicada.
    Retorna True si se guardó correctamente.
    """
    db = next(get_db())
    try:
        cred = db.query(CredentialSemrush).filter(CredentialSemrush.id == credential_id).first()
        if not cred:
            print(f"      -> ❌ No se encontró la credencial #{credential_id} para actualizar proxy.")
            return False
        cred.proxy = host or ""
        cred.port = str(port or "")
        db.commit()
        print(f"      -> 💾 Proxy actualizado en BD para cred #{credential_id}: {host}:{port}")
        return True
    except Exception as e:
        print(f"      -> 🚨 Error actualizando proxy en BD: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            db.close()
        except Exception:
            pass
# ───────────────────────────────────────────────────────────────────────────────
# Flujo de LOGIN (misma lógica, endurecida)
# ───────────────────────────────────────────────────────────────────────────────

def run_semrush_login_flow(credential_id: int):
    """
    Orquesta el flujo de inicio de sesión en Semrush para una credencial específica.
    """
    print("\n" + "="*60)
    print(f"🚀 INICIANDO FLUJO: Login en Semrush para la credencial ID #{credential_id}.")
    print("="*60)

    # 1. Obtener credenciales
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

     # 2. Configuración de navegador
    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    URL = "https://es.semrush.com/login/"
    USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_dev_session")

    browser_manager = None
    driver = None

    try:
        proxy_manager = ProxyManager()
        proxy_config = None  # dict de proxy para BrowserManagerProxy

        # --- Nueva lógica de elección y persistencia de proxy ---
        if proxy_host and proxy_port:
            print(f"   -> Buscando credenciales para el proxy {proxy_host}:{proxy_port} en 'proxies.txt'...")
            proxy_config = proxy_manager.get_proxy_by_host_port(proxy_host, proxy_port)
            if proxy_config:
                print("      -> ✅ Credenciales del proxy encontradas.")
            else:
                print(f"      -> ❌ Proxy {proxy_host}:{proxy_port} no existe en proxies.txt.")
                print("      -> 🔄 Tomando un proxy aleatorio y actualizando la BD...")
                random_proxy = proxy_manager.get_random_proxy()
                if random_proxy:
                    # Persistimos el nuevo proxy en BD
                    _persist_proxy_choice(
                        credential_id,
                        random_proxy.get("host", ""),
                        str(random_proxy.get("port", ""))
                    )
                    # Actualizamos variables locales para logs y coherencia
                    proxy_host = random_proxy.get("host")
                    proxy_port = str(random_proxy.get("port"))
                    proxy_config = random_proxy
                    print(f"      -> ✅ Proxy aleatorio asignado: {proxy_host}:{proxy_port}")
                else:
                    print("      -> ⚠️ No hay proxies disponibles en la lista. Se continuará SIN proxy.")
        else:
            print("   -> ⚠️ No hay proxy definido en la BD para esta credencial.")
            print("      -> 🔄 Tomando un proxy aleatorio y actualizando la BD...")
            random_proxy = proxy_manager.get_random_proxy()
            if random_proxy:
                _persist_proxy_choice(
                    credential_id,
                    random_proxy.get("host", ""),
                    str(random_proxy.get("port", ""))
                )
                proxy_host = random_proxy.get("host")
                proxy_port = str(random_proxy.get("port"))
                proxy_config = random_proxy
                print(f"      -> ✅ Proxy aleatorio asignado: {proxy_host}:{proxy_port}")
            else:
                print("      -> ⚠️ No hay proxies disponibles en la lista. Se continuará SIN proxy.")

        browser_manager = BrowserManagerProxy(
            chrome_path=CHROME_PATH, 
            user_data_dir=USER_DATA_DIR, 
            port="",
            proxy=proxy_config
        )
        
        driver = browser_manager.get_configured_driver(URL)
        if not driver:
            print("   -> ❌ No se pudo iniciar el driver de Selenium-Wire.")
            return

        print("\n   -> Esperando 20 segundos para que la página de login cargue...")
        _sleep(20)
        wait = WebDriverWait(driver, DEFAULT_STEP_TIMEOUT)

        # Email
        if not _wait_and_click(wait, driver, (By.CSS_SELECTOR, 'input[name="email"]'), "input email"):
            return
        _sleep(0.3)
        _send_text_to_input(wait, driver, (By.CSS_SELECTOR, 'input[name="email"]'), email, "input email", clear_first=False)

        # Password
        if not _wait_and_click(wait, driver, (By.CSS_SELECTOR, 'input[name="password"]'), "input password"):
            return
        _sleep(0.3)
        _send_text_to_input(wait, driver, (By.CSS_SELECTOR, 'input[name="password"]'), password, "input password", clear_first=False)

        # Botón Iniciar sesión
        if not _wait_and_click(wait, driver, (By.XPATH, '//button[.//span[text()="Iniciar sesión"]]'), "botón Iniciar sesión"):
            return

        # Confirmación de login
        try:
            wait.until(EC.url_contains("projects"))
            print("\n   -> 🎉 ¡Login exitoso! La sesión permanecerá abierta por 30 segundos.")
        except TimeoutException:
            print("\n   -> 🚨 No se detectó redirección a 'projects' tras login.")
            return

        _sleep(30)
        _best_effort_logout(driver, wait)

    except Exception as e:
        print(f"\n🚨 ERROR FATAL durante el flujo de login de Semrush: {e}")
        traceback.print_exc()
    finally:
        try:
            if driver:
                # Logout FINAL como último paso antes de cerrar
                print("🔐 Intentando logout FINAL (último paso) antes de cerrar el navegador…")
                try:
                    _open_home(driver)
                except Exception:
                    pass
                try:
                    _perform_logout(driver, WebDriverWait(driver, 20))
                except Exception as e:
                    print(f"⚠️ Error intentando logout final: {e}")
        finally:
            if browser_manager:
                browser_manager.quit_driver()
        print("\n" + "="*60)
        print("✅ SERVICIO FINALIZADO: Flujo de login de Semrush.")
        print("="*60 + "\n")


# ───────────────────────────────────────────────────────────────────────────────
# Flujo de CONFIGURACIÓN DE CUENTA (misma lógica, endurecida)
# ───────────────────────────────────────────────────────────────────────────────

def run_semrush_config_account_flow(id_campaign: int, city: str, cycle_number: Optional[int] = None):
    """
    Busca una cuenta de Semrush sin campaña, realiza el login, configura el proyecto
    con la web de la campaña y, solo si tiene éxito, actualiza la base de datos.
    """
    print("\n" + "="*60)
    cycle_info = f" (Ciclo Maestro #{cycle_number})" if cycle_number is not None else ""
    print(f"🚀 INICIANDO FLUJO{cycle_info}: Configuración de cuenta para Campaña ID #{id_campaign} en {city}.")
    print("="*60)


    # Paso 1: Buscar credencial y campaña
    db = next(get_db())
    try:
        print("   -> 🔍 Buscando una credencial disponible en la base de datos...")
        credential_to_use = db.query(CredentialSemrush).filter(CredentialSemrush.id_campaigns == None).first()
        if not credential_to_use:
            print("   -> ❌ No se encontró ninguna credencial con 'id_campaigns' vacío.")
            return
        print(f"   -> ✅ Credencial encontrada (ID: {credential_to_use.id}), email: '{credential_to_use.email}'.")

        print(f"   -> 🔍 Buscando la campaña con ID: {id_campaign}...")
        campaign = db.query(Campaign).filter(Campaign.id == id_campaign).first()
        if not campaign:
            print(f"   -> ❌ No se encontró ninguna campaña con el ID: {id_campaign}")
            return
        if not campaign.web:
            print(f"   -> ❌ La campaña con ID {id_campaign} no tiene una URL web definida.")
            return
        print(f"   -> ✅ Campaña encontrada. Web a configurar: '{campaign.web}'")
        
        web_url = campaign.web
        email = credential_to_use.email
        password = credential_to_use.password
        proxy_host = credential_to_use.proxy
        proxy_port = credential_to_use.port

    finally:
        db.close()

    # Paso 2: Configuración del navegador y login
    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    URL = "https://es.semrush.com/login/"
    USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_dev_session")
    browser_manager = None
    driver = None
    
    try:
        proxy_manager = ProxyManager()
        proxy_config = None

        # --- Nueva lógica de elección y persistencia de proxy (igual que en login) ---
        if proxy_host and proxy_port:
            print(f"   -> Buscando proxy {proxy_host}:{proxy_port} en 'proxies.txt'...")
            proxy_config = proxy_manager.get_proxy_by_host_port(proxy_host, proxy_port)
            if proxy_config:
                print("      -> ✅ Proxy válido encontrado.")
            else:
                print(f"      -> ❌ Proxy {proxy_host}:{proxy_port} no existe en 'proxies.txt'.")
                print("      -> 🔄 Tomando un proxy aleatorio y actualizando la BD...")
                random_proxy = proxy_manager.get_random_proxy()
                if random_proxy:
                    # Persistimos el nuevo proxy en BD para esta credencial
                    _persist_proxy_choice(
                        credential_to_use.id,
                        random_proxy.get("host", ""),
                        str(random_proxy.get("port", ""))
                    )
                    # Actualizamos variables locales y configuración del navegador
                    proxy_host = random_proxy.get("host")
                    proxy_port = str(random_proxy.get("port"))
                    proxy_config = random_proxy
                    print(f"      -> ✅ Proxy aleatorio asignado: {proxy_host}:{proxy_port}")
                else:
                    print("      -> ⚠️ No hay proxies disponibles. Se continuará SIN proxy.")
        else:
            print("   -> ⚠️ La credencial no tiene proxy/port en BD.")
            print("      -> 🔄 Tomando un proxy aleatorio y actualizando la BD...")
            random_proxy = proxy_manager.get_random_proxy()
            if random_proxy:
                _persist_proxy_choice(
                    credential_to_use.id,
                    random_proxy.get("host", ""),
                    str(random_proxy.get("port", ""))
                )
                proxy_host = random_proxy.get("host")
                proxy_port = str(random_proxy.get("port"))
                proxy_config = random_proxy
                print(f"      -> ✅ Proxy aleatorio asignado: {proxy_host}:{proxy_port}")
            else:
                print("      -> ⚠️ No hay proxies disponibles. Se continuará SIN proxy.")
        
        browser_manager = BrowserManagerProxy(
            chrome_path=CHROME_PATH, user_data_dir=USER_DATA_DIR, port="", proxy=proxy_config
        )
        driver = browser_manager.get_configured_driver(URL)
        if not driver:
            print("   -> ❌ No se pudo iniciar el driver de Selenium-Wire.")
            return

        print("\n   -> Esperando para que la página de login cargue...")
        _sleep(20)
        wait = WebDriverWait(driver, DEFAULT_STEP_TIMEOUT)

        # Llenado del formulario de login
        if not _send_text_to_input(wait, driver, (By.CSS_SELECTOR, 'input[name="email"]'), email, "input email", clear_first=False):
            _best_effort_logout(driver, wait); return
        if not _send_text_to_input(wait, driver, (By.CSS_SELECTOR, 'input[name="password"]'), password, "input password", clear_first=False):
            _best_effort_logout(driver, wait); return
        if not _wait_and_click(wait, driver, (By.XPATH, '//button[.//span[text()="Iniciar sesión"]]'), "botón Iniciar sesión"):
            _best_effort_logout(driver, wait); return

        # Paso 3: Configurar el proyecto con la web
        print("\n   -> 🌐 Esperando a la página de creación de proyecto...")
        web_input_sel = (By.CSS_SELECTOR, 'input[data-ui-name="Input.Value"][placeholder="Indica el nombre de tu sitio web"]')
        if not _wait_visible(wait, driver, web_input_sel, "input web del proyecto"):
            _best_effort_logout(driver, wait); return
        
        print(f"   -> ✍️  Introduciendo la web '{web_url}' en el campo del proyecto...")
        if not _send_text_to_input(wait, driver, web_input_sel, web_url, "input web del proyecto", clear_first=False):
            _best_effort_logout(driver, wait); return
        _sleep(2)
        
        # Paso 3a: Botón "Empieza ahora"
        print("\n   -> 🛠️  Buscando el botón 'Empieza ahora'...")
        if not _wait_and_click(wait, driver, (By.XPATH, '//button[.//span[text()="Empieza ahora"]]'), "botón Empieza ahora"):
            _best_effort_logout(driver, wait); return

        _sleep(15)

        # Paso 3b: Bloque de 'Supervisa el posicionamiento de la palabra clave.'
        print("\n   -> 🔍 Esperando el bloque de 'Supervisa el posicionamiento...'")
        pos_block = (By.XPATH, '//div[@data-path="position_tracking"]//span[text()="Supervisa el posicionamiento de la palabra clave."]')
        if not _wait_visible(wait, driver, pos_block, "bloque 'Supervisa el posicionamiento...'"):
            _best_effort_logout(driver, wait); return
        print("   -> ✅ Bloque de posicionamiento encontrado.")

        # Paso 3c: Botón "Configurar" dentro de ese bloque
        print("\n   -> 🛠️  Buscando el botón 'Configurar' dentro del bloque...")
        if not _wait_and_click(
            wait, driver,
            (By.XPATH, '//div[@data-path="position_tracking"]//button[.//div[text()="Configurar"]]'),
            "botón Configurar (position_tracking)"
        ):
            _best_effort_logout(driver, wait); return
        _sleep(10)  # Espera para que cargue el formulario de configuración

        # Paso 3d: Escribir la ciudad en el campo de ubicación y seleccionar la primera sugerencia
        print("\n   -> 🗺️  Rellenando la ubicación (city) y seleccionando la primera sugerencia...")
        loc_input = (By.XPATH, '//input[@data-ui-name="Input.Value" and @placeholder="Introduce país, ciudad, calle o código postal"]')
        el_loc = _wait_clickable(wait, driver, loc_input, "input ubicación")
        if el_loc is None:
            _best_effort_logout(driver, wait); return

        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el_loc)
        except Exception:
            pass

        try:
            el_loc.click(); _sleep(1)
            try:
                el_loc.clear()
            except Exception:
                el_loc.send_keys(Keys.CONTROL, 'a'); _sleep(0.1); el_loc.send_keys(Keys.DELETE); _sleep(0.1)
            el_loc.send_keys(city)
            _sleep(5)  # espera para que carguen sugerencias
            _press_first_suggestion(el_loc, "input ubicación")
        except Exception as e:
            print(f"      -> ⚠️ No se pudo completar la ubicación: {e}")
            _best_effort_logout(driver, wait); return
        _sleep(5)

        # Paso 3e: Rellenar el nombre del negocio usando el name de la campaña
        print("\n   -> 🏷️  Rellenando el nombre del negocio desde public.campaigns.name...")
        biz_input = (By.XPATH, '//input[@data-ui-name="Input.Value" and @placeholder="Incluye el nombre del negocio completo"]')
        try:
            campaign_name = campaign.name if hasattr(campaign, "name") and campaign.name else str(id_campaign)
        except Exception:
            campaign_name = str(id_campaign)
        if not _send_text_to_input(wait, driver, biz_input, campaign_name, "input nombre negocio", clear_first=True):
            _best_effort_logout(driver, wait); return
        print(f"   -> ✅ Nombre del negocio establecido: '{campaign_name}'.")

        # Paso 3f: Esperar 5s y continuar a "Palabras clave"
        print("\n   -> ⏳ Esperando 5 segundos antes de continuar...")
        _sleep(5)

        print("   -> 🡆 Buscando y haciendo clic en 'Continuar a Palabras clave'...")
        if not _wait_and_click(wait, driver, (By.ID, "ptr-wizard-next-step-button"), "Continuar a Palabras clave (ID)"):
            if not _wait_and_click(wait, driver, (By.XPATH, '//button[.//span[text()="Continuar a Palabras clave"]]'),
                                   "Continuar a Palabras clave (texto)"):
                _best_effort_logout(driver, wait); return
        print("   -> ✅ Avanzaste a 'Palabras clave'.")

        # Paso 3g: Obtener frases desde Google Drive para esta campaña/ciudad
        print("\n   -> 🔎 Obteniendo frases de Drive para la ciudad y campaña dadas...")
        phrases: list[str] = []
        try:
            drive = build_drive_client(credentials_json_path="credentials.json", token_json_path="token.json")
            phrases = get_campaign_phrases_by_city(drive, id_campaign, city) or []
            # Limpieza rápida: quitar vacíos y duplicados, conservar orden
            seen = set()
            phrases = [p.strip() for p in phrases if p and p.strip() and not (p.strip() in seen or seen.add(p.strip()))]
            print(f"   -> ✅ Frases obtenidas: {len(phrases)}")
        except FileNotFoundError as e:
            print(f"   -> 🚨 No se encontró el archivo de credenciales/tokens de Google: {e}")
        except ImportError as e:
            print(f"   -> 🚨 Dependencia faltante (openpyxl). Instala con: pip install openpyxl. Detalle: {e}")
        except Exception as e:
            print(f"   -> 🚨 Error al obtener frases desde Drive: {e}")

        if not phrases:
            print("   -> ⚠️ No se encontraron frases para esta ciudad/campaña.")

        # Paso 3h: Pegar frases (separadas por comas) en el textarea de "Palabras clave"
        print("\n   -> 📝 Pegando frases en el textarea de 'Palabras clave'...")
        _sleep(3)

        def _sanitize_phrase(s):
            s = str(s).strip()
            if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
                s = s[1:-1].strip()
            return s

        phrases_csv = ", ".join([_sanitize_phrase(p) for p in (phrases or []) if str(p).strip()])

        if phrases_csv:
            ta_locator = (By.XPATH, '//textarea[@data-ui-name="Textarea" and contains(@placeholder, "keyword1")]')
            if _wait_visible(wait, driver, ta_locator, "textarea Palabras clave"):
                ta = _wait_clickable(wait, driver, ta_locator, "textarea Palabras clave")
                if ta:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", ta)
                        _sleep(0.2)
                    except Exception:
                        pass
                    try:
                        ta.click(); _sleep(0.2)
                        try:
                            ta.clear()
                        except Exception:
                            ta.send_keys(Keys.CONTROL, 'a'); _sleep(0.1)
                            ta.send_keys(Keys.DELETE); _sleep(0.1)
                        ta.send_keys(phrases_csv)
                        print("   -> ✅ Frases pegadas en el textarea de 'Palabras clave'.")
                    except Exception as e:
                        print(f"   -> ⚠️ No se pudieron pegar las frases: {e}")
        else:
            print("   -> ⚠️ No hay frases para pegar (lista vacía). Se continúa sin pegar.")

        # Paso 3i: Clic en "Iniciar rastreo"
        print("\n   -> ▶️ Iniciando rastreo (clic en 'Iniciar rastreo')...")
        _sleep(2)
        if not _wait_and_click(wait, driver, (By.ID, "ptr-wizard-apply-changes-button"), "Iniciar rastreo (ID)"):
            if not _wait_and_click(wait, driver, (By.XPATH, '//button[.//span[text()="Iniciar rastreo"]]'),
                                   "Iniciar rastreo (texto)"):
                _best_effort_logout(driver, wait); return
        _sleep(5)

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

        print("\n   -> 🎉 ¡Configuración completada!")
        _sleep(240)
        _best_effort_logout(driver, wait)

    except Exception as e:
        print(f"\n🚨 ERROR FATAL durante el flujo de configuración: {e}")
        traceback.print_exc()
        print("   -> ❌ Como el proceso falló, NO se ha realizado ninguna modificación en la base de datos.")
    finally:
        try:
            if driver:
                # Logout FINAL como último paso antes de cerrar
                print("🔐 Intentando logout FINAL (último paso) antes de cerrar el navegador…")
                try:
                    _open_home(driver)
                except Exception:
                    pass
                try:
                    _perform_logout(driver, WebDriverWait(driver, 20))
                except Exception as e:
                    print(f"⚠️ Error intentando logout final: {e}")
        finally:
            if browser_manager:
                browser_manager.quit_driver()
        print("\n" + "="*60)
        print("✅ SERVICIO FINALIZADO: Flujo de configuración de cuenta Semrush.")
        print("="*60 + "\n")


def _get_free_credential_ids() -> Set[int]:
    db = next(get_db())
    try:
        rows = db.query(CredentialSemrush.id).filter(CredentialSemrush.id_campaigns == None).all()
        return {r[0] for r in rows}
    finally:
        db.close()

def _pick_newly_assigned_credential_id(
    campaign_id: int,
    pre_free_ids: Set[int]
) -> Optional[int]:
    """
    Identifica cuál credencial (de las que estaban libres antes) quedó asignada
    a la campaña tras una iteración de configuración.
    """
    db = next(get_db())
    try:
        rows = (
            db.query(CredentialSemrush.id)
            .filter(
                CredentialSemrush.id_campaigns == campaign_id,
                CredentialSemrush.id.in_(pre_free_ids)
            )
            .all()
        )
        ids = [r[0] for r in rows]
        if len(ids) == 1:
            return ids[0]
        return None
    finally:
        db.close()

def _update_credential_note(credential_id: int, note_text: str) -> bool:
    """
    Actualiza el campo 'note' de la credencial indicada.
    """
    db = next(get_db())
    try:
        cred = db.query(CredentialSemrush).filter(CredentialSemrush.id == credential_id).first()
        if not cred:
            print(f"   -> ❌ No se encontró la credencial #{credential_id} para actualizar note.")
            return False
        cred.note = note_text or ""
        db.commit()
        print(f"   -> 📝 note actualizado en BD para cred #{credential_id}: '{note_text}'")
        return True
    except Exception as e:
        print(f"   -> 🚨 Error actualizando note en BD: {e}")
        try: db.rollback()
        except Exception: pass
        return False
    finally:
        try: db.close()
        except Exception: pass

def _campaigns_in_db(campaign_ids: List[int]) -> List[int]:
    """
    Devuelve los campaign_ids (de la lista recibida) que existen en la tabla Campaign,
    ordenados ascendentemente.
    """
    if not campaign_ids:
        return []
    db = next(get_db())
    try:
        rows = (
            db.query(Campaign.id)
            .filter(Campaign.id.in_(campaign_ids))
            .order_by(asc(Campaign.id))
            .all()
        )
        return [r[0] for r in rows]
    finally:
        db.close()

def run_semrush_cycle_config_accounts(
    delay_seconds: float = 8.0,
    max_total_iterations: Optional[int] = None
) -> None:
    """
    Ciclo maestro:
    - Mientras haya credenciales libres (id_campaigns NULL),
      recorre campañas accesibles en Drive (orden ascendente) y sus ciudades (ordenadas).
    - Para cada (campaña, ciudad) con frases disponibles:
        * Llama a run_semrush_config_account_flow(campaign_id, city)
        * Detecta la credencial asignada y actualiza 'note' = ciudad usada.
    - Se detiene cuando:
        * No quedan credenciales libres, o
        * Se agotan todas las combinaciones útiles (campaña con al menos una ciudad con frases).
    - delay_seconds: espera entre iteraciones para estabilidad de UI.
    - max_total_iterations: tope de seguridad (None = sin tope).
    """
    print("\n" + "="*72)
    print("🧭 INICIANDO CICLO MAESTRO: configurar cuentas por campaña → ciudades")
    print("="*72)

    # 0) Estado inicial: hay credenciales libres?
    free_ids = _get_free_credential_ids()
    if not free_ids:
        print("   -> ⚠️ No hay credenciales libres (id_campaigns NULL). Nada por hacer.")
        print("="*72 + "\n")
        return

    # 1) Cliente Drive y campañas accesibles (por carpeta mapeada y permisos)
    try:
        drive = build_drive_client(credentials_json_path="credentials.json", token_json_path="token.json")
    except Exception as e:
        print(f"   -> 🚨 No se pudo crear cliente de Drive: {e}")
        print("   -> ❌ Abortando ciclo maestro.")
        print("="*72 + "\n")
        return

    try:
        accessible = list_accessible_campaign_ids(drive)  # por mapa y acceso
    except Exception as e:
        print(f"   -> 🚨 No se pudieron listar campañas accesibles en Drive: {e}")
        accessible = []

    # Filtra a campañas que existen en tu tabla Campaign y ordena asc
    campaign_queue = _campaigns_in_db(accessible)
    if not campaign_queue:
        print("   -> ⚠️ No hay campañas accesibles (Drive) que existan en BD. Nada por hacer.")
        print("="*72 + "\n")
        return

    iter_count = 0

    # 2) Bucle principal
    for campaign_id in campaign_queue:
        # Re-evaluar credenciales libres al inicio de cada campaña
        free_ids = _get_free_credential_ids()
        if not free_ids:
            print("   -> ✅ No quedan credenciales libres. Ciclo maestro finalizado.")
            break

        # Ciudades de la campaña (ordenadas)
        try:
            cities = sorted(get_campaign_cities(drive, campaign_id) or [])
        except Exception as e:
            print(f"   -> ⚠️ No se pudieron obtener ciudades para campaña {campaign_id}: {e}")
            continue

        if not cities:
            print(f"   -> ⚠️ Campaña {campaign_id} no tiene ciudades disponibles. Se omite.")
            continue

        print(f"\n— Campaña #{campaign_id}: {len(cities)} ciudades candidatas —")

        for city in cities:
            # Tope de seguridad
            if max_total_iterations is not None and iter_count >= max_total_iterations:
                print("   -> ⛔ Tope de iteraciones alcanzado. Salida segura.")
                print("="*72 + "\n")
                return

            # ¿Aún hay credenciales libres?
            free_ids = _get_free_credential_ids()
            if not free_ids:
                print("   -> ✅ No quedan credenciales libres. Ciclo maestro finalizado.")
                print("="*72 + "\n")
                return

            # ¿Hay frases para esta ciudad?
            try:
                phrases = get_campaign_phrases_by_city(drive, campaign_id, city) or []
                # limpieza ligera similar a tu uso
                seen = set()
                phrases = [p.strip() for p in phrases if p and p.strip() and not (p.strip() in seen or seen.add(p.strip()))]
            except Exception as e:
                print(f"   -> ⚠️ Error obteniendo frases para {city} (campaña {campaign_id}): {e}")
                continue

            if not phrases:
                print(f"   -> (sin frases) {city} @ campaña {campaign_id} → se omite.")
                continue

            iter_count += 1
            print(f"\n▶️  Iniciando Ciclo de Configuración #{iter_count}: Campaña {campaign_id} · Ciudad '{city}' · {len(phrases)} frases")
            pre_free = set(free_ids)  # snapshot para detectar cuál credencial se asigna

            # Ejecuta TU flujo existente (no se modifica su código)
            try:
                run_semrush_config_account_flow(campaign_id, city, cycle_number=iter_count)
            except Exception as e:
                print(f"   -> 🚨 Error en run_semrush_config_account_flow({campaign_id}, {city}): {e}")
                # NO se detiene el ciclo; intenta siguiente ciudad
                continue

            # Detecta cuál credencial se asignó en esta iteración y actualiza 'note' = ciudad
            assigned_id = _pick_newly_assigned_credential_id(campaign_id, pre_free)
            if assigned_id:
                _update_credential_note(assigned_id, city)
            else:
                print("   -> ⚠️ No se pudo identificar la credencial asignada para actualizar 'note'.")

            if delay_seconds and delay_seconds > 0:
                _sleep(delay_seconds)

    print("\n" + "="*72)
    print("✅ CICLO MAESTRO FINALIZADO: sin credenciales libres o sin más combinaciones útiles.")
    print("="*72 + "\n")