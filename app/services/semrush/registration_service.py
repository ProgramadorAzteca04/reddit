# app/services/semrush/registration_service.py
from app.services.email_reader_service import get_latest_verification_code
from app.services.reddit.desktop_service import HumanInteractionUtils
from app.services.reddit.browser_service import BrowserManagerProxy
from selenium.webdriver.support import expected_conditions as EC
from app.services.semrush.login_service import _perform_logout
from app.services.reddit.proxy_service import ProxyManager
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
    WebDriverException,
)
from app.models.semrush_models import CredentialSemrush
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from app.db.database import get_db
import traceback
import time
import os

# ✅ NUEVO: importar el helper único de CAPTCHA desde el servicio dedicado
from app.services.captcha_service import solve_recaptcha_in_iframes

# ─────────────────────────────────────────────────────────────
# Helpers de resiliencia (no alteran la lógica; la endurecen)
# ─────────────────────────────────────────────────────────────
DEFAULT_STEP_TIMEOUT = 30
DEFAULT_RETRIES = 2

def _sleep(s: float):
    try:
        time.sleep(s)
    except Exception:
        pass

def _wait_clickable(wait: "WebDriverWait", driver: "WebDriver", locator, label: str, timeout: int | None = None):
    """Espera elemento clickable; devuelve el WebElement o None (no lanza)."""
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

def _wait_visible(wait: "WebDriverWait", driver: "WebDriver", locator, label: str, timeout: int | None = None) -> bool:
    """Espera visibilidad; True/False (no lanza)."""
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

def _click_with_fallback(driver: "WebDriver", element, label: str) -> bool:
    """Clic normal; si hay overlay, scroll + JS click."""
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
    except (StaleElementReferenceException, WebDriverException) as e:
        print(f"      -> ⚠️ Error al hacer click en '{label}': {e}")
        return False

def _wait_and_click(wait: "WebDriverWait", driver: "WebDriver", locator, label: str,
                    retries: int = DEFAULT_RETRIES, timeout: int | None = None) -> bool:
    """Espera y hace click con reintentos y fallback. No lanza."""
    for attempt in range(1, retries + 1):
        el = _wait_clickable(wait, driver, locator, label, timeout=timeout)
        if _click_with_fallback(driver, el, label):
            print(f"      -> ✅ Click en '{label}' (intento {attempt}).")
            return True
        print(f"      -> 🔁 Reintentando click en '{label}' (intento {attempt}/{retries})...")
        _sleep(1)
    print(f"      -> ❌ No se pudo hacer click en '{label}' tras {retries} intentos.")
    return False

def _send_text_to_input(wait: "WebDriverWait", driver: "WebDriver", locator, text: str,
                        label: str, clear_first: bool = True, timeout: int | None = None) -> bool:
    """Foco, limpiar opcionalmente y send_keys; silencioso si falla."""
    el = _wait_clickable(wait, driver, locator, label, timeout=timeout)
    if el is None:
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        _sleep(0.2)
    except Exception:
        pass
    try:
        el.click(); _sleep(0.2)
        if clear_first:
            try:
                el.clear()
            except Exception:
                el.send_keys(Keys.CONTROL, 'a'); _sleep(0.1)
                el.send_keys(Keys.DELETE); _sleep(0.1)
        if text:
            el.send_keys(text)
        print(f"      -> ✅ Texto enviado a '{label}'.")
        return True
    except Exception as e:
        print(f"      -> ⚠️ No se pudo escribir en '{label}': {e}")
        return False

def _best_effort_logout(driver: "WebDriver", wait: "WebDriverWait"):
    """Intenta cerrar sesión sin romper si falla."""
    try:
        _perform_logout(driver, wait)
    except Exception as e:
        print(f"   -> ⚠️ Logout best-effort falló: {e}")


