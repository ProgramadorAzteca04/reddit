# app/services/semrush/registration_service.py
import time
import os
import traceback
from app.services.reddit.browser_service import BrowserManagerProxy
from app.services.reddit.proxy_service import ProxyManager
from app.services.reddit.desktop_service import HumanInteractionUtils
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from app.services.email_reader_service import get_latest_verification_code

def _handle_survey_step(driver: WebDriver, wait: WebDriverWait, survey_step: int):
    """
    Función reutilizable para manejar un paso de la encuesta.
    Detecta si hay una encuesta visible y siempre selecciona la segunda opción.
    """
    print(f"\n   -> 📝 Intentando completar el paso #{survey_step} de la encuesta...")
    try:
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'h2[id="questionTitle"]')))
        time.sleep(2)

        print("      -> Buscando opciones disponibles...")
        survey_options = wait.until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'label[data-test="survey_input"]'))
        )

        if len(survey_options) >= 2:
            second_option = survey_options[1]
            option_text = second_option.text.replace("\n", " ").strip()
            print(f"         -> ✅ Se encontraron {len(survey_options)} opciones. Seleccionando la segunda: '{option_text}'")
            driver.execute_script("arguments[0].click();", second_option)
            time.sleep(1.5)

            print("      -> Buscando el botón 'Continuar'...")
            continue_button = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-test="survey_continue"]'))
            )
            continue_button.click()
            print("         -> ✅ Clic en 'Continuar' realizado.")
            return True
        else:
            print(f"      -> ⚠️ Se encontraron menos de 2 opciones ({len(survey_options)}).")
            return False

    except TimeoutException:
        print("      -> No se encontró una nueva pantalla de encuesta.")
        return False

def run_semrush_signup_flow():
    """
    Orquesta el flujo de registro completo en Semrush, manejando un número variable de encuestas
    y los pasos opcionales finales.
    """
    print("\n" + "="*60)
    print("🚀 INICIANDO FLUJO: Registro en Semrush.")
    print("="*60)

    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    URL = "https://es.semrush.com/signup/"
    USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_dev_session")

    browser_manager = None
    driver = None
    try:
        # --- Configuración del navegador ---
        proxy_manager = ProxyManager()
        proxy = proxy_manager.get_random_proxy()
        user_agent = proxy_manager.get_random_user_agent()

        browser_manager = BrowserManagerProxy(
            chrome_path=CHROME_PATH, user_data_dir=USER_DATA_DIR, port="",
            proxy=proxy, user_agent=user_agent
        )
        
        driver = browser_manager.get_configured_driver(URL)
        if not driver:
            raise RuntimeError("No se pudo iniciar el driver de Selenium-Wire.")

        print("\n   -> Esperando 20 segundos para que la página cargue...")
        time.sleep(20)
        
        wait = WebDriverWait(driver, 30)
        
        # --- Llenado del formulario y verificación ---
        email_to_use = HumanInteractionUtils.get_random_email_from_file()
        if not email_to_use: raise ValueError("No se pudo obtener un correo.")
        
        print(f"   -> Usando el correo: {email_to_use}")
        email_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-test="signup-page__input-email"]')))
        email_field.click(); time.sleep(1); email_field.send_keys(email_to_use)
        
        password_to_use = HumanInteractionUtils.generate_password(length=14)
        password_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-test="signup-page__input-password"]')))
        password_field.click(); time.sleep(1); password_field.send_keys(password_to_use)
        
        create_account_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-test="signup-page__btn-signup"]')))
        create_account_button.click()
        print("   -> ✅ Formulario de registro inicial enviado.")
        
        print("\n   -> Esperando 30 segundos para la recepción del correo de activación...")
        time.sleep(30)
        
        verification_code = get_latest_verification_code(subject_keywords=['Activation', 'Semrush'])
        if verification_code and len(verification_code) == 6:
            print(f"      -> ✅ ¡Código encontrado!: {verification_code}")
            try:
                code_inputs = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'input[data-ui-name="Input.Value"][maxlength="1"]')))
                if len(code_inputs) == 6:
                    for i, digit in enumerate(verification_code):
                        code_inputs[i].send_keys(digit)
                        time.sleep(0.3)
                    print("      -> ✅ Código introducido exitosamente.")
            except TimeoutException:
                print("      -> 🚨 ERROR: No se encontraron los campos para el código.")
        else:
            print(f"      -> ⚠️ No se encontró un código de verificación válido.")

        # --- BUCLE DE ENCUESTAS DINÁMICO ---
        time.sleep(15)
        survey_step_count = 1
        while _handle_survey_step(driver, wait, survey_step_count):
            survey_step_count += 1
            time.sleep(5)
        print("\n   -> ✅ Proceso de encuestas finalizado.")
        
        # --- PASOS FINALES OPCIONALES ---
        
        # 1. Omitir periodo de prueba
        print("\n   -> 💳 Buscando botón para omitir periodo de prueba...")
        try:
            # Usamos un tiempo de espera más corto aquí para no ralentizar el flujo si no aparece
            short_wait = WebDriverWait(driver, 10)
            skip_trial_button = short_wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-test="skip-button"]'))
            )
            skip_trial_button.click()
            print("      -> ✅ Periodo de prueba omitido.")
            time.sleep(5)
        except TimeoutException:
            print("      -> No se encontró el botón para omitir la prueba (paso opcional).")

        # 2. Omitir pantalla de "Estamos en contacto"
        print("\n   -> 📞 Buscando pantalla 'Estamos en contacto'...")
        try:
            short_wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'h1[data-test="contact-info__cta-title"]')))
            print("      -> Pantalla encontrada. Omitiendo...")
            skip_contact_button = short_wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-test="contact-info__skip-button"]'))
            )
            skip_contact_button.click()
            print("      -> ✅ Pantalla de contacto omitida.")
            time.sleep(5)
        except TimeoutException:
            print("      -> No se encontró la pantalla de contacto (paso opcional).")

        # 3. Responder "¿Dónde oíste hablar de nosotros?"
        print("\n   -> 🗣️ Buscando pregunta final '¿Dónde oíste hablar de nosotros?'...")
        try:
            short_wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'h1[data-test="marketing-source-page__title"]')))
            print("      -> Pantalla encontrada. Respondiendo...")
            other_option = short_wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[data-test="other"]'))
            )
            other_option.click()
            print("      -> ✅ Opción 'Otros' seleccionada.")
            time.sleep(1.5)

            start_using_button = short_wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-test="marketing-source-page__continue"]'))
            )
            start_using_button.click()
            print("      -> ✅ Clic en 'Empieza a usar Semrush'.")
        except TimeoutException:
            print("      -> No se encontró la pregunta final (paso opcional).")

        print("\n   -> Registro completado. La ventana permanecerá abierta por 20 segundos.")
        time.sleep(20)

    except Exception as e:
        print(f"\n🚨 ERROR FATAL durante el flujo de Semrush: {e}")
        traceback.print_exc()
    finally:
        if browser_manager:
            browser_manager.quit_driver()
        print("\n" + "="*60)
        print("✅ SERVICIO FINALIZADO: Flujo de Semrush.")
        print("="*60 + "\n")