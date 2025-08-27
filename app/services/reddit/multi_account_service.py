import time
from typing import List, Dict, Optional

# Reutilizamos los servicios que ya existen
from .login_service import perform_login_and_setup, run_interaction_loop
from .interaction_service import RedditInteractionService
from .browser_service import BrowserManager

def run_multi_login_flow(
    accounts: List[Dict[str, str]], 
    url: str, 
    window_title: str, 
    interaction_minutes: int
):
    """
    Orquesta un flujo de login para múltiples cuentas, una tras otra.
    
    Para cada cuenta en la lista, este servicio:
    1. Abre el navegador y realiza el login.
    2. Ejecuta un bucle de interacción aleatoria.
    3. Realiza el logout.
    4. Cierra el navegador por completo.
    5. Pasa a la siguiente cuenta.
    """
    print("\n" + "="*60)
    print(f"🚀 INICIANDO SERVICIO MULTI-CUENTA PARA {len(accounts)} CUENTAS.")
    print("="*60)

    for i, account in enumerate(accounts):
        username = account.get("username")
        password = account.get("password")

        if not username or not password:
            print(f"\n⚠️ CUENTA #{i+1}: Saltada (datos incompletos).")
            continue

        print(f"\n--- ⏳ PROCESANDO CUENTA #{i+1}: '{username}' ---")
        
        interaction_service: Optional[RedditInteractionService] = None
        browser_manager: Optional[BrowserManager] = None
        
        try:
            # Reutilizamos la función de login existente
            driver, browser_manager = perform_login_and_setup(username, password, url, window_title)
            
            if driver and browser_manager:
                # Si el login fue exitoso, iniciamos la interacción
                interaction_service = RedditInteractionService(driver)
                run_interaction_loop(interaction_service, interaction_minutes)
            else:
                print(f"   -> 🚨 Falló el login para '{username}'. Pasando a la siguiente cuenta.")

        except Exception as e:
            print(f"\n🚨 ERROR FATAL durante el procesamiento de '{username}': {e}")
        finally:
            # Este bloque se asegura de que todo se cierre correctamente para esta cuenta
            if interaction_service:
                interaction_service.logout()
            if browser_manager:
                browser_manager.quit_driver()
            
            print(f"--- ✅ FIN DEL PROCESO PARA LA CUENTA: '{username}' ---")
            
            # Pausa opcional entre cuentas
            if i < len(accounts) - 1:
                print("\n... Pausa de 15 segundos antes de la siguiente cuenta ...")
                time.sleep(15)

    print("\n" + "="*60)
    print("🎉 SERVICIO MULTI-CUENTA FINALIZADO.")
    print("="*60)