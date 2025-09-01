# app/services/reddit/multi_account_service.py
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
    upvote_from_database_enabled: bool,
    repost_from_feed_enabled: bool
):
    """
    Orquesta un flujo de login para múltiples cuentas, una tras otra,
    verificando la maduración de cada una.
    """
    print("\n" + "="*60)
    print(f"🚀 INICIANDO SERVICIO MULTI-CUENTA PARA {len(account_ids)} CUENTAS.")
    print("="*60)

    db = next(get_db_secondary())
    try:
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
        is_mature = account.maduracion

        print(f"\n--- ⏳ PROCESANDO CUENTA #{i+1}: '{username}' (ID: {account_id}) ---")
        print(f"    -> Estado de maduración: {'✅ MADURA' if is_mature else '❌ NO MADURA'}")

        interaction_service: Optional[RedditInteractionService] = None
        browser_manager: Optional[BrowserManager] = None
        
        try:
            driver, browser_manager = perform_login_and_setup(username, password, url, window_title)
            
            if driver and browser_manager:
                interaction_service = RedditInteractionService(driver, username)
                # --- CAMBIO AÑADIDO ---
                # Se corrige el nombre del parámetro de 'interaction_service' a 'service'.
                run_interaction_loop(
                    service=interaction_service, 
                    duration_minutes=interaction_minutes, 
                    upvote_from_database_enabled=upvote_from_database_enabled,
                    repost_from_feed_enabled=repost_from_feed_enabled,
                    comment_on_feed_enabled=is_mature
                )
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