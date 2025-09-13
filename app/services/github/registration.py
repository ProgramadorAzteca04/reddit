from app.services.openai.content_generator_service import generate_human_username
from app.services.reddit.desktop_service import HumanInteractionUtils
from app.services.reddit.browser_service import BrowserManagerProxy
from app.services.reddit.proxy_service import ProxyManager
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from app.services.reddit.desktop_service import PyAutoGuiService
from app.db.database import get_db_secondary
from app.models.git import Credential
from datetime import datetime
import time, random, os


# =========================
# Utilidades "humanas"
# =========================
DEFAULT_STEP_TIMEOUT = 30

def _sleep(s: float):
    try:
        time.sleep(s)
    except Exception:
        pass

def _human_pause(a: float = 0.6, b: float = 1.4):
    time.sleep(random.uniform(a, b))

def _human_click(wait, driver, locator, label: str, timeout: int = 20) -> bool:
    try:
        el = wait.until(EC.element_to_be_clickable(locator))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        _human_pause(0.15, 0.35)
        ActionChains(driver).move_to_element(el).pause(random.uniform(0.08, 0.25)).click(el).perform()
        print(f"      -> ✅ Click humano en '{label}'.")
        _human_pause(0.25, 0.6)
        return True
    except Exception as e:
        print(f"      -> ❌ Falló click en '{label}': {e}")
        return False

def _human_type_into(wait, driver, locator, text: str, label: str,
                     clear_first: bool = False,
                     click_first: bool = True,
                     per_char_delay: tuple[float, float] = (0.05, 0.16),
                     allow_tiny_hesitations: bool = True,
                     timeout: int = 20) -> bool:
    try:
        el = wait.until(EC.visibility_of_element_located(locator))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        _human_pause(0.15, 0.35)

        if click_first:
            ActionChains(driver).move_to_element(el).pause(random.uniform(0.08, 0.22)).click(el).perform()
            _human_pause(0.08, 0.2)

        if clear_first:
            try:
                el.clear()
                _human_pause(0.05, 0.12)
            except Exception:
                el.send_keys(Keys.CONTROL, 'a')
                _human_pause(0.05, 0.12)
                el.send_keys(Keys.DELETE)
                _human_pause(0.05, 0.12)

        for ch in text:
            el.send_keys(ch)
            time.sleep(random.uniform(*per_char_delay))
            if allow_tiny_hesitations and random.random() < 0.06:
                time.sleep(random.uniform(0.07, 0.18))

        print(f"      -> ✅ Texto (humano) enviado a '{label}'.")
        _human_pause(0.25, 0.6)
        return True
    except Exception as e:
        print(f"      -> ⏱️ Timeout/err tipeando en '{label}': {e}")
        return False


# =========================
# Botón Create account
# =========================
def _is_visible_enabled(btn):
    try:
        if not btn.is_displayed():
            return False
        if btn.get_attribute("disabled") is not None:
            return False
        aria = (btn.get_attribute("aria-disabled") or "").lower()
        if aria in ("true", "disabled"):
            return False
        classes = (btn.get_attribute("class") or "").lower()
        if "disabled" in classes or "is-disabled" in classes:
            return False
        return True
    except Exception:
        return False

def _find_create_account_candidates(driver):
    candidates = []
    candidates += driver.find_elements(By.CSS_SELECTOR, 'button[data-target="signup-form.SignupButton"]')
    candidates += driver.find_elements(By.XPATH, "//button[.//span[contains(@class,'Button-label')] and normalize-space(.)='Create account']")
    candidates += driver.find_elements(By.XPATH, "//button[contains(@class,'signup-form-fields__button') and contains(@class,'Button--primary')][.//span[normalize-space()='Create account']]")
    uniq, seen = [], set()
    for el in candidates:
        key = getattr(el, "_id", id(el))
        if key not in seen:
            seen.add(key); uniq.append(el)
    return [e for e in uniq if _is_visible_enabled(e)]

