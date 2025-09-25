# app/services/github/registration.py

# =========================
# Importaciones
# =========================

# Bibliotecas estándar de Python
import os
import random
import time

# Bibliotecas de terceros
import pyautogui
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Módulos de la aplicación local
from app.db.database import get_db_secondary
from app.models.git import Credential as GitCredential
from app.services.email_reader_service import get_latest_verification_code
from app.services.openai.content_generator_service import generate_human_username
from app.services.reddit.browser_service import BrowserManagerProxy
from app.services.reddit.desktop_service import (DesktopUtils,
                                                  HumanInteractionUtils,
                                                  PathManager)
from app.services.reddit.proxy_service import ProxyManager

# =========================
# Configuración
# =========================

DEFAULT_STEP_TIMEOUT = 30
JOIN_FALLBACK = "https://gist.github.com/join?return_to=https%3A%2F%2Fgist.github.com%2Fstarred&source=header-gist"

# =======================================
# Utilidades de Interacción "Humana"
# =======================================

def _sleep(s: float):
    """Pausa la ejecución por un tiempo determinado."""
    try:
        time.sleep(s)
    except Exception:
        pass


def _human_pause(a: float = 0.6, b: float = 1.4):
    """Pausa la ejecución por un tiempo aleatorio entre 'a' y 'b' segundos."""
    time.sleep(random.uniform(a, b))


def _human_click(wait, driver, locator, label: str, timeout: int = 20) -> bool:
    """
    Realiza un clic simulando el comportamiento humano.
    """
    try:
        el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable(locator))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        _human_pause(0.15, 0.35)
        ActionChains(driver).move_to_element(el).pause(
            random.uniform(0.08, 0.25)
        ).click(el).perform()
        print(f"       -> ✅ Click humano en '{label}'.")
        _human_pause(0.25, 0.6)
        return True
    except Exception as e:
        print(f"       -> ❌ Falló click en '{label}': {e}")
        return False


def _human_type_into(
    wait,
    driver,
    locator,
    text: str,
    label: str,
    clear_first: bool = False,
    click_first: bool = True,
    per_char_delay: tuple[float, float] = (0.05, 0.16),
    timeout: int = 20,
) -> bool:
    """
    Escribe texto en un campo simulando la escritura de una persona.
    """
    try:
        el = WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located(locator)
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        _human_pause(0.15, 0.35)

        if click_first:
            ActionChains(driver).move_to_element(el).pause(
                random.uniform(0.08, 0.22)
            ).click(el).perform()
            _human_pause(0.08, 0.2)

        if clear_first:
            try:
                el.clear()
                _human_pause(0.05, 0.12)
            except Exception:
                el.send_keys(Keys.CONTROL, "a")
                _human_pause(0.05, 0.12)
                el.send_keys(Keys.DELETE)
                _human_pause(0.05, 0.12)

        for ch in text:
            el.send_keys(ch)
            time.sleep(random.uniform(*per_char_delay))
            if random.random() < 0.06:
                time.sleep(random.uniform(0.07, 0.18))

        print(f"       -> ✅ Texto (humano) enviado a '{label}'.")
        _human_pause(0.25, 0.6)
        return True
    except Exception as e:
        print(f"       -> ⏱️ Timeout/err tipeando en '{label}': {e}")
        return False


def wait_and_click_image(
    image_name: str, timeout: int = 60, confidence: float = 0.9
) -> bool:
    """
    Espera a que una imagen aparezca en la pantalla y luego hace clic "humano" en ella.
    """
    print(f"\n-> ⏳ Esperando y buscando '{image_name}' (timeout: {timeout}s)...")
    start_time = time.time()
    img_path = os.path.join(PathManager.get_img_folder(), image_name)

    while time.time() - start_time < timeout:
        try:
            position = pyautogui.locateCenterOnScreen(img_path, confidence=confidence)
            if position:
                print(f"   -> ✅ Imagen '{image_name}' encontrada en {position}.")
                HumanInteractionUtils.move_mouse_humanly(position.x, position.y)
                pyautogui.click()
                print("   -> ✅ Clic realizado en la imagen.")
                return True
        except pyautogui.PyAutoGUIException:
            pass
        time.sleep(1)

    print(f"   -> ❌ Timeout: No se encontró la imagen '{image_name}' en {timeout} segundos.")
    return False


