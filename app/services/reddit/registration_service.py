# app/services/reddit/registration_service.py
import time
import os
import traceback
import pyperclip
import pyautogui
from .desktop_service import PyAutoGuiService, HumanInteractionUtils
from .browser_service import BrowserManager
from app.services.email_reader_service import get_latest_verification_code

def run_registration_flow(email: str, url: str):
    """Flujo principal que orquesta el registro de una nueva cuenta."""
    CHROME_PATH = r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    browser_manager = BrowserManager(CHROME_PATH, "", "")
    pyautogui_service = PyAutoGuiService()

    try:
        browser_manager.open_chrome_incognito(url)
        time.sleep(5)

        print("\n--- Iniciando Proceso de Registro con PyAutoGUI ---")

        # 1. Ingresar correo con fallback de tabulador
        email_images = ["correo_dark.png", "correo_ligh.png"]
        if not pyautogui_service.find_and_click_humanly(email_images, attempts=2, wait_time=3):
            print("⚠️ No se encontró el campo de correo por imagen. Usando tabulador como alternativa...")
            for _ in range(5):
                pyautogui.press("tab")
                time.sleep(0.5)
        HumanInteractionUtils.type_text_humanly(email)

        # 2. Clic en Continuar
        continue_images = ["continuar1.png", "continuar1_ligh.png"]
        if not pyautogui_service.find_and_click_humanly(continue_images, attempts=5, scroll_on_fail=True):
            raise RuntimeError("No se encontró el primer botón 'Continuar'.")

        # --- PASO MEJORADO: OBTENER Y ESCRIBIR CÓDIGO DE VERIFICACIÓN ---
        print("\n--- Buscando código de verificación por correo ---")
        verification_code = get_latest_verification_code()
        
        if verification_code:
            verification_images = ["verification.png"] # <-- Imagen que se buscará
            print(f"   -> Buscando el campo de verificación con la imagen '{verification_images[0]}'...")
            
            # Intenta hacer clic en la imagen del campo de verificación
            if pyautogui_service.find_and_click_humanly(verification_images, attempts=3, wait_time=2):
                print(f"   -> Campo encontrado. Ingresando código: {verification_code}")
                HumanInteractionUtils.type_text_humanly(verification_code)
                time.sleep(1)
            else:
                # Si no encuentra la imagen, escribe el código directamente como antes
                print(f"⚠️ No se encontró '{verification_images[0]}'. Escribiendo código directamente.")
                HumanInteractionUtils.type_text_humanly(verification_code)
                time.sleep(1)
            
            # Vuelve a presionar Continuar
            pyautogui_service.find_and_click_humanly(continue_images)
        else:
            print("⚠️ No se encontró código de verificación, el flujo podría fallar si se requiere.")
        # --------------------------------------------------

        # 3. Saltar selección de intereses inicial
        skip_images = ["saltar.png", "saltar_ligh.png"]
        pyautogui_service.find_and_click_humanly(skip_images, attempts=10, wait_time=2)

        # 4. Capturar nombre de usuario
        username_images = ["usuario.png", "usuario_ligh.png"]
        if not pyautogui_service.find_and_click_humanly(username_images, attempts=5, wait_time=2):
            raise RuntimeError("No se encontró el campo de nombre de usuario.")
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.5)
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.5)
        username = pyperclip.paste()
        print(f"📋 Nombre de usuario capturado: '{username}'")

        # 5. Ingresar contraseña
        password_images = ["password.png"]
        if not pyautogui_service.find_and_click_humanly(password_images, attempts=5):
            raise RuntimeError("No se encontró el campo de contraseña. Asegúrate de que 'password.png' existe.")
        password = HumanInteractionUtils.generate_password()
        HumanInteractionUtils.type_text_humanly(password)

        # 6. Clic en Continuar (después de la contraseña)
        if not pyautogui_service.find_and_click_humanly(continue_images):
            raise RuntimeError("No se encontró el segundo botón 'Continuar'.")

        # 7. Saltar selección de género
        pyautogui_service.find_and_click_humanly(skip_images)

        # 8. Seleccionar un interés y continuar
        interest_images = ["interes14.png"]
        if pyautogui_service.find_and_click_humanly(interest_images, attempts=10, wait_time=3, scroll_on_fail=True):
            if not pyautogui_service.find_and_click_humanly(continue_images):
                print("⚠️ No se pudo hacer clic en 'Continuar' después de seleccionar intereses.")
        else:
            print("⚠️ No se seleccionó ningún interés.")
            
        print("✅ Registro con PyAutoGUI completado.")
        credentials = {"username": username, "password": password, "email": email}
        
        print("\n" + "="*50)
        print("🎉 ¡REGISTRO EXITOSO! 🎉")
        print(f"Correo: {credentials['email']}")
        print(f"Usuario: {credentials['username']}")
        print(f"Contraseña: {credentials['password']}")
        print("="*50)
        
        return credentials

    except Exception as e:
        print(f"\n🚨 ERROR FATAL en el flujo de registro: {e}")
        traceback.print_exc()
        print("\nProceso de registro abortado.")
    finally:
        print("\nℹ️  El script de registro ha finalizado.")