# app/services/email_reader_service.py
import os
import sys
import mailbox
import re
import time
import subprocess
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from email.header import decode_header
from typing import List, Optional

# --- CONSTANTE: RUTA A THUNDERBIRD ---
THUNDERBIRD_PATH = r"C:\Program Files\Mozilla Thunderbird\thunderbird.exe"

# ----------------------- Función de Sincronización ----------------------- #

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
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("   -> Thunderbird no respondió, forzando el cierre.")
                process.kill()
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
    
def _get_html_part(msg):
    """
    Recorre las partes de un correo para encontrar y devolver la parte 'text/html'.
    """
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                return part
    elif msg.get_content_type() == "text/html":
        return msg
    return None

def _extract_semrush_code_from_html(msg):
    """
    Extrae específicamente el código de 6 dígitos de un correo HTML de Semrush.
    """
    html_part = _get_html_part(msg)
    if not html_part:
        return None

    try:
        html_body = html_part.get_payload(decode=True).decode(
            html_part.get_content_charset() or 'utf-8', 
            errors="replace"
        )
        match = re.search(r'class="ct-code".*?>.*?(\d{6}).*?</div>', html_body, re.DOTALL)
        if match:
            code = match.group(1)
            print(f"   -> ✨ Código encontrado con lógica HTML de Semrush: {code}")
            return code
            
    except Exception as e:
        print(f"   -> ⚠️ Error procesando el HTML de Semrush: {e}")
        
    return None

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
                    # Decodificar el contenido si es necesario
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    return payload.decode(charset, errors='replace')
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

# =================================================================================
# NUEVO: Lógica de extracción de códigos mejorada
# =================================================================================
def _extract_verification_code_from_msg(msg) -> Optional[str]:
    """
    Extrae un código de verificación de un correo.
    Prioriza lógicas específicas (GitHub, Semrush) y luego usa una búsqueda genérica.
    """
    from_header = _decode_header_value(msg.get("From", "")).lower()
    subject = _decode_header_value(msg.get("Subject", ""))
    body = _get_body_text(msg)

    # --- Lógica específica para GitHub (8 dígitos) ---
    if "github" in from_header:
        print("   -> 🕵️  Detectado correo de GitHub. Usando lógica específica...")
        # Busca un número de 8 dígitos que esté solo en una línea, como en el .eml
        match = re.search(r'^\s*(\d{8})\s*$', body, re.MULTILINE)
        if match:
            code = match.group(1)
            print(f"   -> ✨ Código de GitHub encontrado: {code}")
            return code

    # --- Lógica específica para Semrush (6 dígitos en HTML) ---
    if "semrush" in from_header:
        print("   -> 🕵️  Detectado correo de Semrush. Usando lógica de HTML...")
        code = _extract_semrush_code_from_html(msg)
        if code:
            return code

    # --- Lógica Genérica (Fallback) ---
    print("   -> ⚙️  Usando lógica de extracción genérica (6-8 dígitos)...")
    # Busca un código de 6 a 8 dígitos en el asunto o en el cuerpo.
    generic_pattern = r"\b(\d{6,8})\b"
    
    match_subject = re.search(generic_pattern, subject)
    if match_subject:
        code = match_subject.group(1)
        print(f"   -> ✨ Código genérico encontrado en el asunto: {code}")
        return code
    
    match_body = re.search(generic_pattern, body)
    if match_body:
        code = match_body.group(1)
        print(f"   -> ✨ Código genérico encontrado en el cuerpo: {code}")
        return code

    return None

# ----------------------- Función Principal del Servicio (Modificada) ----------------------- #

def get_latest_verification_code(
    subject_keywords: List[str],
    profile_path: str = None,
    timeout_seconds: int = 60
) -> Optional[str]:
    """
    Abre Thunderbird para sincronizar, luego busca el correo de verificación más reciente 
    cuyo asunto contenga las palabras clave y devuelve el código.
    """
    _open_and_sync_thunderbird(duration_seconds=60)

    print(f"📧 Buscando código de verificación en los correos de Thunderbird...")
    start_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        try:
            profile = profile_path or _guess_profile_dir()
            all_messages = _collect_messages(profile)

            verification_emails = []
            for msg in all_messages:
                subj = _decode_header_value(msg.get("Subject", "")).lower()
                if any(keyword.lower() in subj for keyword in subject_keywords):
                    dt = _get_datetime(msg.get("Date"))
                    verification_emails.append((dt, msg))
            
            if not verification_emails:
                print(f"   -> No se han encontrado correos de verificación. Reintentando en 5 segundos...")
                time.sleep(5)
                continue

            verification_emails.sort(key=lambda t: (t[0] is not None, t[0]), reverse=True)
            latest_msg = verification_emails[0][1]
            
            # Utiliza la nueva función de extracción mejorada
            code = _extract_verification_code_from_msg(latest_msg)

            if code:
                # No es necesario imprimir aquí, la función de extracción ya lo hace
                return code
            else:
                print(f"   -> Correo de verificación encontrado (Asunto: '{_decode_header_value(latest_msg.get('Subject'))}'), pero no se pudo extraer un código. Reintentando...")

        except Exception as e:
            print(f"⚠️ Error al leer los correos: {e}. Reintentando...")
        
        time.sleep(5)
    
    print("❌ No se pudo encontrar el código de verificación después de varios intentos.")
    return None