# app/services/reddit/multi_registration_service.py
import random
import time
import os
from .registration_service import run_registration_flow

def run_multi_registration_flow(count: int, file_path: str, url: str):
    """
    Orquesta el registro de múltiples cuentas.
    Si un correo es rechazado, lo descarta y prueba con uno nuevo hasta
    alcanzar el número de registros exitosos solicitados.
    Aplica una pausa incremental después de cada intento (exitoso o fallido).
    """
    print("\n" + "="*60)
    print(f"🚀 INICIANDO SERVICIO DE REGISTRO MÚLTIPLE | OBJETIVO: {count} CUENTAS.")
    print("="*60)

    try:
        with open(file_path, 'r') as f:
            all_emails = [line.strip() for line in f if line.strip()]
        if len(all_emails) < count:
            print(f"   -> ⚠️  ADVERTENCIA: Se solicitaron {count} registros, pero solo hay {len(all_emails)} correos. Se intentará registrar el máximo posible.")
        print(f"   -> ✅ Se encontraron {len(all_emails)} correos disponibles en '{file_path}'.")
    except FileNotFoundError:
        print(f"   -> 🚨 ERROR: No se encontró el archivo de correos en la ruta: '{file_path}'")
        return {"status": "error", "message": f"Archivo no encontrado: {file_path}"}

    successful_registrations = 0
    used_emails = set()
    # <-- 1. CAMBIO: El tiempo de espera inicial ahora es de 240 segundos.
    pausa_duration = 240

    # Bucle principal: continúa hasta que se alcance el objetivo de registros
    while successful_registrations < count:
        
        available_emails = [email for email in all_emails if email not in used_emails]

        if not available_emails:
            print("   -> 🛑 Se han agotado todos los correos del archivo. No se pueden realizar más registros.")
            break

        email_to_try = random.choice(available_emails)
        used_emails.add(email_to_try)

        print(f"\n--- ⏳ INTENTO DE REGISTRO #{successful_registrations + 1} | Usando correo: '{email_to_try}' ---")
        
        try:
            success = run_registration_flow(email=email_to_try, url=url)
            
            if success:
                successful_registrations += 1
                print(f"   -> ✅ REGISTRO EXITOSO para '{email_to_try}'")
            else:
                # Si el correo fue rechazado, simplemente lo informamos. La pausa se manejará más abajo.
                print(f"   -> 🛑 CORREO RECHAZADO: '{email_to_try}'.")

        except Exception as e:
            # Si ocurre un error inesperado, lo informamos. La pausa se manejará más abajo.
            print(f"   -> 🚨 ERROR INESPERADO en el flujo para '{email_to_try}': {e}")

        # <-- 2. NUEVA LÓGICA: La pausa se unifica y se ejecuta aquí después de CADA intento.
        # Se activa solo si aún no hemos alcanzado el objetivo final de registros.
        if successful_registrations < count:
            print(f"\n   -> ⏸️  Pausa de {pausa_duration} segundos antes del siguiente intento...")
            for i in range(pausa_duration, 0, -1):
                # Imprime el contador en la misma línea
                print(f"\r      Siguiente intento en {i} segundos...  ", end="", flush=True)
                time.sleep(1)
            print("\r                                          \r", end="") # Limpia la línea del contador
            
            # <-- 3. CAMBIO: El incremento ahora es de 60 segundos para la siguiente pausa.
            pausa_duration += 60

    # --- Actualización final del archivo de correos ---
    final_emails_to_keep = [email for email in all_emails if email not in used_emails]
    try:
        with open(file_path, 'w') as f:
            for email in final_emails_to_keep:
                f.write(email + "\n")
        print(f"\n   -> 💾 Archivo '{file_path}' actualizado. Se eliminaron {len(used_emails)} correos usados.")
    except Exception as e:
        print(f"   -> 🚨 ERROR al actualizar el archivo de correos: {e}")

    summary = f"Registro múltiple finalizado. Cuentas creadas exitosamente: {successful_registrations}/{count}."
    print("\n" + "="*60)
    print(f"🎉 {summary}")
    print("="*60)
    
    return {"status": "completed", "message": summary}