def click_create_account_human(wait, driver, verify_transition: bool = True) -> bool:
    candidates = _find_create_account_candidates(driver)
    if not candidates:
        print("   -> ❌ No se encontraron botones 'Create account' visibles/habilitados.")
        return False

    for idx, btn in enumerate(candidates, start=1):
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            ActionChains(driver).move_to_element(btn).pause(0.12).click(btn).perform()
            print(f"   -> ✅ Click humano en 'Create account' (candidato {idx}).")
        except Exception as e1:
            print(f"   -> ⚠️ Click interceptado en candidato {idx}: {e1}. Intentando alternativas…")
            for try_fn in (
                lambda: btn.send_keys(Keys.ENTER),
                lambda: btn.send_keys(Keys.SPACE),
                lambda: ActionChains(driver).move_to_element(btn.find_element(By.CSS_SELECTOR, ".Button-label")).pause(0.08).click().perform(),
                lambda: driver.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", btn),
                lambda: driver.execute_script("var f=arguments[0].closest('form'); if(f){ (f.requestSubmit||f.submit).call(f)}", btn),
            ):
                try:
                    try_fn(); print(f"   -> ✅ Alternativa de click aplicada (candidato {idx})."); break
                except Exception: pass

        if not verify_transition:
            return True
        try:
            wait.until(EC.any_of(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-target*='captcha'], iframe[src*='captcha'], iframe[title*='captcha'], .octocaptcha")),
                EC.url_contains("signup/verify"),
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='otp'], input[id*='code']")),
                EC.presence_of_element_located((By.CSS_SELECTOR, ".flash-error, .flash-warn"))
            ))
            print("   -> ✅ Siguiente paso detectado (captcha/verificación/feedback).")
            return True
        except TimeoutException:
            cls = (btn.get_attribute("class") or "").lower()
            if "loading" in cls or "progress" in cls:
                print("   -> ℹ️ Botón en estado de carga. Dando por válido.")
                return True
            print("   -> ⚠️ Sin transición clara; probando otro candidato…")

    print("   -> ❌ Ningún intento logró avanzar tras 'Create account'.")
    return False


# =========================
# País
# =========================
def validate_or_select_country_human(wait, driver, expected_country: str = "United States of America") -> bool:
    try:
        btn = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "button[aria-labelledby='country-dropdown-label']")))
        text = btn.text.strip()
        if text == expected_country:
            print(f"✅ País correcto ya seleccionado: '{expected_country}'")
            return True

        print(f"❌ País visible: '{text}' (se esperaba '{expected_country}') — abriendo selector…")
        if not _human_click(wait, driver, (By.CSS_SELECTOR, "button[aria-labelledby='country-dropdown-label']"), "selector de país"):
            return False

        dialog_id = btn.get_attribute("aria-controls")
        if dialog_id:
            dialog = wait.until(EC.presence_of_element_located((By.ID, dialog_id)))
            scope_sel = f"#{dialog.get_attribute('id')}"
        else:
            dialog = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "[role='dialog'], div[id*='select-panel'][id$='-dialog']")))
            scope_sel = "[role='dialog']"

        input_locators = [
            (By.CSS_SELECTOR, f"{scope_sel} input[type='search']"),
            (By.CSS_SELECTOR, f"{scope_sel} input[type='text']"),
        ]
        wrote = False
        for loc in input_locators:
            if _human_type_into(wait, driver, loc, expected_country, "input country", clear_first=True):
                try:
                    el = wait.until(EC.element_to_be_clickable(loc))
                    el.send_keys(Keys.ENTER); _human_pause(0.25, 0.55)
                except Exception: pass
                wrote = True; print(f"✍️ País tecleado humanamente: {expected_country}")
                break

        if not wrote:
            option_xpaths = [
                f"{scope_sel} *[self::button or self::span or self::div][normalize-space()='{expected_country}']",
            ]
            clicked = any(_human_click(wait, driver, (By.XPATH, xp), f"opción país: {expected_country}") for xp in option_xpaths)
            if not clicked:
                print("🚨 No fue posible seleccionar el país."); return False

        try:
            wait.until(EC.text_to_be_present_in_element((By.CSS_SELECTOR, "button[aria-labelledby='country-dropdown-label']"), expected_country))
            print(f"✅ Confirmado en el botón: '{expected_country}'"); return True
        except TimeoutException:
            btn2 = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "button[aria-labelledby='country-dropdown-label']")))
            if btn2.text.strip() == expected_country:
                print(f"✅ Confirmado en el botón (fallback): '{expected_country}'"); return True
            print("⚠️ El país no se reflejó en el botón tras la selección."); return False
    except Exception as e:
        print(f"⚠️ Error en validate_or_select_country_human: {e}")
        return False


