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
from sqlalchemy import asc, func
from app.api.v1.endpoints.drive_campaign import (
    build_drive_client,
    list_accessible_campaign_ids,
    get_campaign_cities,
    get_campaign_phrases_by_city,
)

import traceback
import time
import os
import re
import random


# ───────────────────────────────────────────────────────────────────────────────
# Helpers de resiliencia (sin cambios)
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
    
def _check_for_location_error(driver: WebDriver) -> bool:
    """Verifica si el tooltip de error 'Escoge la ubicación en la lista' está visible."""
    try:
        error_locator = (By.XPATH, "//div[contains(@class, '___STooltip_') and contains(text(), 'Escoge la ubicación en la lista')]")
        WebDriverWait(driver, 3).until(EC.visibility_of_element_located(error_locator))
        print("      -> ❌ ERROR DETECTADO: La ubicación no es válida o no fue seleccionada de la lista.")
        return True
    except TimeoutException:
        return False


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
# Logout robusto (sin cambios)
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
# Flujo de LOGIN (sin cambios)
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


def _handle_existing_project(driver: WebDriver, wait: WebDriverWait) -> bool:
    """Detecta y elimina un proyecto existente para permitir una nueva configuración."""
    print("\n   -> ⚠️ No se encontró el input de la web. Verificando si ya existe un proyecto...")
    visibility_locator = (By.XPATH, '//span[text()="Supervisa el posicionamiento de la palabra clave."]')
    if not _wait_visible(wait, driver, visibility_locator, "Bloque 'Supervisa el posicionamiento'", timeout=10):
        print("      -> No se encontró ni el input de proyecto ni el dashboard existente.")
        return False
    
    print("      -> ✅ Se detectó un dashboard de proyecto existente. Iniciando flujo de eliminación.")
    try:
        if not _wait_and_click(wait, driver, (By.CSS_SELECTOR, 'div[data-testid="settings-icon"]'), "Ícono de configuración"): return False
        _sleep(1.5)
        if not _wait_and_click(wait, driver, (By.CSS_SELECTOR, 'div[data-testid="delete-menu-item"]'), "Opción 'Eliminar proyecto'"): return False
        _sleep(2)
        
        label_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'span[data-testid="multi-delete-confirm-code-number"]')))
        code_match = re.search(r'\d+', label_element.text)
        if not code_match: print("      -> ❌ No se pudo extraer el código numérico."); return False
        
        confirmation_code = code_match.group(0)
        print(f"         -> Código de confirmación extraído: {confirmation_code}")

        if not _send_text_to_input(wait, driver, (By.ID, "conformationCode"), confirmation_code, "Input de confirmación"): return False
        
        if not _wait_and_click(wait, driver, (By.XPATH, '//button[@data-testid="project-modal-button-action" and .//span[text()="Borrar"]]'), "Botón final 'Borrar'"): return False
        
        print("      -> ✅ Proyecto eliminado exitosamente.")
        _sleep(5)
        return True
    except Exception as e:
        print(f"      -> 🚨 Error durante la eliminación del proyecto: {e}")
        return False


# ───────────────────────────────────────────────────────────────────────────────
# Flujo de CONFIGURACIÓN DE CUENTA (MODIFICADO CON PAUSAS)
# ───────────────────────────────────────────────────────────────────────────────

