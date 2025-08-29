# app/services/email_reader_service.py
import os
import sys
import mailbox
import re
import time
import subprocess  # <-- Importación nueva
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from email.header import decode_header

# --- NUEVA CONSTANTE: RUTA A THUNDERBIRD ---
# Cambia esta ruta si tu Thunderbird está instalado en otro lugar.
THUNDERBIRD_PATH = r"C:\Program Files\Mozilla Thunderbird\thunderbird.exe"

# ----------------------- Nueva Función de Sincronización ----------------------- #

def _open_and_sync_thunderbird(duration_seconds: int = 30):
    """Abre Thunderbird, espera para que sincronice y luego lo cierra de forma segura."""
    if not os.path.exists(THUNDERBIRD_PATH):
        print(f"⚠️ No se encontró el ejecutable de Thunderbird en: {THUNDERBIRD_PATH}")
        print("   -> Saltando la sincronización. Se leerán los correos locales existentes.")
        return

    process = None
    try:
        print(f"\n⚡ Abriendo Thunderbird para sincronizar por {duration_seconds} segundos...")
        process = subprocess.Popen([THUNDERBIRD_PATH])
        # Barra de progreso para la espera
        for i in range(duration_seconds):
            time.sleep(1)
            progress = i + 1
            print(f"\r   -> Sincronizando... [{progress}/{duration_seconds}s]", end="")
        print("\n   -> Tiempo de sincronización finalizado.")

    except Exception as e:
        print(f"🚨 Error al intentar abrir Thunderbird: {e}")
    finally:
        if process:
            print("   -> Cerrando Thunderbird...")
            process.terminate()  # Intenta cerrar amistosamente primero
            try:
                process.wait(timeout=5)  # Espera 5 segundos a que cierre
            except subprocess.TimeoutExpired:
                print("   -> Thunderbird no respondió, forzando el cierre.")
                process.kill()  # Si no cierra, lo fuerza
            print("   -> Thunderbird cerrado.\n")


# ----------------------- Utilidades (sin cambios) ----------------------- #

def _guess_profile_dir():
    """Intenta adivinar el directorio de perfiles de Thunderbird más reciente."""
    base_appdata = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Thunderbird", "Profiles")
    if not os.path.isdir(base_appdata):
        raise FileNotFoundError("No se encontró Thunderbird en AppData/Roaming/Thunderbird/Profiles")
    
    candidates = [os.path.join(base_appdata, n) for n in os.listdir(base_appdata) if n.endswith(".default-release")]
    if not candidates:
        candidates = [os.path.join(base_appdata, n) for n in os.listdir(base_appdata) if os.path.isdir(os.path.join(base_appdata, n))]
    
    if not candidates:
        raise FileNotFoundError("No se encontró ningún perfil de Thunderbird.")
    
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]

def _parse_eml(path):
    with open(path, "rb") as f:
        return BytesParser(policy=policy.default).parse(f)

def _parse_mbox(path):
    try:
        mbox = mailbox.mbox(path, create=False)
        for msg in mbox:
            yield msg
    except Exception:
        return

def _is_probable_mbox_file(path):
    if not os.path.isfile(path):
        return False
    base = os.path.basename(path)
    if base.endswith(".msf") or "." in base:
        return False
    try:
        return os.path.getsize(path) > 0
    except Exception:
        return False

def _decode_header_value(value: str) -> str:
    if not value: return ""
    parts = decode_header(value)
    chunks = []
    for txt, enc in parts:
        try:
            chunks.append(txt.decode(enc or "utf-8", errors="replace") if isinstance(txt, bytes) else txt)
        except Exception:
            chunks.append(str(txt) if not isinstance(txt, bytes) else txt.decode("utf-8", errors="replace"))
    return "".join(chunks).strip()

def _get_datetime(date_header):
    if not date_header: return None
    try:
        return parsedate_to_datetime(date_header)
    except Exception:
        return None

def _get_body_text(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return " ".join((part.get_content() or "").split())
                except Exception:
                    continue
    try:
        body = msg.get_body(preferencelist=("plain", "html"))
        content = body.get_content()
        if body.get_content_type() == "text/html":
            content = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", content)
            content = re.sub(r"(?is)<[^>]+>", " ", content)
        return " ".join(content.split())
    except Exception:
        return ""

def _collect_messages(profile_dir):
    results = []
    roots = [os.path.join(profile_dir, "ImapMail"), os.path.join(profile_dir, "Mail")]
    for root_candidate in roots:
        if not os.path.isdir(root_candidate): continue
        for root, _, files in os.walk(root_candidate):
            if root.lower().endswith(".mozmsgs"):
                for name in files:
                    if name.lower().endswith((".eml", ".wdseml")):
                        try:
                            results.append(_parse_eml(os.path.join(root, name)))
                        except Exception:
                            continue
            else:
                for name in files:
                    path = os.path.join(root, name)
                    if _is_probable_mbox_file(path):
                        for msg in _parse_mbox(path) or []:
                            results.append(msg)
    return results

def _extract_six_digits_from_msg(msg):
    subject = _decode_header_value(msg.get("Subject"))
    m_subject = re.search(r"\b(\d{6})\b", subject)
    if m_subject: return m_subject.group(1)
    body = _get_body_text(msg)
    m_body = re.search(r"\b(\d{6})\b", body)
    if m_body: return m_body.group(1)
    return None

# ----------------------- Función Principal del Servicio (Modificada) ----------------------- #

def get_latest_verification_code(profile_path: str = None, timeout_seconds: int = 60) -> str | None:
    """
    Abre Thunderbird para sincronizar, luego busca el correo de verificación más reciente y devuelve el código.
    """
    # --- PASO AÑADIDO: ABRIR, SINCRONIZAR Y CERRAR THUNDERBIRD ---
    _open_and_sync_thunderbird(duration_seconds=60)
    # ----------------------------------------------------------------

    print(f"📧 Buscando código de verificación de 6 dígitos en los correos de Thunderbird...")
    start_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        try:
            profile = profile_path or _guess_profile_dir()
            all_messages = _collect_messages(profile)

            verification_emails = []
            for msg in all_messages:
                subj = _decode_header_value(msg.get("Subject", ""))
                if "verification" in subj.lower() or "verificación" in subj.lower():
                    dt = _get_datetime(msg.get("Date"))
                    verification_emails.append((dt, msg))
            
            if not verification_emails:
                print(f"   -> No se han encontrado correos de verificación. Reintentando en 5 segundos...")
                time.sleep(5)
                continue

            verification_emails.sort(key=lambda t: (t[0] is not None, t[0]), reverse=True)
            latest_msg = verification_emails[0][1]
            code = _extract_six_digits_from_msg(latest_msg)

            if code:
                print(f"✅ Código de verificación encontrado: {code}")
                return code
            else:
                print(f"   -> Correo de verificación encontrado, pero sin código. Reintentando...")

        except Exception as e:
            print(f"⚠️ Error al leer los correos: {e}. Reintentando...")
        
        time.sleep(5)
    
    print("❌ No se pudo encontrar el código de verificación después de varios intentos.")
    return None