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
from app.services.semrush.login_service import _perform_logout
# --- NUEVO: 2Captcha + utilidades ---
from app.services.captcha_service import TwoCaptchaSolver

# --- DB ---
from app.db.database import get_db
from app.models.semrush_models import CredentialSemrush


def _handle_survey_step(driver: WebDriver, wait: WebDriverWait, survey_step: int):
    """
    Maneja un paso de encuesta (selecciona segunda opción y continúa).
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
            print(f"         -> ✅ Se encontraron {len(survey_options)} opciones. Seleccionando: '{option_text}'")
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


# ==========================
#   CAPTCHA: RESOLVER v2
# ==========================
def _extract_sitekey_from_bframe_src(src: str) -> str | None:
    """
    Extrae el sitekey (param 'k') desde la URL del iframe bframe de reCAPTCHA.
    """
    if not src:
        return None
    try:
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(src).query)
        k = q.get("k", [None])[0]
        return k
    except Exception:
        return None


def _inject_recaptcha_token_no_submit(driver: WebDriver, token: str) -> None:
    """
    Inyecta 'token' en g-recaptcha-response, dispara eventos y,
    en lugar de forzar submit, intenta invocar el callback de reCAPTCHA (v2/enterprise).
    Evita recargar la página.
    """
    driver.execute_script("""
      (function(tok){
        // 1) Asegurar textarea y setear valor
        var ta = document.getElementById('g-recaptcha-response');
        if(!ta){
          ta = document.createElement('textarea');
          ta.id = 'g-recaptcha-response';
          ta.name = 'g-recaptcha-response';
          ta.style.display='block';
          ta.style.width='1px';
          ta.style.height='1px';
          ta.style.opacity='0.01';
          ta.style.position='absolute';
          ta.style.left='-9999px';
          document.body.appendChild(ta);
        }
        ta.value = tok;

        // También setear en cualquier otro textarea con ese name
        var all = document.querySelectorAll('textarea[name="g-recaptcha-response"]');
        all.forEach(function(e){ e.value = tok; });

        // 2) Disparar eventos para frameworks (sin submit)
        var evts = ['input','change'];
        evts.forEach(function(e){
          try { ta.dispatchEvent(new Event(e, {bubbles:true})); } catch(_){}
        });

        // 3) Intentar invocar callback registrado de reCAPTCHA (v2/enterprise)
        function safeInvoke(cb){
          try { cb(tok); } catch(e){}
        }

        var invoked = false;

        try {
          // enterprise primero
          if (window.grecaptcha && window.grecaptcha.enterprise && typeof window.grecaptcha.enterprise.getResponse === 'function') {
            // Buscar posibles callbacks en la config interna
            var cfg = window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients || {};
            for (var i in cfg){
              var ci = cfg[i];
              for (var j in ci){
                var cj = ci[j];
                for (var k in cj){
                  var ck = cj[k];
                  if (ck && typeof ck.callback === 'function') { safeInvoke(ck.callback); invoked = true; }
                  if (ck && ck.sitekey) {
                    // algunos bindings guardan callback en 'b.callback' o similar
                    if (ck.b && typeof ck.b.callback === 'function') { safeInvoke(ck.b.callback); invoked = true; }
                  }
                }
              }
            }
          } else if (window.grecaptcha) {
            // v2 normal
            var cfg2 = window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients || {};
            for (var i2 in cfg2){
              var c2 = cfg2[i2];
              for (var j2 in c2){
                var cj2 = c2[j2];
                for (var k2 in cj2){
                  var ck2 = cj2[k2];
                  if (ck2 && typeof ck2.callback === 'function') { safeInvoke(ck2.callback); invoked = true; }
                  if (ck2 && ck2.b && typeof ck2.b.callback === 'function') { safeInvoke(ck2.b.callback); invoked = true; }
                }
              }
            }
          }
        } catch(e){}

        // 4) Fallback suave: emitir un evento global para apps que lo escuchen
        if (!invoked) {
          try { document.dispatchEvent(new CustomEvent('recaptcha-token-injected', {detail:{token: tok}})); } catch(_){}
        }
      })(arguments[0]);
    """, token)


def _solve_semrush_recaptcha_iframe(driver: WebDriver, wait: WebDriverWait, user_agent: str | None, max_attempts: int = 2) -> bool:
    """
    Detecta el iframe `api2/bframe` (reCAPTCHA v2 invisible/enterprise),
    extrae sitekey desde 'k=...', pide token a 2Captcha e inyecta en la página.
    Devuelve True si lo resolvió e inyectó.
    """
    try:
        time.sleep(2)  # breve pausa para permitir que aparezca el overlay
        # localizar posibles iframes del reto
        iframes = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='api2/bframe' i], iframe[src*='recaptcha' i]")
        print(f"   -> Detección de iframes reCAPTCHA: encontrados {len(iframes)}")
        if not iframes:
            # algunos montajes crean el popup dentro de un div wrapper; si no hay iframe, no forzamos
            print("   -> No se detectó iframe de reCAPTCHA; no se resuelve.")
            return False

        # tomar el primero que tenga parámetro k
        sitekey = None
        iframe_src = None
        for ifr in iframes:
            src = ifr.get_attribute("src") or ""
            k = _extract_sitekey_from_bframe_src(src)
            if k:
                sitekey = k
                iframe_src = src
                break

        if not sitekey:
            print("   -> ⚠️ No se pudo extraer sitekey (param k) de los iframes.")
            return False

        print(f"   -> 🎯 Sitekey detectado: {sitekey}")
        if iframe_src:
            print(f"      -> SRC del iframe: {iframe_src}")

        solver = TwoCaptchaSolver()  # lee TWOCAPTCHA_API_KEY del .env
        attempt = 1
        while attempt <= max_attempts:
            print(f"      -> Solicitando token a 2Captcha (intento {attempt}/{max_attempts})...")
            try:
                # reCAPTCHA v2 invisible / enterprise: invisible=1 ayuda al proveedor
                token = solver.solve(
                    method="userrecaptcha",
                    googlekey=sitekey,
                    pageurl=driver.current_url,
                    invisible=1,
                    # enterprise=1 se puede enviar, pero 2Captcha lo infiere en muchos casos
                    # enterprise=1,
                    **({"userAgent": user_agent} if user_agent else {})
                )
                if token:
                    print("      -> ✅ Token recibido. Inyectando en la página...")
                    _inject_recaptcha_token_no_submit(driver, token)

                    # Esperar a que desaparezca el iframe/popup (no obligatorio)
                    try:
                        WebDriverWait(driver, 10).until_not(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[src*='api2/bframe' i], .sso-recaptcha-popup"))
                        )
                    except TimeoutException:
                        pass
                    return True
                else:
                    print("      -> ❌ 2Captcha no devolvió token.")
            except Exception as e:
                print(f"      -> ❌ Error solicitando/injectando token: {e}")
            attempt += 1
            time.sleep(3)

        print("   -> 🚨 No se pudo resolver el reCAPTCHA tras los reintentos.")
        return False

    except Exception as e:
        print(f"   -> ❌ Error general al resolver el reCAPTCHA: {e}")
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
    # --- Variables para guardar en la BD ---
    email_to_use = ""
    password_to_use = ""
    proxy_info = {}

    try:
        # --- Configuración del navegador ---
        proxy_manager = ProxyManager()
        proxy = proxy_manager.get_random_proxy()
        user_agent = proxy_manager.get_random_user_agent()
        
        # --- Guardamos la info del proxy ---
        if proxy:
            proxy_info = {
                "host": proxy.get("host"),
                "port": proxy.get("port")
            }

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
        print(f"🔒 Contraseña generada: {'*' * len(password_to_use)}")
        password_field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-test="signup-page__input-password"]')))
        password_field.click(); time.sleep(1); password_field.send_keys(password_to_use)
        
        create_account_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-test="signup-page__btn-signup"]')))
        create_account_button.click()
        print("   -> ✅ Formulario de registro inicial enviado.")

        # ---------- Resolver reCAPTCHA si aparece (popup sin checkbox) ----------
        print("   -> ⚠️ Verificando si hay reCAPTCHA para resolver...")
        solved = _solve_semrush_recaptcha_iframe(driver, wait, user_agent=user_agent, max_attempts=2)
        if solved:
            print("   -> ✅ reCAPTCHA resuelto correctamente.")
        else:
            print("   -> (No hubo captcha o no se pudo resolver; continuo el flujo de todas formas)")

        # ---------- Continuamos con el correo de activación ----------
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

        # ====== NUEVO: resolver un posible 2º reCAPTCHA ======
        time.sleep(2)  # darle tiempo a montar overlay post-verificación
        print("\n   -> ⚠️ Verificando si apareció un segundo reCAPTCHA…")
        second_ok = _solve_semrush_recaptcha_iframe(driver, wait, user_agent=user_agent, max_attempts=2)
        if second_ok:
            print("   -> ✅ Segundo reCAPTCHA resuelto correctamente.")
        else:
            print("   -> (No hubo segundo captcha o no se pudo resolver; continuo el flujo).")
        # =====================================================

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

            # 0) Asegurarnos de que no haya overlays por encima
            try:
                WebDriverWait(driver, 5).until_not(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '.modal-backdrop, .ReactModal__Overlay, [data-test="modal"]'))
                )
            except TimeoutException:
                pass

            # 1) Localizar el INPUT radio "Otros" y su LABEL ancestro
            other_input = short_wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[data-test="other"]'))
            )
            # El patrón común del UI es que el input esté dentro de un label -> lo buscamos por xpath
            label_for_other = driver.find_elements(By.XPATH, '//input[@data-test="other"]/ancestor::label[1]')
            target = label_for_other[0] if label_for_other else other_input

            # 2) Scroll suave y primer intento de click normal sobre el LABEL (o el input si no hay label)
            driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", target)
            time.sleep(0.3)

            clicked = False
            for attempt in range(1, 4):
                try:
                    # intento 1/2/3: clic normal
                    target.click()
                    clicked = True
                    break
                except Exception:
                    # intento con JS si fue interceptado
                    try:
                        driver.execute_script("arguments[0].click();", target)
                        clicked = True
                        break
                    except Exception:
                        time.sleep(0.4)

            if not clicked:
                raise TimeoutException("No se pudo clicar la opción 'Otros' ni con JS.")

            # 3) Verificar selección (algunas UIs marcan 'checked' o aria-checked en un wrapper)
            is_checked = False
            try:
                is_checked = other_input.is_selected()
            except Exception:
                pass

            if not is_checked:
                # chequeo alterno: buscar el wrapper role="radio" seleccionado
                try:
                    wrapper = driver.find_element(By.XPATH, '//input[@data-test="other"]/ancestor::*[@role="radio"][1]')
                    aria = wrapper.get_attribute("aria-checked") or ""
                    is_checked = aria.lower() == "true"
                except Exception:
                    pass

            if not is_checked:
                # último empujón: click JS directo al input
                driver.execute_script("arguments[0].click();", other_input)
                time.sleep(0.2)

            # 4) Click en “Empieza a usar Semrush” con fallback JS si hay intercepción
            start_using_button = short_wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-test="marketing-source-page__continue"]'))
            )
            try:
                start_using_button.click()
            except Exception:
                driver.execute_script("arguments[0].click();", start_using_button)

            print("      -> ✅ Opción 'Otros' seleccionada y continuado correctamente.")

        except TimeoutException:
            print("      -> No se encontró la pregunta final (paso opcional).")

        # --- ¡NUEVO BLOQUE PARA GUARDAR EN LA BASE DE DATOS! ---
        # --- GUARDAR EN BD ---
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

            # LOGOUT tras registro exitoso
            try:
                print("   -> Intentando exponer el header antes de logout (si fuera necesario)...")
                driver.get("https://es.semrush.com/")
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'body'))
                )
            except Exception:
                pass
            print("   -> Cerrando sesión…")
            _perform_logout(driver, wait)

        except Exception as db_error:
            print(f"      -> 🚨 ERROR al guardar en la base de datos: {db_error}")
            db.rollback()
        finally:
            db.close()

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
