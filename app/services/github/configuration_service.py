# app/services/github/config_service.py
import time
import os
import traceback
import random
from app.services.reddit.browser_service import BrowserManagerProxy
from app.services.reddit.proxy_service import ProxyManager
from app.services.reddit.desktop_service import DesktopUtils
from app.db.database import get_db_secondary
from app.models.git import Credential as GitCredential
# --- IMPORTACIONES DE IA ACTUALIZADAS ---
from app.services.openai.git_ia_generator import generate_north_american_name, generate_tech_bio

# Reutilizando las funciones y helpers del servicio de login
from .login_service import perform_github_login, _perform_github_logout, _human_click, _human_type_into

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC

def _perform_github_logout_from_profile(driver, wait) -> bool:
    """
    Realiza el cierre de sesión desde la página de perfil, usando los nuevos selectores.
    """
    try:
        # 1. Clic en el botón de perfil/avatar para abrir el nuevo menú
        profile_button_locator = (By.CSS_SELECTOR, "button[aria-label='Open user navigation menu']")
        if not _human_click(wait, driver, profile_button_locator, "botón de perfil (nuevo)"):
            return False
        
        time.sleep(1) # Espera a que el menú desplegable aparezca

        # 2. Clic en el enlace "Sign out"
        sign_out_locator = (By.CSS_SELECTOR, "a[href='/logout']")
        if not _human_click(wait, driver, sign_out_locator, "enlace 'Sign out'"):
            return False
        
        # 3. Clic en el botón de confirmación final
        print("   -> ⏳ Esperando la página de confirmación de cierre de sesión...")
        final_logout_locator = (By.CSS_SELECTOR, "input[type='submit'][value='Sign out from all accounts']")
        if not _human_click(wait, driver, final_logout_locator, "botón 'Sign out from all accounts'"):
            print("   -> ⚠️ No se pudo hacer clic en el botón de confirmación final.")
        
        print("   -> ✅ Cierre de sesión completado.")
        return True
    except Exception as e:
        print(f"   -> 🚨 Error durante el cierre de sesión desde el perfil: {e}")
        return False