def run_semrush_config_account_flow(credential_id: int, id_campaign: int, all_cities_for_campaign: List[str] = [], cycle_number: Optional[int] = None) -> Optional[str]:
    """
    Usa una credencial, prueba ciudades hasta encontrar una válida, configura el proyecto y actualiza la BD.
    Maneja proyectos existentes y cuentas en estados no estándar. Devuelve un estado al finalizar.
    """
    print("\n" + "="*60)
    cycle_info = f" (Ciclo Maestro #{cycle_number})" if cycle_number is not None else " (Ejecución Única)"
    print(f"🚀 INICIANDO FLUJO{cycle_info}: Config. de Campaña ID #{id_campaign} en Credencial ID #{credential_id}.")
    print("="*60)

    db = next(get_db())
    try:
        credential_to_use = db.query(CredentialSemrush).filter(CredentialSemrush.id == credential_id).first()
        if not credential_to_use: print(f"   -> ❌ No se encontró credencial con ID: {credential_id}."); return "DB_ERROR"
        campaign = db.query(Campaign).filter(Campaign.id == id_campaign).first()
        if not campaign or not campaign.web: print(f"   -> ❌ No se encontró campaña o no tiene web (ID: {id_campaign})."); return "DB_ERROR"
        web_url, email, password, proxy_host, proxy_port = campaign.web, credential_to_use.email, credential_to_use.password, credential_to_use.proxy, credential_to_use.port
    finally:
        db.close()

    cities_to_try = all_cities_for_campaign
    if not cities_to_try:
        try:
            drive = build_drive_client(credentials_json_path="credentials.json", token_json_path="token.json")
            cities_to_try = get_campaign_cities(drive, id_campaign) or []
            if not cities_to_try: print(f"   -> ❌ No se encontraron ciudades para la campaña {id_campaign}."); return "DRIVE_ERROR"
        except Exception as e:
            print(f"   -> 🚨 Error obteniendo datos de Drive: {e}."); return "DRIVE_ERROR"
    
    for city_candidate in cities_to_try:
        browser_manager = None
        driver = None
        try:
            print(f"\n--- 🔄 Probando con la ciudad: '{city_candidate}' ---")
            
            drive = build_drive_client()
            phrases = get_campaign_phrases_by_city(drive, id_campaign, city_candidate) or []
            phrases = list(dict.fromkeys(p.strip() for p in phrases if p and p.strip()))
            if not phrases:
                print("      -> Sin frases disponibles. Saltando a la siguiente ciudad.")
                continue

            proxy_manager = ProxyManager()
            proxy_config = proxy_manager.get_proxy_by_host_port(proxy_host, proxy_port)
            browser_manager = BrowserManagerProxy(chrome_path=r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", user_data_dir=os.path.join(os.getcwd(), "chrome_dev_session"), port="", proxy=proxy_config)
            driver = browser_manager.get_configured_driver("https://es.semrush.com/login/")
            if not driver: continue
            
            wait = WebDriverWait(driver, DEFAULT_STEP_TIMEOUT)
            _sleep(20)

            if not _send_text_to_input(wait, driver, (By.CSS_SELECTOR, 'input[name="email"]'), email, "input email", clear_first=False) or \
               not _send_text_to_input(wait, driver, (By.CSS_SELECTOR, 'input[name="password"]'), password, "input password", clear_first=False) or \
               not _wait_and_click(wait, driver, (By.XPATH, '//button[.//span[text()="Iniciar sesión"]]'), "botón Iniciar sesión"):
                raise Exception("Fallo en el login inicial")

            web_input_sel = (By.CSS_SELECTOR, 'input[data-ui-name="Input.Value"][placeholder="Indica el nombre de tu sitio web"]')
            visibility_locator = (By.XPATH, '//span[text()="Supervisa el posicionamiento de la palabra clave."]')

            if not _wait_visible(wait, driver, web_input_sel, "input web", timeout=15):
                print("\n   -> ⚠️ No se encontró el input de la web. Verificando si ya existe un proyecto...")
                if _wait_visible(wait, driver, visibility_locator, "Bloque 'Supervisa el posicionamiento'", timeout=5):
                    if not _handle_existing_project(driver, wait) or not _wait_visible(wait, driver, web_input_sel, "input web (tras limpieza)"):
                        raise Exception("Falló la eliminación del proyecto o el input no apareció después.")
                else:
                    print("   -> 🛑 La cuenta está en un estado configurado no estándar. No se puede proceder.")
                    db = next(get_db())
                    try:
                        cred_to_update = db.query(CredentialSemrush).filter(CredentialSemrush.id == credential_id).first()
                        if cred_to_update:
                            cred_to_update.id_campaigns = id_campaign
                            cred_to_update.note = "Configuración preexistente no estándar"
                            db.commit()
                    finally:
                        db.close()
                    return "PRECONFIGURED_STATE"
            
            if not _send_text_to_input(wait, driver, web_input_sel, web_url, "input web") or \
               not _wait_and_click(wait, driver, (By.XPATH, '//button[.//span[text()="Empieza ahora"]]'), "botón Empieza ahora"):
                raise Exception("Fallo en la creación inicial del proyecto")
            _sleep(15)

            if not _wait_visible(wait, driver, (By.XPATH, '//span[text()="Supervisa el posicionamiento de la palabra clave."]'), "bloque tracking") or \
               not _wait_and_click(wait, driver, (By.XPATH, '//div[@data-path="position_tracking"]//button[.//div[text()="Configurar"]]'), "botón Configurar"):
                raise Exception("Fallo navegando a la configuración de tracking")
            _sleep(10)
            
            loc_input = (By.XPATH, '//input[@data-ui-name="Input.Value" and @placeholder="Introduce país, ciudad, calle o código postal"]')
            el_loc = _wait_clickable(wait, driver, loc_input, "input ubicación")
            if not el_loc: raise Exception("No se encontró el input de ubicación")
            
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el_loc)
            el_loc.click(); _sleep(1); el_loc.send_keys(Keys.CONTROL, 'a'); _sleep(0.1); el_loc.send_keys(Keys.DELETE); _sleep(0.1)
            el_loc.send_keys(city_candidate)
            _sleep(5); _press_first_suggestion(el_loc, "input ubicación"); _sleep(2)

            if _check_for_location_error(driver):
                print(f"      -> Ciudad '{city_candidate}' rechazada. Probando la siguiente."); continue
            
            print(f"   -> ✅ Ubicación '{city_candidate}' aceptada.")
            city_to_use, phrases_to_use = city_candidate, phrases

            biz_input = (By.XPATH, '//input[@data-ui-name="Input.Value" and @placeholder="Incluye el nombre del negocio completo"]')
            campaign_name = campaign.name or str(id_campaign)
            if not _send_text_to_input(wait, driver, biz_input, campaign_name, "input nombre negocio", clear_first=True) or \
               not _wait_and_click(wait, driver, (By.ID, "ptr-wizard-next-step-button"), "Continuar a Palabras clave"):
                raise Exception("Fallo rellenando nombre de negocio")
            _sleep(8)
            
            phrases_csv = ", ".join(phrases_to_use)
            if phrases_csv: _send_text_to_input(wait, driver, (By.XPATH, '//textarea[@data-ui-name="Textarea" and contains(@placeholder, "keyword1")]'), phrases_csv, "textarea keywords", clear_first=True)
            
            _sleep(5)
            if not _wait_and_click(wait, driver, (By.ID, "ptr-wizard-apply-changes-button"), "Iniciar rastreo"):
                raise Exception("Fallo al iniciar rastreo")
            
            db = next(get_db())
            try:
                credential_to_update = db.query(CredentialSemrush).filter(CredentialSemrush.id == credential_id).first()
                if credential_to_update:
                    credential_to_update.id_campaigns = id_campaign
                    credential_to_update.note = city_to_use
                    db.commit()
                    print(f"\n   -> ✅ ¡ÉXITO! BD actualizada. Campaña {id_campaign} y ciudad '{city_to_use}' asignadas a credencial {credential_id}.")
            finally:
                db.close()

            print("\n   -> 🎉 ¡Configuración completada!")
            _sleep(240)
            _best_effort_logout(driver, wait)
            return "SUCCESS"

        except Exception as e:
            print(f"      -> 🚨 Error en el intento con '{city_candidate}': {e}.")
        finally:
            if browser_manager: browser_manager.quit_driver()
    
    print(f"\n   -> 🛑 AGOTADO: Ninguna de las ciudades probadas para la campaña {id_campaign} fue válida.")
    return "ALL_CITIES_FAILED"


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