# =========================
# Detección transición post submit
# =========================
def detect_signup_transition(wait, driver, timeout: int = 25) -> tuple[bool, str]:
    try:
        WebDriverWait(driver, timeout).until(EC.any_of(
            EC.url_contains("/signup/verify"),
            EC.presence_of_element_located((By.CSS_SELECTOR, ".octocaptcha, iframe[src*='captcha'], iframe[title*='captcha']")),
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='otp'], input[id*='code']")),
            EC.presence_of_element_located((By.XPATH, "//h1[contains(., 'Verify') or contains(., 'Puzzle') or contains(., 'verification')]"))
        ))
        return True, "transition-detected"
    except TimeoutException:
        return False, "timeout-awaiting-transition"


# =========================
# Octocaptcha (iframe + Shadow DOM)
# =========================
def check_octocaptcha_presence(wait: WebDriverWait, driver, timeout: int = 15) -> tuple[bool, str]:
    try:
        container = None
        try:
            container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#captcha-container-nux")))
        except TimeoutException:
            container = None

        iframe_elems = driver.find_elements(By.CSS_SELECTOR, "iframe.js-octocaptcha-frame, iframe[src*='octocaptcha.com']")
        token_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name='octocaptcha-token'].js-octocaptcha-token, input[name='octocaptcha-token']")
        token_value = ""
        if token_inputs:
            try: token_value = token_inputs[0].get_attribute("value") or ""
            except Exception: token_value = ""

        success_elems = driver.find_elements(By.CSS_SELECTOR, ".js-octocaptcha-success")
        success_visible = any("d-none" not in (el.get_attribute("class") or "").lower() for el in success_elems)

        verify_present = bool(driver.find_elements(By.CSS_SELECTOR, "#verify-account-header, h2#verify-account-header"))

        if success_visible or (token_inputs and token_value.strip()):
            return True, "success"
        if container is not None or iframe_elems or token_inputs or verify_present:
            return True, "pending"
        return False, "absent"
    except Exception:
        return False, "absent"

def _find_visible_octocaptcha_iframe(driver):
    frames = driver.find_elements(By.CSS_SELECTOR, "iframe.js-octocaptcha-frame, iframe[src*='octocaptcha.com']")
    for fr in frames:
        try:
            if fr.is_displayed() and fr.size.get("width", 0) > 0 and fr.size.get("height", 0) > 0:
                return fr
        except Exception:
            continue
    return None

def _switch_to_octocaptcha_iframe(wait: WebDriverWait, driver, timeout: int = 20) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        iframe = _find_visible_octocaptcha_iframe(driver)
        if iframe:
            try: driver.execute_script("arguments[0].scrollIntoView({block:'center'});", iframe)
            except Exception: pass
            try:
                driver.switch_to.frame(iframe); time.sleep(0.25)
                return True
            except Exception as e:
                print(f"      -> ⚠️ Falló switch a iframe visible: {e}")
        time.sleep(0.5)
    print("      -> ❌ Timeout localizando/switch al iframe de Octocaptcha.")
    return False

def _deep_query_element(driver, css_selector: str, timeout: int = 10):
    script = """
const sel = arguments[0];
const deadline = Date.now() + (arguments[1] * 1000);
function deepQuery(selector, root){
  const el = root.querySelector(selector);
  if (el) return el;
  const hosts = root.querySelectorAll('*');
  for (let i=0; i<hosts.length; i++){
    const h = hosts[i];
    if (h.shadowRoot){
      const found = deepQuery(selector, h.shadowRoot);
      if (found) return found;
    }
  }
  return null;
}
let found = null;
while (Date.now() < deadline){
  try { found = deepQuery(sel, document); if (found) break; } catch(e){}
}
return found;
"""
    try:
        return driver.execute_script(script, css_selector, timeout)
    except Exception:
        return None

