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
    used_emails = set() # Para llevar registro de los correos ya usados (exitosos o fallidos)
    pausa_duration = 240 # <-- ¡CAMBIO! Se inicializa la duración de la pausa aquí.

    # Bucle principal: continúa hasta que se alcance el objetivo de registros
    while successful_registrations < count:
        
        # Filtra los correos disponibles que aún no se han intentado
        available_emails = [email for email in all_emails if email not in used_emails]

        if not available_emails:
            print("   -> 🛑 Se han agotado todos los correos del archivo. No se pueden realizar más registros.")
            break

        # Selecciona un correo aleatorio de la lista de disponibles
        email_to_try = random.choice(available_emails)
        used_emails.add(email_to_try) # Lo marca como usado para no volver a seleccionarlo

        print(f"\n--- ⏳ INTENTO DE REGISTRO #{successful_registrations + 1} | Usando correo: '{email_to_try}' ---")
        
        try:
            success = run_registration_flow(email=email_to_try, url=url)
            
            if success:
                successful_registrations += 1
                print(f"   -> ✅ REGISTRO EXITOSO para '{email_to_try}'")
                
                # Si aún no hemos alcanzado el objetivo, hacemos la pausa
                if successful_registrations < count:
                    # --- BUCLE DE CONTEO REGRESIVO ---
                    print(f"\n   -> ⏸️  Pausa de {pausa_duration} segundos antes del siguiente registro...")
                    for i in range(pausa_duration, 0, -1):
                        # Imprime el contador en la misma línea
                        print(f"\r      Siguiente intento en {i} segundos...  ", end="", flush=True)
                        time.sleep(1)
                    print("\r                                          \r", end="")
                    
                    # <-- ¡CAMBIO! Se incrementa la duración para la siguiente pausa.
                    pausa_duration += 60
            else:
                # Este caso ocurre si el correo fue rechazado por Reddit (error.jpg)
                print(f"   -> 🛑 CORREO RECHAZADO: '{email_to_try}'. Se intentará con un nuevo correo.")
                time.sleep(5) # Pequeña pausa antes del siguiente intento

        except Exception as e:
            print(f"   -> 🚨 ERROR INESPERADO en el flujo para '{email_to_try}': {e}")
            time.sleep(20) # Pausa más larga si hay un error grave

    # --- Actualización final del archivo de correos ---
    final_emails_to_keep = [email for email in all_emails if email not in used_emails]
    try:
        with open(file_path, 'w') as f:
            for email in final_emails_to_keep:
                f.write(email + "\n")
        print(f"\n   -> 💾 Archivo '{file_path}' actualizado. Se eliminaron {len(used_emails)} correos.")
    except Exception as e:
        print(f"   -> 🚨 ERROR al actualizar el archivo de correos: {e}")

    summary = f"Registro múltiple finalizado. Cuentas creadas exitosamente: {successful_registrations}/{count}."
    print("\n" + "="*60)
    print(f"🎉 {summary}")
    print("="*60)
    
    return {"status": "completed", "message": summary}