# ───────────────────────────────────────────────────────────────────────────────
# CICLO MAESTRO (CON CONTADORES)
# ───────────────────────────────────────────────────────────────────────────────
def run_semrush_cycle_config_accounts(
    delay_seconds: float = 8.0,
    max_total_iterations: Optional[int] = None
) -> None:
    """
    Ciclo maestro que orquesta la configuración, ahora pasando la lista de ciudades
    a la función de configuración para que pueda iterar internamente.
    """
    print("\n" + "="*72 + "\n🧭 INICIANDO CICLO MAESTRO\n" + "="*72)
    successful_configurations, failed_configurations, iter_count = 0, 0, 0
    
    try:
        drive = build_drive_client()
        all_campaign_ids = _campaigns_in_db(list_accessible_campaign_ids(drive))
        random.shuffle(all_campaign_ids)
    except Exception as e:
        print(f"   -> 🚨 No se pudo conectar a Drive o a la BD para obtener campañas: {e}"); return

    while True:
        if max_total_iterations is not None and iter_count >= max_total_iterations:
            print("   -> ⛔ Tope de iteraciones alcanzado."); break

        free_credential_ids = list(_get_free_credential_ids())
        if not free_credential_ids:
            print("   -> ✅ No quedan credenciales libres. Ciclo finalizado."); break
        
        if not all_campaign_ids:
            print("   -> ⚠️ No quedan más campañas por procesar."); break
            
        campaign_id_to_process = all_campaign_ids.pop(0)
        credential_id_to_process = random.choice(free_credential_ids)
        iter_count += 1
        
        try:
            cities_for_campaign = get_campaign_cities(drive, campaign_id_to_process) or []
            if not cities_for_campaign:
                print(f"   -> (sin ciudades) Campaña {campaign_id_to_process} se omite.")
                continue
        except Exception as e:
            print(f"   -> ⚠️ No se pudieron obtener ciudades para campaña {campaign_id_to_process}: {e}"); continue
        
        print(f"\n▶️  Iniciando Ciclo de Configuración #{iter_count}: Campaña {campaign_id_to_process} en Credencial {credential_id_to_process}")
        
        result = run_semrush_config_account_flow(
            credential_id=credential_id_to_process,
            id_campaign=campaign_id_to_process,
            all_cities_for_campaign=cities_for_campaign,
            cycle_number=iter_count
        )
        
        if result == "SUCCESS":
            successful_configurations += 1
        else:
            failed_configurations += 1

        if delay_seconds > 0:
            _sleep(delay_seconds)

    print("\n" + "="*72 + "\n📊 RESUMEN DEL CICLO MAESTRO\n" + "="*72)
    print(f"   -> ✅ Configuraciones Exitosas: {successful_configurations}")
    print(f"   -> ❌ Configuraciones Fallidas (ninguna ciudad válida o error): {failed_configurations}")
    print(f"   -> 🔄 Total de Credenciales Procesadas: {iter_count}")
    print("="*72 + "\n✅ CICLO MAESTRO FINALIZADO.\n" + "="*72 + "\n")
