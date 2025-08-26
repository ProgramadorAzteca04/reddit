# app/services/reddit/post_creator_service.py
from selenium.webdriver.common.keys import Keys
from typing import Optional
import time
import os
import pyautogui
import traceback
from .login_service import perform_login_and_setup
from .interaction_service import RedditInteractionService
from .desktop_service import PyAutoGuiService
from app.services.openai.content_generator_service import generate_post_content
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


# 2. COMANDOS JAVASCRIPT
# ----------------------
CLICK_CREATE_POST_JS = """
const el = document.getElementById('create-post');
if (el) {
  ['pointerdown','mousedown','mouseup','click'].forEach(type =>
    el.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window}))
  );
  return 'SUCCESS: El botón para crear post fue encontrado y se hizo clic.';
} else {
  return 'ERROR: No se encontró el elemento con ID "create-post".';
}
"""

# === ESCRITURA DEL TÍTULO (parametrizado) ===
TITLE_FILL_JS = """
const titleValue = arguments[0];
const hostTitulo = document.querySelector('faceplate-textarea-input[name="title"]');
if (!hostTitulo) { return 'NO_HOST'; }
const sr = hostTitulo.shadowRoot;
if (!sr) { return 'NO_SHADOW'; }
const textareaTitulo = sr.querySelector('#innerTextArea');
if (!textareaTitulo) { return 'NO_TEXTAREA'; }
textareaTitulo.value = titleValue;
textareaTitulo.dispatchEvent(new Event('input', { bubbles: true }));
textareaTitulo.dispatchEvent(new Event('change', { bubbles: true }));
textareaTitulo.focus();
return 'OK';
"""
# === ESCRITURA DEL CUERPO (parametrizado) ===
BODY_FILL_JS = """
const bodyText = arguments[0];
const editor = document.querySelector('div[contenteditable="true"][name="body"]');
if (!editor) { return 'NO_EDITOR'; }
editor.focus();
const success = document.execCommand("insertText", false, bodyText);
if (success) {
    editor.dispatchEvent(new Event('input', { bubbles: true }));
    editor.dispatchEvent(new Event('change', { bubbles: true }));
    return 'OK';
} else {
    return 'EXEC_COMMAND_FAILED';
}
"""

# --- Helper para normalizar el prefijo "u/" ---
def _user_prefixed(username: str) -> str:
    u = (username or "").strip()
    if not u:
        return "u/"
    if u.lower().startswith("u/"):
        return "u/" + u.split("/", 1)[1]
    return "u/" + u

