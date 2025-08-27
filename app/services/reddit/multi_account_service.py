import time
from typing import List, Dict, Optional
from app.models.reddit_models import Credential
from app.db.database import get_db_secondary
from .login_service import perform_login_and_setup, run_interaction_loop
from .interaction_service import RedditInteractionService
from .browser_service import BrowserManager

def run_multi_login_flow(
    account_ids: List[int],
    url: str, 
    window_title: str, 
    interaction_minutes: int,
    upvote_from_database_enabled: bool # <-- Nuevo parámetro
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
    print(f"🚀 INICIANDO SERVICIO MULTI-CUENTA PARA {len(account_ids)} CUENTAS.")
    print("="*60)

    db = next(get_db_secondary())
    try:
        # Obtenemos todas las credenciales de una vez para ser más eficientes
        accounts_from_db = db.query(Credential).filter(Credential.id.in_(account_ids)).all()
        account_map = {acc.id: acc for acc in accounts_from_db}
    finally:
        db.close()

    for i, account_id in enumerate(account_ids):
        account = account_map.get(account_id)

        if not account:
            print(f"\n⚠️ CUENTA ID #{account_id}: Saltada (no se encontró en la base de datos).")
            continue

        username = account.username
        password = account.password

        print(f"\n--- ⏳ PROCESANDO CUENTA #{i+1}: '{username}' (ID: {account_id}) ---")
        
        interaction_service: Optional[RedditInteractionService] = None
        browser_manager: Optional[BrowserManager] = None
        
        try:
            driver, browser_manager = perform_login_and_setup(username, password, url, window_title)
            
            if driver and browser_manager:
                interaction_service = RedditInteractionService(driver, username)
                # Pasamos el nuevo parámetro al bucle de cada cuenta
                run_interaction_loop(interaction_service, interaction_minutes, upvote_from_database_enabled)
            else:
                print(f"   -> 🚨 Falló el login para '{username}'. Pasando a la siguiente cuenta.")

        except Exception as e:
            print(f"\n🚨 ERROR FATAL durante el procesamiento de '{username}': {e}")
        finally:
            if interaction_service:
                interaction_service.logout()
            if browser_manager:
                browser_manager.quit_driver()
            
            print(f"--- ✅ FIN DEL PROCESO PARA LA CUENTA: '{username}' ---")
            
            if i < len(account_ids) - 1:
                print("\n... Pausa de 15 segundos antes de la siguiente cuenta ...")
                time.sleep(15)

    print("\n" + "="*60)
    print("🎉 SERVICIO MULTI-CUENTA FINALIZADO.")
    print("="*60)