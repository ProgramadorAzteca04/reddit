# app/services/semrush/registration_service.py
import time
import os
import traceback
from app.services.reddit.browser_service import BrowserManagerProxy
from app.services.reddit.proxy_service import ProxyManager
from app.services.reddit.desktop_service import HumanInteractionUtils
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from app.services.email_reader_service import get_latest_verification_code

def run_semrush_signup_flow():
    """
    Orquesta el flujo de registro en Semrush, incluyendo el llenado del código de verificación
    y la selección de opciones en la encuesta de personalización.
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
        proxy_manager = ProxyManager()
        proxy = proxy_manager.get_random_proxy()
        user_agent = proxy_manager.get_random_user_agent()

        browser_manager = BrowserManagerProxy(
            chrome_path=CHROME_PATH,
            user_data_dir=USER_DATA_DIR,
            port="", # El puerto ya no es relevante
            proxy=proxy,
            user_agent=user_agent
        )
        
        driver = browser_manager.get_configured_driver(URL)
        if not driver:
            raise RuntimeError("No se pudo iniciar el driver de Selenium-Wire.")

        print("\n   -> Esperando 20 segundos para que la página cargue...")
        time.sleep(20)
        
        wait = WebDriverWait(driver, 20)
        
        email_to_use = HumanInteractionUtils.get_random_email_from_file()
        if not email_to_use:
            raise ValueError("No se pudo obtener un correo del archivo correos.txt.")
        
        print(f"   -> Usando el correo: {email_to_use}")
        email_field = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-test="signup-page__input-email"]'))
        )
        email_field.click()
        time.sleep(1)
        email_field.send_keys(email_to_use)
        print("   -> ✅ Correo electrónico escrito exitosamente.")

        password_to_use = HumanInteractionUtils.generate_password(length=14)
        
        password_field = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-test="signup-page__input-password"]'))
        )
        password_field.click()
        time.sleep(1)
        password_field.send_keys(password_to_use)
        print("   -> ✅ Contraseña escrita exitosamente.")

        print("   -> Buscando el botón 'Crear una cuenta'...")
        
        create_account_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-test="signup-page__btn-signup"]'))
        )
        create_account_button.click()
        
        print("   -> ✅ Clic exitoso en 'Crear una cuenta'.")
        
        print("\n   -> Esperando 30 segundos para la recepción del correo de activación...")
        time.sleep(30)

        print("   -> 📧 Buscando código de activación en el correo...")
        verification_code = get_latest_verification_code(subject_keywords=['Activation', 'Semrush'])
        
        if verification_code and len(verification_code) == 6:
            print(f"      -> ✅ ¡Código de verificación encontrado!: {verification_code}")
            
            print("   -> 🔢 Intentando introducir el código en la página...")
            try:
                code_inputs = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'input[data-ui-name="Input.Value"][maxlength="1"]'))
                )
                
                if len(code_inputs) == 6:
                    print("      -> ✅ Se encontraron los 6 campos para el código.")
                    for i, digit in enumerate(verification_code):
                        input_field = code_inputs[i]
                        input_field.send_keys(digit)
                        print(f"         -> Escribiendo dígito {i+1}: '{digit}'")
                        time.sleep(0.3)
                    
                    print("      -> ✅ Código de verificación introducido exitosamente.")
                else:
                    print(f"      -> ⚠️  Se esperaban 6 campos para el código, pero se encontraron {len(code_inputs)}.")

            except TimeoutException:
                print("      -> 🚨 ERROR: No se encontraron los campos para introducir el código en la página.")
            
        else:
            print(f"      -> ⚠️ No se encontró un código de verificación válido. (Recibido: {verification_code})")

        # --- INICIO DE LA NUEVA LÓGICA PARA LA ENCUESTA ---
        print("\n   -> 📝 Esperando 30 segundos para la encuesta de personalización...")
        time.sleep(30)
        
        try:
            print("      -> Buscando opciones de la encuesta...")
            # 1. Esperar a que las opciones (etiquetas <label>) estén presentes
            survey_options = wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'label[data-test="survey_input"]'))
            )

            if len(survey_options) >= 2:
                # 2. Seleccionar y hacer clic en la segunda opción
                second_option = survey_options[1]
                option_text = second_option.text
                print(f"         -> ✅ Se encontraron {len(survey_options)} opciones. Seleccionando la segunda: '{option_text}'")
                second_option.click()
                time.sleep(1.5)

                # 3. Buscar y hacer clic en el botón "Continuar"
                print("      -> Buscando el botón 'Continuar'...")
                continue_button = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-test="survey_continue"]'))
                )
                continue_button.click()
                print("         -> ✅ Clic en 'Continuar' realizado.")
            else:
                print(f"      -> ⚠️ Se encontraron menos de 2 opciones en la encuesta ({len(survey_options)}), saltando este paso.")

        except TimeoutException:
            print("      -> 🚨 No se encontró la pantalla de la encuesta. El flujo puede continuar si esto es opcional.")
        # --- FIN DE LA NUEVA LÓGICA ---

        print("\n   -> Proceso de registro enviado. La ventana permanecerá abierta por 45 segundos para observar el resultado.")
        time.sleep(45)

    except TimeoutException as e:
        print(f"   -> 🚨 ERROR: Tiempo de espera agotado. No se pudo encontrar un elemento: {e}")
    except Exception as e:
        print(f"\n🚨 ERROR FATAL durante el flujo de Semrush: {e}")
        traceback.print_exc()
    finally:
        if browser_manager:
            browser_manager.quit_driver()
        print("\n" + "="*60)
        print("✅ SERVICIO FINALIZADO: Flujo de Semrush.")
        print("="*60 + "\n")