def _try_acknowledge_if_needed(driver) -> bool:
    candidate_selectors = [
        "input[type='checkbox']",
        "button[data-theme*='ack'],button[data-testid*='ack']",
        "label:has(input[type='checkbox'])",
    ]
    clicked = False
    for sel in candidate_selectors:
        try:
            el = _deep_query_element(driver, sel, timeout=1)
            if not el: continue
            tag = (el.tag_name or "").lower()
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.1)
            if tag == "input" and (el.get_attribute("type") or "").lower() == "checkbox":
                if not el.is_selected():
                    el.click(); clicked = True; print("   -> ✅ Reconocimiento (checkbox) marcado.")
            else:
                try: ActionChains(driver).move_to_element(el).pause(0.08).click(el).perform()
                except Exception: driver.execute_script("arguments[0].click();", el)
                clicked = True; print("   -> ✅ Reconocimiento (botón) aceptado.")
        except Exception:
            continue
    return clicked

def _wait_until_octocaptcha_success(wait: WebDriverWait, driver, max_seconds: int = 180) -> bool:
    """
    Espera activa hasta que Octocaptcha muestre SUCCESS.
    Ya no intenta abrir 'Visual puzzle'.
    """
    deadline = time.monotonic() + max_seconds
    while time.monotonic() < deadline:
        try:
            succ = driver.find_elements(By.CSS_SELECTOR, ".js-octocaptcha-success")
            if succ and any(el.is_displayed() and "d-none" not in (el.get_attribute("class") or "").lower() for el in succ):
                print("   -> ✅ Octocaptcha en estado SUCCESS.")
                return True
        except Exception:
            pass
        time.sleep(1.0)

    print(f"   -> ❌ Timeout esperando SUCCESS de Octocaptcha ({max_seconds}s).")
    return False


# =========================
# Persistencia
# =========================
def persist_credentials(email: str, username: str, password: str, proxy_info: dict) -> bool:
    db = None
    try:
        db = next(get_db_secondary())
        cred = Credential(
            username=username,
            email=email,
            password=password,
            proxy=proxy_info.get("host"),
            port=proxy_info.get("port"),
            created_at=datetime.utcnow() if hasattr(Credential, "created_at") else None
        )
        db.add(cred); db.commit()
        try:
            _id = getattr(cred, "id", None)
            print(f"💾 Credenciales guardadas correctamente (id={_id}).")
        except Exception:
            print("💾 Credenciales guardadas correctamente.")
        return True
    except Exception as e:
        if db: db.rollback()
        print(f"🚨 ERROR al guardar credenciales: {e}")
        return False
    finally:
        if db: db.close()


