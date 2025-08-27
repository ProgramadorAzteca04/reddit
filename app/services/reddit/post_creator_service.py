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
from app.models.reddit_models import Post, Credential
# --- Importaciones para la Base de Datos ---
from app.db.database import get_db_secondary
from app.models.reddit_models import Post

# --- Comandos Javascript (sin cambios) ---
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

# --- Función Principal del Servicio ---
def execute_create_post_flow(credential_id: int) -> dict:
    """
    Orquesta el flujo completo: genera contenido, inicia sesión, publica en Reddit y guarda en la BD.
    """
    print("\n" + "="*60)
    print("🚀 INICIANDO SERVICIO: Flujo completo para crear y publicar en Reddit.")
    print("="*60)

    db = next(get_db_secondary())
    try:
        credential = db.query(Credential).filter(Credential.id == credential_id).first()
        if not credential:
            raise ValueError(f"No se encontró ninguna credencial con el ID: {credential_id}")
        
        username = credential.username
        password = credential.password
        print(f"   -> Credenciales encontradas para el usuario: '{username}' (ID: {credential_id})")

    finally:
        db.close()
    
    # Paso 0: Generar Contenido (ahora sin pasarle un tema)
    print("   -> Generando contenido con tema automático...")
    generated_content = generate_post_content()
    if "Error" in generated_content["title"]:
        error_msg = f"No se pudo generar contenido de OpenAI: {generated_content['body']}"
        return {"status": "error", "message": error_msg}
    title = generated_content["title"]
    body = generated_content["body"]
    print("   -> ✅ Contenido generado exitosamente.")

    # Inicialización de servicios
    LOGIN_URL = "https://www.reddit.com/login"
    WINDOW_TITLE = "Reddit"
    interaction_service: Optional[RedditInteractionService] = None
    browser_manager = None
    pyautogui_service = PyAutoGuiService()
    
    try:
        if not password:
            raise ValueError("El parámetro 'password' es obligatorio para iniciar sesión.")

        # Paso 1: Login y Preparación
        driver, browser_manager = perform_login_and_setup(username, password, LOGIN_URL, WINDOW_TITLE)
        if not driver or not browser_manager:
            raise RuntimeError("El proceso de login falló. No se puede continuar.")
        
        print(f"   -> Login completado exitosamente como '{username}'.")
        interaction_service = RedditInteractionService(driver, username)
        
        interaction_service.prepare_page()
        time.sleep(3)

        # Paso 2: Abrir el Editor de Publicaciones
        print("   -> Ejecutando script para hacer clic en 'Crear publicación'...")
        result = driver.execute_script(CLICK_CREATE_POST_JS)
        print(f"   -> Resultado del script: {result}")
        if "ERROR" in result:
            return {"status": "error", "message": result}
        time.sleep(5)

        # Paso 3: Seleccionar Comunidad (Perfil del Usuario)
        print("   -> Buscando el botón para seleccionar comunidad con PyAutoGUI...")
        community_images = ["select_community.png"]
        if not pyautogui_service.find_and_click_humanly(community_images, confidence=0.8, attempts=3, wait_time=2):
            return {"status": "error", "message": "No se pudo encontrar 'select_community.png'."}
        
        time.sleep(1.5)
        target_profile = _user_prefixed(username)
        pyautogui.write(target_profile, interval=0.1)
        time.sleep(2)
        
        try:
            active_element = driver.switch_to.active_element
            active_element.send_keys(Keys.ARROW_DOWN)
            time.sleep(1.5)
            active_element.send_keys(Keys.ENTER)
            print("   -> ✅ Comunidad seleccionada exitosamente.")
        except Exception as e:
            raise RuntimeError(f"Selenium no pudo enviar las teclas de acción. Error: {e}")
        
        # Pasos 4 y 5: Escribir Título y Cuerpo
        time.sleep(1.6)
        print(f"   -> Escribiendo el título: '{title}'...")
        if driver.execute_script(TITLE_FILL_JS, title) != 'OK':
            raise RuntimeError("No se pudo escribir en el campo del título.")
        
        print("   -> ✅ Título escrito correctamente.")
        if driver.execute_script(BODY_FILL_JS, body) != 'OK':
            # Segundo intento para robustez
            time.sleep(0.5)
            if driver.execute_script(BODY_FILL_JS, body) != 'OK':
                raise RuntimeError("No se pudo escribir en el cuerpo del post.")
        print("   -> ✅ Cuerpo del post escrito correctamente.")
        
        # Paso 6: Publicar
        time.sleep(3)
        if not pyautogui_service.find_and_click_humanly(["publicar.png"], confidence=0.8):
            raise RuntimeError("No se pudo encontrar el botón 'publicar.png'.")
        print("   -> ✅ ¡Post publicado exitosamente!")
        
        # Paso 7: Obtener URL y Guardar en la Base de Datos
        print("   -> ⏳ Esperando que cargue la primera publicación del feed...")
        try:
            wait = WebDriverWait(driver, 20)
            post_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "shreddit-post")))
            
            permalink = post_element.get_attribute("permalink")
            post_url = f"https://www.reddit.com{permalink}"
            
            print(f"   -> ✅ ¡Primera publicación encontrada!")
            print(f"   -> 🔗 URL de la publicación capturada: {post_url}")

            if "/comments/" in post_url:
                # --- LÓGICA DE GUARDADO CORREGIDA ---
                print("\n--- Guardando post en la base de datos ---")
                db = next(get_db_secondary())
                try:
                    # Corrección: El ID del post está en la posición 4 cuando se publica en un perfil.
                    path_parts = permalink.strip('/').split('/')
                    # path_parts: ['user', 'Username', 'comments', 'post_id', 'title']
                    # o ['r', 'subreddit', 'comments', 'post_id', 'title']
                    post_id = path_parts[3] if path_parts[2] == 'comments' else path_parts[4]

                    print(f"   -> ID del Post extraído: {post_id}")
                    
                    db_post = Post(
                        id=post_id,
                        title=title,
                        subreddit=target_profile,
                        author=username,
                        post_url=post_url,
                    )
                    
                    db.add(db_post)
                    db.commit()
                    print("   -> ✅ Post guardado exitosamente en la base de datos.")
                except Exception as db_error:
                    print(f"   -> 🚨 ERROR al guardar en la base de datos: {db_error}")
                    db.rollback()
                finally:
                    db.close()
                # -----------------------------------------------

                return {"status": "success", "message": "Post publicado y guardado.", "post_url": post_url}
            else:
                raise ValueError("El permalink no parece ser una URL de post válida.")

        except TimeoutException:
            return {"status": "success_with_warning", "message": "Post publicado, pero no se pudo verificar la URL."}
        except Exception as e:
            return {"status": "error", "message": f"Error verificando la URL o guardando en BD: {e}"}

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