def _handle_survey_step(driver: WebDriver, wait: WebDriverWait, survey_step: int):
    """
    Maneja un paso de encuesta (selecciona segunda opción y continúa).
    No lanza excepciones; True si completó el paso, False si no hay paso nuevo.
    """
    print(f"\n   -> 📝 Intentando completar el paso #{survey_step} de la encuesta...")
    try:
        if not _wait_visible(wait, driver, (By.CSS_SELECTOR, 'h2[id="questionTitle"]'), "titulo encuesta", timeout=10):
            print("      -> No se encontró una nueva pantalla de encuesta.")
            return False

        print("      -> Buscando opciones disponibles...")
        try:
            survey_options = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'label[data-test="survey_input"]'))
            )
        except TimeoutException:
            print("      -> ⏱️ Timeout buscando opciones de encuesta.")
            return False

        if len(survey_options) >= 2:
            second_option = survey_options[1]
            option_text = second_option.text.replace("\n", " ").strip()
            print(f"         -> ✅ Se encontraron {len(survey_options)} opciones. Seleccionando: '{option_text}'")
            try:
                second_option.click()
            except Exception:
                driver.execute_script("arguments[0].click();", second_option)
            _sleep(1.0)

            print("      -> Buscando el botón 'Continuar'...")
            if _wait_and_click(wait, driver, (By.CSS_SELECTOR, 'button[data-test="survey_continue"]'), "botón Continuar", retries=3, timeout=10):
                print("         -> ✅ Clic en 'Continuar' realizado.")
                return True
            print("         -> ❌ No se pudo clicar 'Continuar'.")
            return False
        else:
            print(f"      -> ⚠️ Se encontraron menos de 2 opciones ({len(survey_options)}).")
            return False

    except Exception as e:
        print(f"      -> ⚠️ Error manejando encuesta: {e}")
        return False