def run_github_config_flow(credential_id: int):
    """
    Orquesta un flujo de configuración de cuenta:
    1. Inicia sesión.
    2. Navega al perfil del usuario.
    3. Edita el nombre, la biografía y los pronombres del perfil.
    4. Cierra sesión.
    """
    print("\n" + "="*60)
    print(f"🚀 INICIANDO FLUJO: Configuración de cuenta en GitHub para la credencial ID #{credential_id}.")
    print("="*60)

    # --- 1. Obtener credenciales ---
    db = next(get_db_secondary())
    try:
        credential = db.query(GitCredential).filter(GitCredential.id == credential_id).first()
        if not credential:
            print(f"   -> 🚨 ERROR: No se encontró la credencial de GitHub con ID: {credential_id}")
            return
        
        login_identifier = credential.username
        password = credential.password
        proxy_host = credential.proxy
        proxy_port = credential.port
        
        print(f"   -> ✅ Credenciales encontradas para el usuario: '{login_identifier}'")
    finally:
        db.close()

    # --- 2. Configuración del navegador ---
    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    URL = "https://gist.github.com/starred"
    USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_dev_session_github_config")
    WINDOW_TITLE = "GitHub"

    browser_manager = None
    driver = None

    try:
        # --- 3. Iniciar Navegador ---
        proxy_manager = ProxyManager()
        proxy_config = proxy_manager.get_proxy_by_host_port(proxy_host, proxy_port)
        if not proxy_config:
            print(f"   -> ⚠️ Proxy no encontrado. Usando un proxy aleatorio.")
            proxy_config = proxy_manager.get_random_proxy()

        user_agent = proxy_manager.get_random_user_agent()

        browser_manager = BrowserManagerProxy(
            chrome_path=CHROME_PATH,
            user_data_dir=USER_DATA_DIR,
            port="",
            proxy=proxy_config,
            user_agent=user_agent
        )
        
        driver = browser_manager.get_configured_driver(URL)
        if not driver:
            return

        print(f"\n   -> ✅ Navegador abierto en: {URL}")
        
        time.sleep(5)
        DesktopUtils.get_and_focus_window(WINDOW_TITLE)
        
        wait = WebDriverWait(driver, 30)

        # --- 4. Reutilizar Login ---
        if not perform_github_login(driver, wait, login_identifier, password):
            raise Exception("El proceso de inicio de sesión falló.")
        
        print("\n   -> 🎉 ¡Login completado! Procediendo a la configuración del perfil.")
        time.sleep(5)

        # --- 5. Navegar al Perfil ---
        print("\n   -> 👤 Navegando a la página de perfil...")

        # a. Clic en el botón del avatar
        profile_button_locator = (By.CSS_SELECTOR, "button[aria-label='View profile and more']")
        if not _human_click(wait, driver, profile_button_locator, "botón de perfil (avatar)"):
            raise Exception("No se pudo hacer clic en el botón de perfil.")
        
        time.sleep(1)

        # b. Clic en "Your GitHub profile"
        your_profile_locator = (By.XPATH, "//a[@role='menuitem' and .//span[normalize-space()='Your GitHub profile']]")
        if not _human_click(wait, driver, your_profile_locator, "enlace 'Your GitHub profile'"):
            raise Exception("No se pudo hacer clic en el enlace del perfil.")
            
        print("   -> ✅ Navegación al perfil exitosa.")
        
        # --- 6. Clic en "Edit profile" ---
        print("\n   -> ✏️  Buscando el botón 'Edit profile'...")
        time.sleep(3) # Espera para que la página de perfil cargue completamente

        edit_profile_locator = (By.XPATH, "//button[contains(@class, 'js-profile-editable-edit-button') and normalize-space()='Edit profile']")
        if not _human_click(wait, driver, edit_profile_locator, "botón 'Edit profile'"):
            raise Exception("No se pudo hacer clic en el botón 'Edit profile'.")
        
        print("   -> ✅ Modo de edición de perfil activado.")
        
        # --- 7. Generar y escribir nombre ---
        time.sleep(5) # Espera para que los campos de edición carguen
        
        print("   -> 🤖 Generando un nombre y género con IA...")
        # Decidir aleatoriamente el género para que los pronombres coincidan
        gender_choice = random.choice(["male", "female"])
        full_name = generate_north_american_name(gender=gender_choice)
        
        name_input_locator = (By.ID, "user_profile_name")
        if not _human_type_into(wait, driver, name_input_locator, full_name, "campo de nombre", clear_first=True):
             raise Exception("No se pudo escribir en el campo del nombre.")
        
        print(f"   -> ✅ Nombre '{full_name}' (género: {gender_choice}) introducido correctamente.")

        # --- 8. Generar y escribir biografía ---
        print("   -> 🤖 Generando una biografía con IA...")
        bio = generate_tech_bio(full_name)

        bio_locator = (By.ID, "user_profile_bio")
        if not _human_type_into(wait, driver, bio_locator, bio, "campo de biografía", clear_first=True):
            raise Exception("No se pudo escribir en el campo de la biografía.")

        print(f"   -> ✅ Biografía introducida correctamente.")

        # --- 9. Seleccionar pronombres ---
        print("   -> 👥 Seleccionando pronombres...")
        try:
            pronoun_select_locator = (By.ID, "user_profile_pronouns")
            select_element = wait.until(EC.presence_of_element_located(pronoun_select_locator))
            
            pronoun_dropdown = Select(select_element)
            
            if gender_choice == "male":
                pronoun_value = "he/him"
            else: # female
                pronoun_value = "she/her"
            
            pronoun_dropdown.select_by_value(pronoun_value)
            print(f"   -> ✅ Pronombres '{pronoun_value}' seleccionados.")
            time.sleep(1)

        except Exception as e:
            print(f"   -> ⚠️ No se pudieron seleccionar los pronombres: {e}")
            # No es un error fatal, el flujo puede continuar

        # --- 10. Guardar cambios ---
        print("   -> 💾 Guardando los cambios en el perfil...")
        save_button_locator = (By.XPATH, "//button[normalize-space()='Save changes']")
        if not _human_click(wait, driver, save_button_locator, "botón 'Save changes'"):
            # Opcional: añadir un fallback si el botón no se encuentra
            print("   -> ⚠️ No se encontró el botón 'Save changes', los cambios podrían no guardarse.")
        else:
            print("   -> ✅ Cambios guardados. Esperando 10 segundos para la confirmación.")
            time.sleep(10)

        # --- 11. Reutilizar Logout ---
        print("\n   -> 👋 Iniciando proceso de cierre de sesión desde la página de perfil...")
        if not _perform_github_logout_from_profile(driver, wait):
            print("   -> ⚠️ El proceso de cierre de sesión no pudo completarse.")

    except Exception as e:
        print(f"\n🚨 ERROR FATAL durante el flujo de configuración de GitHub: {e}")
        traceback.print_exc()
    finally:
        if browser_manager:
            browser_manager.quit_driver()
        print("\n" + "="*60)
        print("✅ SERVICIO FINALIZADO: Flujo de configuración de GitHub.")
        print("="*60 + "\n")