# 3. FUNCIÓN DE SERVICIO
# ----------------------
def execute_create_post_flow(username: str = "", password: str = "", topic: str = "Beneficios de la IA en la vida diaria") -> dict:
    """
    Orquesta el flujo completo: genera contenido sobre un tema, inicia sesión en Reddit
    y prepara una publicación con el contenido generado.
    """
    print("\n" + "="*60)
    print("🚀 INICIANDO SERVICIO: Flujo completo para crear y publicar en Reddit.")
    print("="*60)

    # ================================================================
    # PASO 0: GENERAR CONTENIDO CON OPENAI
    # ================================================================
    print(f"   -> Generando contenido para el tema: '{topic}'...")
    generated_content = generate_post_content(topic)

    if "Error" in generated_content["title"]:
        error_msg = f"No se pudo generar contenido de OpenAI: {generated_content['body']}"
        print(f"   -> 🚨 {error_msg}")
        return {"status": "error", "message": error_msg}

    title = generated_content["title"]
    body = generated_content["body"]
    print("   -> ✅ Contenido generado exitosamente.")

    LOGIN_URL = "https://www.reddit.com/login"
    WINDOW_TITLE = "Reddit"
    
    interaction_service: Optional[RedditInteractionService] = None
    browser_manager = None
    pyautogui_service = PyAutoGuiService()

    try:
        if not password:
            raise ValueError("El parámetro 'password' es obligatorio para iniciar sesión.")

        # ================================================================
        # PASO 1: LOGIN Y PREPARACIÓN
        # ================================================================
        driver, browser_manager = perform_login_and_setup(username, password, LOGIN_URL, WINDOW_TITLE)
        if not driver or not browser_manager:
            raise RuntimeError("El proceso de login falló. No se puede continuar.")
        
        print(f"   -> Login completado exitosamente como '{username}'.")
        interaction_service = RedditInteractionService(driver)
        interaction_service.prepare_page()
        time.sleep(3)

        # ================================================================
        # PASO 2: ABRIR EL EDITOR DE PUBLICACIONES
        # ================================================================
        print("   -> Ejecutando script para hacer clic en 'Crear publicación'...")
        result = driver.execute_script(CLICK_CREATE_POST_JS)
        print(f"   -> Resultado del script: {result}")
        if "ERROR" in result:
            return {"status": "error", "message": result}
        time.sleep(5)

        # ================================================================
        # PASO 3: SELECCIONAR LA COMUNIDAD (EL PERFIL DEL USUARIO)
        # ================================================================
        print("   -> Buscando el botón para seleccionar comunidad con PyAutoGUI...")
        community_images = ["select_community.png"]
        if not pyautogui_service.find_and_click_humanly(community_images, confidence=0.8, attempts=3, wait_time=2):
            error_msg = "PyAutoGUI no pudo encontrar el botón 'select_community.png'."
            print(f"   -> 🚨 {error_msg}")
            return {"status": "error", "message": error_msg}
        
        print("   -> ✅ Clic inicial con PyAutoGUI exitoso.")
        time.sleep(1.5)
        target_profile = _user_prefixed(username)
        print(f"   -> Escribiendo '{target_profile}' con PyAutoGUI...")
        pyautogui.write(target_profile, interval=0.1)
        time.sleep(2)
        
        try:
            print("   -> Usando Selenium para enviar teclas al elemento activo...")
            active_element = driver.switch_to.active_element
            print("   -> Presionando 'Flecha Abajo' con Selenium...")
            active_element.send_keys(Keys.ARROW_DOWN)
            time.sleep(1.5)
            print("   -> Presionando 'Enter' con Selenium...")
            active_element.send_keys(Keys.ENTER)
            print("   -> ✅ Comunidad seleccionada exitosamente.")
        except Exception as e:
            error_msg = f"Selenium no pudo enviar las teclas de acción. Error: {e}"
            print(f"   -> 🚨 {error_msg}")
            traceback.print_exc()
            return {"status": "error", "message": error_msg}
        
        # ================================================================
        # PASO 4 Y 5: ESCRIBIR TÍTULO Y CUERPO
        # ================================================================
        time.sleep(1.6)
        print(f"   -> Escribiendo el título: '{title}'...")
        result_title = driver.execute_script(TITLE_FILL_JS, title)
        print(f"   -> Resultado del script del título: {result_title}")
        if result_title != 'OK':
            error_msg = f"No se pudo escribir en el campo del título. Script devolvió: {result_title}"
            return {"status": "error", "message": error_msg}
        
        print("   -> ✅ Título escrito correctamente.")
        print(f"   -> Escribiendo en el cuerpo del post...")
        driver.execute_script(BODY_FILL_JS, body)
        time.sleep(0.5)
        result_body = driver.execute_script(BODY_FILL_JS, body) # Segundo intento para robustez
        if result_body != 'OK':
            error_msg = f"No se pudo escribir en el cuerpo del post. Script devolvió: {result_body}"
            return {"status": "error", "message": error_msg}

        print("   -> ✅ Cuerpo del post escrito correctamente.")
        
        # ================================================================
        # PASO 6: PUBLICAR EL POST
        # ================================================================
        time.sleep(3)
        print("   -> Buscando el botón para publicar el post con PyAutoGUI...")
        publish_images = ["publicar.png"]
        if not pyautogui_service.find_and_click_humanly(publish_images, confidence=0.8, attempts=3, wait_time=2):
            error_msg = "No se pudo encontrar el botón 'publicar.png' en la pantalla."
            print(f"   -> 🚨 {error_msg}")
            return {"status": "error", "message": error_msg}
        print("   -> ✅ ¡Post publicado exitosamente!")
        
        # ================================================================
        # PASO 7: OBTENER URL DE CONFIRMACIÓN
        # ================================================================
        print("   -> ⏳ Esperando que cargue la primera publicación del feed...")
        try:
            wait = WebDriverWait(driver, 20)
            first_post_element = wait.until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "shreddit-post"))
            )
            
            permalink = first_post_element.get_attribute("permalink")
            post_url = f"https://www.reddit.com{permalink}"
            
            print(f"   -> ✅ ¡Primera publicación encontrada!")
            print(f"   -> 🔗 URL de la publicación capturada: {post_url}")

            if "/comments/" in post_url:
                return {
                    "status": "success",
                    "message": f"Post para '{target_profile}' publicado y verificado exitosamente.",
                    "post_url": post_url
                }
            else:
                raise Exception("El permalink extraído no parece ser una URL de publicación válida.")

        except TimeoutException:
            error_msg = "El post fue publicado, pero no se encontró ninguna publicación en el feed para obtener la URL. La página tardó demasiado en cargar o está vacía."
            print(f"   -> 🚨 {error_msg}")
            return {
                "status": "success_with_warning",
                "message": error_msg,
                "post_url": driver.current_url
            }
        except Exception as e:
            error_msg = f"Ocurrió un error inesperado al intentar extraer la URL: {e}"
            print(f"   -> 🚨 {error_msg}")
            return {
                "status": "error",
                "message": error_msg,
                "post_url": driver.current_url
            }

    except Exception as e:
        print(f"\n🚨 ERROR FATAL en el servicio de crear post: {e}")
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

    finally:
        if interaction_service:
            print("   -> Cerrando la sesión...")
            interaction_service.logout()
        if browser_manager:
            browser_manager.quit_driver()
        print("="*60)
        print("✅ SERVICIO FINALIZADO: Flujo para crear publicación.")
        print("="*60 + "\n")