def run_semrush_signup_flow():
    """
    Orquesta el flujo de registro completo en Semrush, maneja encuestas y pasos opcionales.
    """
    print("\n" + "="*60)
    print("🚀 INICIANDO FLUJO: Registro en Semrush.")
    print("="*60)

    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    URL = "https://es.semrush.com/signup/"
    USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_dev_session")

    browser_manager = None
    driver = None
    email_to_use = ""
    password_to_use = ""
    proxy_info = {}

    try:
        # Configuración de navegador/proxy
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
            return

        print("\n   -> Esperando 20 segundos para que la página cargue...")
        _sleep(20)
        wait = WebDriverWait(driver, DEFAULT_STEP_TIMEOUT)
        short_wait = WebDriverWait(driver, 10)

        # Llenado del formulario y envío
        email_to_use = HumanInteractionUtils.get_random_email_from_file()
        if not email_to_use:
            print("   -> ❌ No se pudo obtener un correo.")
            return
        print(f"   -> Usando el correo: {email_to_use}")

        if not _send_text_to_input(wait, driver, (By.CSS_SELECTOR, '[data-test="signup-page__input-email"]'),
                                   email_to_use, "input email", clear_first=False):
            return

        password_to_use = HumanInteractionUtils.generate_password(length=14)
        print(f"🔒 Contraseña generada: {'*' * len(password_to_use)}")
        if not _send_text_to_input(wait, driver, (By.CSS_SELECTOR, '[data-test="signup-page__input-password"]'),
                                   password_to_use, "input password", clear_first=False):
            return

        if not _wait_and_click(wait, driver, (By.CSS_SELECTOR, '[data-test="signup-page__btn-signup"]'),
                               "botón crear cuenta", retries=3):
            return
        print("   -> ✅ Formulario de registro inicial enviado.")

        # reCAPTCHA (si aparece) — ahora delegado al servicio de captcha
        print("   -> ⚠️ Verificando si hay reCAPTCHA para resolver...")
        solved = solve_recaptcha_in_iframes(driver, wait, user_agent=user_agent, max_attempts=2, submit=False)
        print("   -> ✅ reCAPTCHA resuelto correctamente." if solved else "   -> (No hubo captcha o no se pudo resolver; continúo)")

        # Esperar correo de activación
        print("\n   -> Esperando 30 segundos para la recepción del correo de activación...")
        _sleep(30)

        verification_code = get_latest_verification_code(subject_keywords=['Activation', 'Semrush'])
        if verification_code and len(verification_code) == 6:
            print(f"      -> ✅ ¡Código encontrado!: {verification_code}")
            try:
                code_inputs = short_wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'input[data-ui-name="Input.Value"][maxlength="1"]'))
                )
                if len(code_inputs) == 6:
                    for i, digit in enumerate(verification_code):
                        try:
                            code_inputs[i].send_keys(digit)
                            _sleep(0.2)
                        except Exception:
                            pass
                    print("      -> ✅ Código introducido exitosamente.")
                else:
                    print("      -> ⚠️ No se encontraron 6 campos de código.")
            except TimeoutException:
                print("      -> 🚨 No se encontraron los campos para el código.")
        else:
            print("      -> ⚠️ No se encontró un código de verificación válido.")

        # Segundo captcha (posible)
        _sleep(2)
        print("\n   -> ⚠️ Verificando si apareció un segundo reCAPTCHA…")
        second_ok = solve_recaptcha_in_iframes(driver, wait, user_agent=user_agent, max_attempts=2, submit=False)
        print("   -> ✅ Segundo reCAPTCHA resuelto correctamente." if second_ok else "   -> (No hubo segundo captcha o no se resolvió; continúo).")

        # Bucle de encuestas
        _sleep(15)
        survey_step_count = 1
        while _handle_survey_step(driver, wait, survey_step_count):
            survey_step_count += 1
            _sleep(5)
        print("\n   -> ✅ Proceso de encuestas finalizado.")

        # Paso opcional: omitir periodo de prueba
        print("\n   -> 💳 Buscando botón para omitir periodo de prueba...")
        if not _wait_and_click(short_wait, driver, (By.CSS_SELECTOR, 'button[data-test="skip-button"]'),
                               "botón omitir prueba", retries=2):
            print("      -> No se encontró el botón para omitir la prueba (paso opcional).")
        else:
            _sleep(5)

        # Paso opcional: “Estamos en contacto”
        print("\n   -> 📞 Buscando pantalla 'Estamos en contacto'...")
        if _wait_visible(short_wait, driver, (By.CSS_SELECTOR, 'h1[data-test="contact-info__cta-title"]'),
                         "pantalla contacto", timeout=8):
            if _wait_and_click(short_wait, driver, (By.CSS_SELECTOR, 'button[data-test="contact-info__skip-button"]'),
                               "botón omitir contacto", retries=2):
                print("      -> ✅ Pantalla de contacto omitida.")
                _sleep(5)
            else:
                print("      -> ⚠️ No se pudo omitir la pantalla de contacto (continuo).")
        else:
            print("      -> No se encontró la pantalla de contacto (paso opcional).")

        # Paso opcional: “¿Dónde oíste hablar de nosotros?”
        print("\n   -> 🗣️ Buscando pregunta final '¿Dónde oíste hablar de nosotros?'...")
        if _wait_visible(short_wait, driver, (By.CSS_SELECTOR, 'h1[data-test="marketing-source-page__title"]'),
                         "pantalla fuente marketing", timeout=8):
            try:
                other_input = short_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[data-test="other"]')))
                label_for_other = driver.find_elements(By.XPATH, '//input[@data-test="other"]/ancestor::label[1]')
                target = label_for_other[0] if label_for_other else other_input

                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", target)
                _sleep(0.3)
                clicked = False
                for attempt in range(1, 4):
                    try:
                        target.click(); clicked = True; break
                    except Exception:
                        try:
                            driver.execute_script("arguments[0].click();", target)
                            clicked = True; break
                        except Exception:
                            _sleep(0.4)
                if not clicked:
                    print("      -> ⚠️ No se pudo clicar la opción 'Otros'.")
                # Continuar
                if _wait_and_click(short_wait, driver, (By.CSS_SELECTOR, 'button[data-test="marketing-source-page__continue"]'),
                                   "botón seguir (marketing source)", retries=2):
                    print("      -> ✅ Opción 'Otros' seleccionada y continuado correctamente.")
                else:
                    print("      -> ⚠️ No se pudo continuar en marketing source (paso opcional).")
            except TimeoutException:
                print("      -> ⚠️ No se encontró la opción 'Otros' (paso opcional).")
        else:
            print("      -> No se encontró la pantalla de marketing source (paso opcional).")

        # Guardar en BD
        print("\n   -> 💾 Intentando guardar la nueva cuenta en la base de datos...")
        db = next(get_db())
        try:
            new_credential = CredentialSemrush(
                email=email_to_use,
                password=password_to_use,
                proxy=proxy_info.get("host"),
                port=proxy_info.get("port"),
                note="Registrado automáticamente"
            )
            db.add(new_credential)
            db.commit()
            print("      -> ✅ ¡Cuenta guardada exitosamente en la base de datos!")

            # Logout best-effort
            try:
                print("   -> Intentando exponer el header antes de logout (si fuera necesario)...")
                driver.get("https://es.semrush.com/")
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'body')))
            except Exception:
                pass
            print("   -> Cerrando sesión…")
            _best_effort_logout(driver, WebDriverWait(driver, 20))

        except Exception as db_error:
            print(f"      -> 🚨 ERROR al guardar en la base de datos: {db_error}")
            db.rollback()
        finally:
            db.close()

        print("\n   -> Registro completado. La ventana permanecerá abierta por 20 segundos.")
        _sleep(20)

    except Exception as e:
        print(f"\n🚨 ERROR FATAL durante el flujo de Semrush: {e}")
        traceback.print_exc()
    finally:
        try:
            if driver:
                print("🔐 Intentando logout FINAL (último paso) antes de cerrar el navegador…")
                try:
                    driver.get("https://es.semrush.com/")
                    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
                except Exception:
                    pass
                # Llamada al logout robusto (usa primero tus dos selectores exactos)
                _perform_logout(driver, WebDriverWait(driver, 20))
        except Exception as e:
            print(f"⚠️ Error intentando logout final: {e}")
        finally:
            if browser_manager:
                browser_manager.quit_driver()
        print("\n" + "="*60)
        print("✅ SERVICIO FINALIZADO: Flujo de Semrush.")
        print("="*60 + "\n")