# =========================
# Flujo principal
# =========================
def run_github_sign_in_flow():
    print("\n" + "="*60)
    print("🚀 INICIANDO FLUJO: Registro en GitHub.")
    print("="*60)

    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    URL = "https://gist.github.com/starred"
    USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_dev_session")

    pyautogui_service = PyAutoGuiService()

    browser_manager = None
    driver = None
    email_to_use = ""
    password_to_use = ""
    username_to_use = ""
    proxy_info = {}

    try:
        proxy_manager = ProxyManager()
        proxy = proxy_manager.get_random_proxy()
        user_agent = proxy_manager.get_random_user_agent()
        if proxy:
            proxy_info = {"host": proxy.get("host"), "port": proxy.get("port")}

        browser_manager = BrowserManagerProxy(
            chrome_path=CHROME_PATH, user_data_dir=USER_DATA_DIR, port="",
            proxy=proxy, user_agent=user_agent
        )
        driver = browser_manager.get_configured_driver(URL)
        if not driver:
            print("   -> ❌ No se pudo iniciar el driver de Selenium-Wire.")
            return False

        print("\n   -> Esperando 20 segundos para que la página cargue...")
        _sleep(20)

        wait = WebDriverWait(driver, DEFAULT_STEP_TIMEOUT)

        # 0) Click en "Sign up" antes de llenar el correo (versión robusta)
        print("   -> ⏳ Buscando enlace 'Sign up'…")

        # a) localizar por atributos estables (evita depender del texto con &nbsp;)
        sign_locators = [
            (By.CSS_SELECTOR, "a.Header-link[href*='/join'][data-ga-click*='sign up']"),
            (By.CSS_SELECTOR, "a.Header-link[data-ga-click*='sign up']"),
            (By.XPATH, "//a[contains(@data-ga-click, 'sign up')]"),
            (By.XPATH, "//a[contains(@href, '/join') and contains(@class,'Header-link')]"),
        ]

        sign_el = None
        for by, sel in sign_locators:
            try:
                # presencia primero (evita fallar si aún no es clickeable)
                candidate = WebDriverWait(driver, 8).until(EC.presence_of_element_located((by, sel)))
                if candidate and candidate.is_displayed():
                    sign_el = candidate
                    break
            except Exception:
                continue

        if not sign_el:
            print("❌ No se encontró el enlace 'Sign up' por selectores robustos.")
            return False

        # b) asegurar que no haya overlays cubriendo el header y centrar el elemento
        try:
            driver.execute_script("window.scrollTo(0, 0)")
        except Exception:
            pass
        _human_pause(0.2, 0.4)
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", sign_el)
        except Exception:
            pass
        _human_pause(0.2, 0.4)

        # c) intento #1: click "humano" con ActionChains
        clicked = False
        try:
            ActionChains(driver).move_to_element(sign_el).pause(random.uniform(0.08, 0.2)).click(sign_el).perform()
            clicked = True
            print("   -> ✅ Click humano en 'Sign up'.")
        except Exception as e:
            print(f"   -> ⚠️ Click humano interceptado: {e}")

        # d) alternativas si falló
        if not clicked:
            for try_fn in (
                lambda: sign_el.send_keys(Keys.ENTER),
                lambda: sign_el.send_keys(Keys.SPACE),
                lambda: driver.execute_script("arguments[0].click();", sign_el),
            ):
                try:
                    try_fn()
                    clicked = True
                    print("   -> ✅ Alternativa de click aplicada en 'Sign up'.")
                    break
                except Exception:
                    pass

        # e) último recurso: navegar directo a la URL absoluta de join
        if not clicked:
            try:
                href = sign_el.get_attribute("href") or "/join"
                abs_url = driver.execute_script("return new URL(arguments[0], window.location.href).href;", href)
                print(f"   -> 🔗 Navegando directo a: {abs_url}")
                driver.get(abs_url)
            except Exception as e:
                print(f"   -> ❌ No se pudo navegar a join directamente: {e}")
                return False

        _human_pause(0.8, 1.6)  # pequeña pausa humana después del click

        # 1) Email
        email_to_use = HumanInteractionUtils.get_random_email_from_file()
        if not email_to_use:
            print("❌ No se pudo obtener un correo electrónico válido para el registro.")
            return False
        print(f"Usando correo electrónico para registro: {email_to_use}")
        if not _human_type_into(wait, driver, (By.CSS_SELECTOR, '#email'), email_to_use, "input email", clear_first=False):
            return False
        _human_pause()

        # 2) Password
        password_to_use = HumanInteractionUtils.generate_password(length=12)
        print(f"🔒 Contraseña generada: {password_to_use}")
        if not _human_type_into(wait, driver, (By.CSS_SELECTOR, '#password'), password_to_use, "input password", clear_first=False, allow_tiny_hesitations=False):
            return False
        _human_pause()

        # 3) Username
        username_to_use = generate_human_username()
        print(f"👤 Username generado: {username_to_use}")
        if not _human_type_into(wait, driver, (By.CSS_SELECTOR, '#login'), username_to_use, "input username", clear_first=False):
            return False
        _human_pause()

        # 4) País
        if not validate_or_select_country_human(wait, driver, "United States of America"):
            return False
        _human_pause(0.8, 1.8)

        time.sleep(5)

        # 5) Create account (PyAutoGUI con dos intentos)
        try:
            print("   -> ⏳ Buscando botón 'Create account' con PyAutoGUI (1er intento)…")
            if not pyautogui_service.find_and_click_humanly(["create_account_git.png"], attempts=3):
                raise RuntimeError("No se encontró el botón 'Create account' en el primer intento.")
            print("   -> ✅ Click humano (PyAutoGUI) en 'Create account' (1er intento).")

            # Espera antes de repetir
            time.sleep(5)

            print("   -> ⏳ Buscando botón 'Create account' con PyAutoGUI (2do intento)…")
            if not pyautogui_service.find_and_click_humanly(["create_account_git.png"], attempts=3):
                print("⚠️ No se encontró el botón en el 2do intento. Continuando sin error…")
            else:
                print("   -> ✅ Click humano (PyAutoGUI) en 'Create account' (2do intento).")

        except Exception as e:
            print(f"❌ Error al intentar hacer click en 'Create account': {e}")
            return False

        # Verificación de transición tras el click
        ok, reason = detect_signup_transition(wait, driver, timeout=30)
        if not ok:
            print(f"❌ No se detectó transición tras 'Create account' ({reason}). No se guardarán credenciales.")
            return False

        # 6) Octocaptcha antes de guardar
        present, state = check_octocaptcha_presence(wait, driver, timeout=15)
        print(f"   -> ℹ️ Verificación detectada (estado: {state}).")

        if not present:
            print("❌ No se encontró UI de verificación (Octocaptcha). No se guardarán credenciales.")
            return False

        # ⏳ NUEVO: si el captcha está 'pending' (solicitado), esperamos 60s antes de continuar
        if state == "pending":
            print("   -> ⏳ Captcha solicitado (estado: pending). Esperando 60 segundos antes de continuar…")
            _sleep(60)

            # Revalidación tras la espera
            present_after, state_after = check_octocaptcha_presence(wait, driver, timeout=5)
            print(f"   -> 🔄 Revalidación tras 60s: present={present_after}, state={state_after}")

            if state_after == "pending":
                # Intento manual con PyAutoGUI
                try:
                    if not pyautogui_service.find_and_click_humanly(["visual_puzzle.png"], attempts=2):
                        raise RuntimeError("No se encontró el campo de puzzle.")
                    print("   -> ✅ Puzzle visual detectado y clickeado.")
                    # 👇 NUEVO: esperar 3 segundos y luego buscar botón de recarga
                    time.sleep(3)

                    print("   -> ⏳ Buscando botón 'Reload Challenge' en el DOM…")
                    try:
                        if not _human_click(wait, driver, (By.XPATH, "//button[normalize-space()='Reload Challenge']"), "Reload Challenge"):
                            print("⚠️ No se encontró o no fue clickeable el botón 'Reload Challenge'. Continuando…")
                        else:
                            print("   -> ✅ Click humano en 'Reload Challenge'.")
                    except Exception as e:
                        print(f"❌ Error al intentar clickear 'Reload Challenge': {e}")
                    
                except Exception as e:
                    print(f"❌ Error al intentar abrir el puzzle visual: {e}")
                    return False

                # Luego del intento manual, espera a SUCCESS
                print("   -> ⏳ Octocaptcha PENDING tras la acción manual: esperando SUCCESS…")
                if not _wait_until_octocaptcha_success(wait, driver, max_seconds=180):
                    print("❌ La verificación Octocaptcha no se completó. No se guardarán credenciales.")
                    return False

            elif state_after == "success":
                print("   -> ✅ Verificación completada durante la espera de 60s.")
            else:
                print("   -> ⚠️ Estado inesperado tras la espera. Continuando con precaución…")

        # 7) Guardar credenciales SOLO si verificación OK
        print("   -> ✅ Verificación completada. Guardando credenciales…")
        if not persist_credentials(email_to_use, username_to_use, password_to_use, proxy_info):
            return False

    except Exception as e:
        print(f"❌ Error durante el proceso de registro: {e}")
        return False