def validate_or_select_country_human(
    wait, driver, expected_country: str = "United States of America"
) -> bool:
    """
    Busca y selecciona un país en el menú desplegable.
    """

    def _btn_country():
        return wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "button[aria-labelledby='country-dropdown-label']")
            )
        )

    # 1. Verificar si ya está seleccionado
    try:
        btn = _btn_country()
        if (btn.text or "").strip() == expected_country:
            print(f"✅ País correcto ya seleccionado: '{expected_country}'")
            return True
    except Exception:
        pass

    # 2. Abrir el selector
    try:
        btn = _btn_country()
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        ActionChains(driver).move_to_element(btn).pause(0.12).click(btn).perform()
        print("       -> ✅ Click humano en 'selector de país'.")
    except Exception as e:
        print(f"       -> ❌ No se pudo abrir el selector de país: {e}")
        return False

    # 3. Escribir y presionar Enter
    try:
        active_element = driver.switch_to.active_element
        for ch in expected_country:
            active_element.send_keys(ch)
            time.sleep(random.uniform(0.03, 0.08))
        time.sleep(0.25)
        active_element.send_keys(Keys.ENTER)
        print(f"✍️  País tecleado y confirmado con ENTER: {expected_country}")
    except Exception as e:
        print(f"       -> ⚠️ No se pudo teclear en el elemento activo: {e}")
        return False

    # 4. Verificar que el cambio se reflejó
    try:
        wait.until(
            EC.text_to_be_present_in_element(
                (By.CSS_SELECTOR, "button[aria-labelledby='country-dropdown-label']"),
                expected_country,
            )
        )
        print(f"✅ Confirmado en el botón: '{expected_country}'")
        return True
    except TimeoutException:
        print("⚠️ El país no se reflejó en el botón tras la selección.")
        return False


def _is_visible_enabled(btn):
    """Verifica si un botón está visible y habilitado para ser clickeado."""
    try:
        if not btn.is_displayed() or btn.get_attribute("disabled") is not None:
            return False
        if (btn.get_attribute("aria-disabled") or "").lower() == "true":
            return False
        return True
    except Exception:
        return False


def _find_create_account_candidates(driver):
    """Encuentra todos los posibles botones de 'Create account'."""
    candidates = []
    candidates += driver.find_elements(
        By.CSS_SELECTOR, 'button[data-target="signup-form.SignupButton"]'
    )
    candidates += driver.find_elements(
        By.XPATH, "//button[normalize-space()='Create account']"
    )

    unique_elements = {el.id: el for el in candidates}.values()
    return [el for el in unique_elements if _is_visible_enabled(el)]


def click_create_account_human(wait, driver) -> bool:
    """
    Busca el botón 'Create account' y hace clic en él.
    """
    candidates = _find_create_account_candidates(driver)
    if not candidates:
        print("       -> ❌ No se encontraron botones 'Create account' visibles/habilitados.")
        return False

    for idx, btn in enumerate(candidates, start=1):
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            ActionChains(driver).move_to_element(btn).pause(0.12).click(btn).perform()
            print(f"       -> ✅ Click humano en 'Create account' (candidato {idx}).")
            return True
        except Exception as e:
            print(f"       -> ⚠️ Click fallido en candidato {idx}: {e}.")

    print("       -> ❌ Ningún intento de clic en 'Create account' tuvo éxito.")
    return False


# ===============================
# Flujo Principal de Registro
# ===============================