# ─────────────────────────────────────────────────────────────
# Batch: ejecutar N veces el flujo de registro (secuencial)
# ─────────────────────────────────────────────────────────────
def run_semrush_signup_flow_batch(times: int, delay_seconds: float = 10.0) -> None:
    """
    Ejecuta N veces el flujo de registro de forma secuencial.
    Cada iteración se aísla con try/except para que un fallo no
    interrumpa las siguientes. No devuelve nada.
    """
    # Sanitizar parámetros
    try:
        times = int(times)
    except Exception:
        print("⚠️  times no es un entero válido; usando 1.")
        times = 1
    if times <= 0:
        print("⚠️  times <= 0; no hay nada que ejecutar.")
        return
    try:
        delay_seconds = float(delay_seconds)
        if delay_seconds < 0:
            delay_seconds = 0.0
    except Exception:
        delay_seconds = 10.0

    MAX_TIMES = 50  # límite de seguridad
    if times > MAX_TIMES:
        print(f"⚠️  times={times} supera el máximo permitido ({MAX_TIMES}); se ajusta a {MAX_TIMES}.")
        times = MAX_TIMES

    for i in range(1, times + 1):
        print(f"\n=== ▶️ Inicio de registro #{i}/{times} ===")
        try:
            run_semrush_signup_flow()
        except Exception as e:
            print(f"⚠️  Error en el registro #{i}: {e}")
            import traceback as _tb
            _tb.print_exc()
        finally:
            if i < times and delay_seconds > 0:
                print(f"⏳ Esperando {delay_seconds} segundos antes del siguiente registro...")
                _sleep(delay_seconds)
        print(f"=== ✅ Fin de registro #{i}/{times} ===\n")