def run_github_sign_in_flow() -> bool:
    print("\n" + "=" * 60)
    print("🚀 INICIANDO FLUJO: Registro en GitHub (hasta crear cuenta).")
    print("=" * 60)

    # --- Configuración del entorno ---
    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    URL = "https://gist.github.com/starred"
    USER_DATA_DIR = os.path.join(
        os.getcwd(), "chrome_dev_session"
    )  # Directorio de datos de usuario único
    WINDOW_TITLE = "GitHub"

    browser_manager = None
    driver = None

    try:
        # --- Proxy y User Agent ---
        proxy_manager = ProxyManager()
        proxy = proxy_manager.get_random_proxy()
        user_agent = proxy_manager.get_random_user_agent()

        # --- Iniciar y conectar con el navegador usando BrowserManagerProxy ---
        browser_manager = BrowserManagerProxy(
            chrome_path=CHROME_PATH,
            user_data_dir=USER_DATA_DIR,
            port="",  # No es necesario para este método
            proxy=proxy,
            user_agent=user_agent,
        )
        driver = browser_manager.get_configured_driver(URL)
        if not driver:
            print("❌ No se pudo iniciar el driver de Selenium-Wire.")
            return False

        # Opcional: enfocar la ventana si es necesario
        time.sleep(5)
        DesktopUtils.get_and_focus_window(WINDOW_TITLE)

        print("\n-> Esperando a que la página cargue...")
        wait = WebDriverWait(driver, DEFAULT_STEP_TIMEOUT)

        # --- Ir a la página de 'Sign up' ---
        print("-> ⏳ Navegando a la página de registro...")
        driver.get(JOIN_FALLBACK)
        _human_pause(2.0, 3.0)
        time.sleep(6)

        # --- Rellenar formulario ---
        print("\n-> 📝 Rellenando datos del formulario...")
        email_to_use = HumanInteractionUtils.get_random_email_from_file()
        if not email_to_use:
            print("❌ No se encontró un email válido para usar.")
            return False

        print(f"📧 Email: {email_to_use}")
        if not _human_type_into(wait, driver, (By.ID, "email"), email_to_use, "input email"):
            return False

        password_to_use = HumanInteractionUtils.generate_password(length=12)
        print(f"🔒 Contraseña: {password_to_use}")
        if not _human_type_into(
            wait, driver, (By.ID, "password"), password_to_use, "input password"
        ):
            return False

        username_to_use = generate_human_username()
        print(f"👤 Usuario: {username_to_use}")
        if not _human_type_into(
            wait, driver, (By.ID, "login"), username_to_use, "input username"
        ):
            return False

        # --- Seleccionar País ---
        if not validate_or_select_country_human(wait, driver, "United States of America"):
            return False
        _human_pause(0.8, 1.8)
        time.sleep(3)

        # --- Hacer clic en 'Create account' ---
        print("\n-> 🚀 Intentando crear la cuenta...")
        if not click_create_account_human(wait, driver):
            print("❌ El proceso falló al intentar enviar el formulario.")
            return False

        # --- Esperar y hacer clic en el puzzle visual ---
        if not wait_and_click_image("visual_puzzle.png", timeout=60):
            print("❌ No apareció el puzzle visual o no se pudo hacer clic. El flujo no puede continuar.")
            return False

        # --- Proceso de verificación por correo electrónico ---
        print("\n-> 📧 Iniciando proceso de verificación de correo electrónico...")
        print("   -> ⏳ Esperando 120 segundos para la llegada del correo de verificación...")
        time.sleep(120)

        try:
            print("   -> 🧐 Verificando que la página solicita el código...")
            WebDriverWait(driver, 30).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//h2[contains(text(), 'Confirm your email address')]")
                )
            )
            print("   -> ✅ Página de confirmación de correo cargada.")
        except TimeoutException:
            print("   -> ❌ No se cargó la página de confirmación de correo a tiempo.")
            return False

        print("   -> 📥 Buscando código de verificación en el correo...")
        verification_code = get_latest_verification_code(
            subject_keywords=["GitHub", "launch", "code"]
        )

        if not verification_code:
            print("   -> ❌ No se encontró un código de verificación en el correo.")
            return False

        print(f"   -> ✅ Código de verificación encontrado: {verification_code}")

        try:
            code_inputs = driver.find_elements(
                By.CSS_SELECTOR, "input[id^='launch-code-']"
            )
            if len(code_inputs) >= len(verification_code):
                print("   -> ✍️  Introduciendo el código en los campos...")
                for i, digit in enumerate(verification_code):
                    code_inputs[i].send_keys(digit)
                    time.sleep(random.uniform(0.1, 0.4))
                print("   -> ✅ Código introducido exitosamente.")
            else:
                print(
                    f"   -> ❌ Se encontraron {len(code_inputs)} campos, pero se necesitan {len(verification_code)}."
                )
                return False
        except Exception as e:
            print(f"   -> ❌ Error al intentar introducir el código en los campos: {e}")
            return False

        # --- Pasos finales de confirmación ---
        print("\n-> 🎉 Finalizando la creación de la cuenta...")
        continue_button_locator = (By.XPATH, "//button[.//span[text()='Continue']]")
        if not _human_click(
            wait, driver, continue_button_locator, "botón Continue final"
        ):
            print("   -> ❌ No se pudo hacer clic en el botón 'Continue' final.")
            return False

        print("   -> ⏳ Esperando 60 segundos para la creación final de la cuenta...")
        time.sleep(60)

        try:
            print("   -> 🧐 Verificando mensaje de éxito final...")
            success_message_locator = (
                By.XPATH,
                "//div[contains(text(), 'Your account was created successfully!')]",
            )
            WebDriverWait(driver, 30).until(
                EC.visibility_of_element_located(success_message_locator)
            )
            print("   -> ✅ ¡Cuenta creada exitosamente! Mensaje de confirmación encontrado.")
        except TimeoutException:
            print("   -> ❌ No se encontró el mensaje de éxito final.")
            return False

        # --- Guardar credenciales en la base de datos ---
        print("\n-> 💾 Guardando credenciales en la base de datos...")
        db = next(get_db_secondary())
        try:
            new_credential = GitCredential(
                username=username_to_use,
                password=password_to_use,
                email=email_to_use,
                proxy=proxy.get("host", "") if proxy else "",
                port=proxy.get("port", "") if proxy else "",
            )
            db.add(new_credential)
            db.commit()
            print("   -> ✅ Credenciales de GitHub guardadas exitosamente.")
        except Exception as e:
            print(
                f"   -> 🚨 ERROR al guardar las credenciales en la base de datos: {e}"
            )
            db.rollback()
            return False
        finally:
            db.close()

        print("\n" + "=" * 60)
        print("✅ Flujo de registro y verificación completado con éxito.")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"❌ Error catastrófico durante el flujo: {e}")
        return False
    finally:
        if browser_manager:
            browser_manager.quit_driver()
            print("\n-> Conexión con el navegador cerrada.")


# ===============================================
# Punto de entrada para ejecutar el script
# ===============================================

if __name__ == "__main__":
    run_github_sign_in_flow()