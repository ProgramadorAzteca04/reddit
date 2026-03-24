from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from pathlib import Path
import io
import os
import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

# === Config ===
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# Mapa original de carpetas (comentado — reemplazado por archivo único)
# CAMPAIGN_TO_FOLDER_MAP: Dict[int, str] = {
#     1:   '1USPG1OiA3VNvgjXJqGRqZOkbDFPTyUih',
#     2:   '1K7Sz-6aA0HMDmVtqQAS9A8n12eT9veIK',
#     3:   '1uOTuodJMoHXO-w_kGddy3LTmJi_RtAUN',
#     4:   '1kDAZrpfb_L4kkxwBdkSKte9XoNtVjBB5',
#     5:   '1JfbnUNTlTYwKDB_5F57T1eUhd5RtOzUy',
#     6:   '1m4b3BJ3CCdldHIrArkJG3-w-DaTUI69F',
#     7:   '1T17NooEgccdIyvMcYOxUkXVGDZleVejs',
#     8:   '1Is9XIHGERN436WkfLmXDTIb16Zbf_OfZ',
#     9:   '1SfJS6nwCGUvrmioDBLcDG01zKt8GB1z-',
#     10:  '1mOM4p84hqkF2mwo7mTJwHrH0VUhEeJMq',
#     12:  '1go_XE8fDrEzexQpRoX9HUXs8FR03aEBK',
#     13:  '1eXaBx8r_qijDmEyqVFudckpqd8lEA1W-',
#     40:  '199sJiYJxKxdC1-Usf3301mY4hHKPNUPY',
#     42:  '1yNcAr9uvOsZ4OGBg3b8SugClZ89JSklQ',
#     43:  '1oVGosUBx7j_t36iAORrTW9eVeuTq2O6-',
#     44:  '12sfC6Hp9LLDeKYBMxGyvVApT6g2_AygA',
#     58:  '1NA8Ytw9nZt1riC47DYh6bIkezUqHXa1Y',
#     59:  '1xOqoPpM9xXQA8uXkCXsdjG2VGEncrXpO',
#     71:  '1auUzEVlCGkYj30OAE3R7AbPniR3bkgoj',
#     72:  '13tVWVJ-OlxJJU3Oipk1d79wA7uBekHl8',
#     75:  '1K7eNmb_L29lInFgJ1lkDT76CMCZWtyMf',
#     109: '1BJGhVlLhmqO4L9LGWwjcDGeq3Al3IbpD',
#     110: '1VBznDJS0sUgX70EZNVB4KV7FXEzoyK3v',
# }

# ID del archivo Google Sheet que contiene todas las campañas por pestaña
FILE_ID = '1eI0ErDM2ZNJLO19NLzd7r9-VH3_VKZgDYJEYcLOMYiM'

CAMPAIGN_TO_FILE_MAP: Dict[int, str] = {
    1:   FILE_ID,
    2:   FILE_ID,
    3:   FILE_ID,
    4:   FILE_ID,
    5:   FILE_ID,
    6:   FILE_ID,
    7:   FILE_ID,
    8:   FILE_ID,
    9:   FILE_ID,
    10:  FILE_ID,
    12:  FILE_ID,
    13:  FILE_ID,
    40:  FILE_ID,
    42:  FILE_ID,
    43:  FILE_ID,
    44:  FILE_ID,
    58:  FILE_ID,
    59:  FILE_ID,
    71:  FILE_ID,
    72:  FILE_ID,
    75:  FILE_ID,
    108: FILE_ID,
    109: FILE_ID,
    110: FILE_ID,
}

# Hoja específica por campaign_id (nombre exacto de la pestaña en el Google Sheet)
CAMPAIGN_TO_SHEET_MAP: Dict[int, str] = {
    1:   'AMARRES EN CHICAGO',
    2:   'BOTANICA DEL AMOR',
    3:   'BOTANICA INDIO AMAZONICO',
    4:   'BOTANICA MAESTROS ESPIRITUALES',
    5:   'BOTANICA EL SECRETO AZTECA',
    6:   'BOTANICA VIRGEN MORENA',
    7:   'Cash Deals Today',
    8:   'Elite Frenchies',
    9:   'EXPRESS CLEAN',
    10:  'Lopez y Lopez Abogados',
    12:  'CHICAGOLAND FENCE PROS',
    13:  'QUICK CLEANING',
    40:  'CHICAGO SECURITY PROS',
    42:  'ELITE CHICAGO FACIALS',
    43:  'SPA 312',
    44:  'CHICAGOLAND FENCE PROS',
    58:  'Boxmark Digital',
    59:  'CLEANING SERVICES CHI',
    71:  'CLEANING SERVICES CHICAGOLAND',
    72:  'CHICAGO COMMERCIAL FENCING',
    75:  'VIDEO STUDIO JIMENEZ IN',
    108: 'Chicago Top Maids',
    109: 'Botanica San Gregorio',
    110: 'Botanica Amarre Amazonico',
}

# Campañas que tienen fila 2 con ciudad Semrush en el Excel.
# Las que NO están aquí leen frases desde fila 2 (comportamiento original).
# Agrega aquí cada campaña cuando actualices su Excel con la fila de ciudad Semrush.
CAMPAIGNS_WITH_SEMRUSH_ROW: Set[int] = {
    2,   # BOTANICA DEL AMOR
    12,  # CHICAGOLAND FENCE PRO
    44,  # CHICAGOLAND FENCE PROS
    71,  # CLEANING SERVICES CHICAGOLAND
    72,  # CHICAGO COMMERCIAL FENCING
    108, # Chicago Top Maids
}

# Campañas donde la ubicación Semrush es fija (no viene de fila 0 ni fila 2).
# Solo para campañas donde TODAS las columnas usan la misma ciudad.
CAMPAIGN_FIXED_CITY: Dict[int, str] = {
    43: 'Chicago, Illinois, United States',  # SPA 312 — columnas son servicios, ciudad siempre Chicago
}


# === Models ===
@dataclass(frozen=True)
class CampaignFolder:
    campaign_id: int
    folder_id: str
    name: str
    is_folder: bool


@dataclass(frozen=True)
class DriveFile:
    id: str
    name: str
    mime_type: str


# === Auth / Client ===
def build_drive_client(
    credentials_json_path: str = "credentials.json",
    token_json_path: str = "token.json",
    scopes: Optional[List[str]] = None
) -> Resource:
    _scopes = scopes or SCOPES
    creds: Optional[Credentials] = None
    if os.path.exists(token_json_path):
        creds = Credentials.from_authorized_user_file(token_json_path, _scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(credentials_json_path).exists():
                raise FileNotFoundError(
                    f"No existe {credentials_json_path}. Descárgalo desde GCP y colócalo en el servidor."
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_json_path, _scopes)
            creds = flow.run_local_server(port=0)
        with open(token_json_path, "w") as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)


# === Core logic ===
def list_available_campaign_folders(
    drive: Resource,
    campaign_map: Dict[int, str] = CAMPAIGN_TO_FILE_MAP
) -> List[CampaignFolder]:
    out: List[CampaignFolder] = []
    for cid, fid in campaign_map.items():
        try:
            meta = drive.files().get(fileId=fid, fields='id,name,mimeType').execute()
            out.append(
                CampaignFolder(
                    campaign_id=cid,
                    folder_id=fid,
                    name=meta.get('name', ''),
                    is_folder=(meta.get('mimeType') == 'application/vnd.google-apps.folder'),
                )
            )
        except HttpError:
            continue
    return out


def _list_folder_files(drive: Resource, folder_id: str) -> List[DriveFile]:
    res = drive.files().list(
        q=f"'{folder_id}' in parents",
        fields="files(id, name, mimeType)"
    ).execute()
    files = res.get('files', []) or []
    return [DriveFile(id=f['id'], name=f['name'], mime_type=f['mimeType']) for f in files]


def _pick_programacion_file(files: List[DriveFile]) -> Optional[DriveFile]:
    upper = [(f, f.name.upper()) for f in files]
    for f, n in upper:
        if 'PROGRAMACION BACKLINS' in n:
            return f
    for f, n in upper:
        if 'PROGRAMACION BACKLINKS' in n:
            return f
    for f, n in upper:
        if 'BACKLINS' in n:
            return f
    for f, n in upper:
        if 'BACKLINKS' in n:
            return f
    return None


def select_campaign_programacion_file(
    drive: Resource,
    campaign_id: int,
    campaign_map: Dict[int, str] = CAMPAIGN_TO_FILE_MAP
) -> Optional[DriveFile]:
    if campaign_id in CAMPAIGN_TO_FILE_MAP:
        file_id = CAMPAIGN_TO_FILE_MAP[campaign_id]
        try:
            meta = drive.files().get(fileId=file_id, fields='id,name,mimeType').execute()
            print(f"   -> ✅ Archivo encontrado para campaña #{campaign_id}: '{meta.get('name')}'")
            return DriveFile(
                id=meta['id'],
                name=meta.get('name', ''),
                mime_type=meta.get('mimeType', '')
            )
        except Exception as e:
            print(f"   -> ⚠️ No se pudo acceder al archivo para campaña #{campaign_id}: {e}")
    raise KeyError(f"campaign_id {campaign_id} no existe en el mapa configurado.")


def download_excel_bytes(drive: Resource, file: DriveFile) -> bytes:
    if file.mime_type == 'application/vnd.google-apps.spreadsheet':
        request = drive.files().export_media(
            fileId=file.id,
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    else:
        request = drive.files().get_media(fileId=file.id)
    bio = io.BytesIO()
    downloader = MediaIoBaseDownload(bio, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    return bio.getvalue()


def read_programacion_dataframe(xlsx_bytes: bytes, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """
    Lee el Excel horizontal sin interpretación de headers.
    Estructura esperada:
    - Fila 0: nombre de columna (ciudad o servicio)
    - Fila 1: URL de home
    - Fila 2: ciudad Semrush (SOLO si campaign_id está en CAMPAIGNS_WITH_SEMRUSH_ROW)
    - Fila 2 o 3+: frases objetivas (según si existe fila de ciudad Semrush)
    """
    sheet_to_read = 0
    try:
        xls = pd.ExcelFile(io.BytesIO(xlsx_bytes))
        print(f"   -> Hojas encontradas: {xls.sheet_names}")
        if sheet_name and sheet_name in xls.sheet_names:
            sheet_to_read = sheet_name
            print(f"   -> ✅ Leyendo hoja especificada: '{sheet_to_read}'")
        else:
            sheet_map = {name.upper().strip(): name for name in xls.sheet_names}
            if "CIUDADES TRABAJADAS" in sheet_map:
                sheet_to_read = sheet_map["CIUDADES TRABAJADAS"]
                print(f"   -> ✅ Leyendo hoja prioritaria: '{sheet_to_read}'")
            elif "CIUDADES" in sheet_map:
                sheet_to_read = sheet_map["CIUDADES"]
                print(f"   -> ✅ Leyendo hoja: '{sheet_to_read}'")
            else:
                print(f"   -> ⚠️ Hoja '{sheet_name}' no encontrada. Leyendo la primera hoja.")
    except Exception as e:
        print(f"   -> ⚠️ Error inspeccionando hojas ({e}). Leyendo la primera hoja.")

    df = pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=sheet_to_read, header=None)
    return df


def get_available_cities(df: pd.DataFrame) -> List[str]:
    """
    Lee fila 0 como identificadores de columna (ciudad o servicio).
    Retorna lista única y ordenada.
    """
    cities_row = df.iloc[0]
    cities = []
    for val in cities_row:
        if pd.notna(val):
            city = str(val).strip()
            if city and city.lower() not in ("nan", ""):
                cities.append(city)
    cities = sorted(set(cities))
    print(f"   -> Ciudades/columnas encontradas: {cities}")
    return cities


def get_semrush_city_for_column(
    df: pd.DataFrame,
    column_name: str,
    campaign_id: int = 0
) -> str:
    """
    Obtiene la ciudad exacta para escribir en Semrush.
    - Si campaign_id está en CAMPAIGNS_WITH_SEMRUSH_ROW → lee fila 2
    - Si fila 2 está vacía o campaign_id NO está en el set → usa fila 0 (nombre columna)
    """
    cities_row = df.iloc[0]
    for idx, val in enumerate(cities_row):
        if pd.notna(val) and str(val).strip().lower() == column_name.strip().lower():

            # Solo intenta leer fila 2 si la campaña tiene esa fila configurada
            if campaign_id in CAMPAIGNS_WITH_SEMRUSH_ROW and len(df) > 2:
                semrush_city_val = df.iloc[2, idx]
                if pd.notna(semrush_city_val):
                    semrush_city = str(semrush_city_val).strip().replace('\u200b', '').strip()
                    if semrush_city:
                        print(f"   -> 🏙️ Ciudad Semrush desde fila 2: '{semrush_city}'")
                        return semrush_city

            # Fallback: usar nombre de columna (fila 0)
            print(f"   -> 🏙️ Ciudad Semrush desde fila 0 (fallback): '{column_name}'")
            return column_name

    print(f"   -> ⚠️ Columna '{column_name}' no encontrada para obtener ciudad Semrush.")
    return column_name


def get_phrases_for_city(
    df: pd.DataFrame,
    city: str,
    campaign_id: int = 0
) -> List[str]:
    """
    Busca la columna por nombre (fila 0, case-insensitive).
    - Si campaign_id está en CAMPAIGNS_WITH_SEMRUSH_ROW → frases desde fila 3
    - Si no → frases desde fila 2 (comportamiento original)
    Retorna máximo 10 frases.
    """
    cities_row = df.iloc[0]
    col_idx = None
    for idx, val in enumerate(cities_row):
        if pd.notna(val) and str(val).strip().lower() == city.strip().lower():
            col_idx = idx
            break

    if col_idx is None:
        print(f"   -> ⚠️ Columna '{city}' no encontrada.")
        return []

    # Fila 1 = URL home (solo log informativo)
    if len(df) > 1:
        url_home = df.iloc[1, col_idx]
        if pd.notna(url_home):
            print(f"   -> 🔗 URL home de '{city}': {str(url_home).strip()}")

    # Determinar fila de inicio de frases
    start_row = 3 if campaign_id in CAMPAIGNS_WITH_SEMRUSH_ROW else 2
    print(f"   -> 📋 Leyendo frases desde fila {start_row} para campaña #{campaign_id}")

    frases = []
    for row_idx in range(start_row, len(df)):
        val = df.iloc[row_idx, col_idx]
        if pd.notna(val):
            frase = str(val).strip().replace('\u200b', '').strip()
            if frase:
                frases.append(frase)

    frases_limitadas = frases[:10]
    print(f"   -> Frases para '{city}' (máx 10): {frases_limitadas}")
    return frases_limitadas


# === High-level helpers para FastAPI ===
def list_accessible_campaign_ids(drive: Resource) -> List[int]:
    folders = list_available_campaign_folders(drive)
    return [f.campaign_id for f in folders]


def get_campaign_cities(drive: Resource, campaign_id: int) -> List[str]:
    f = select_campaign_programacion_file(drive, campaign_id)
    if not f:
        print(f"   -> ❌ No se encontró archivo para campaña ID: {campaign_id}")
        return []
    xlsx = download_excel_bytes(drive, f)
    sheet_name = CAMPAIGN_TO_SHEET_MAP.get(campaign_id)
    df = read_programacion_dataframe(xlsx, sheet_name=sheet_name)
    return get_available_cities(df)


def get_campaign_phrases_by_city(drive: Resource, campaign_id: int, city: str) -> List[str]:
    f = select_campaign_programacion_file(drive, campaign_id)
    if not f:
        print(f"   -> ❌ No se encontró archivo para campaña ID: {campaign_id}")
        return []
    xlsx = download_excel_bytes(drive, f)
    sheet_name = CAMPAIGN_TO_SHEET_MAP.get(campaign_id)
    df = read_programacion_dataframe(xlsx, sheet_name=sheet_name)
    return get_phrases_for_city(df, city, campaign_id=campaign_id)  # ⬅️ pasa campaign_id


def get_campaign_semrush_city(drive: Resource, campaign_id: int, column_name: str) -> str:
    """
    Retorna la ciudad exacta para escribir en Semrush dado un campaign_id y nombre de columna.
    Orden de prioridad:
    1. Ciudad fija (CAMPAIGN_FIXED_CITY) — ej: SPA 312 siempre Chicago
    2. Fila 2 del Excel (CAMPAIGNS_WITH_SEMRUSH_ROW) — ej: Albany Park, Chicago, IL
    3. Nombre de columna fila 0 (fallback) — ej: chicago
    """
    # 1. Ciudad fija por campaña
    if campaign_id in CAMPAIGN_FIXED_CITY:
        fixed = CAMPAIGN_FIXED_CITY[campaign_id]
        print(f"   -> 🏙️ Ciudad fija para campaña #{campaign_id}: '{fixed}'")
        return fixed

    # 2. Lee desde fila 2 del Excel (solo si campaña está en CAMPAIGNS_WITH_SEMRUSH_ROW)
    if campaign_id in CAMPAIGNS_WITH_SEMRUSH_ROW:
        f = select_campaign_programacion_file(drive, campaign_id)
        if f:
            xlsx = download_excel_bytes(drive, f)
            sheet_name = CAMPAIGN_TO_SHEET_MAP.get(campaign_id)
            df = read_programacion_dataframe(xlsx, sheet_name=sheet_name)
            return get_semrush_city_for_column(df, column_name, campaign_id=campaign_id)

    # 3. Fallback: usar el nombre de columna directamente
    print(f"   -> 🏙️ Ciudad Semrush desde nombre de columna: '{column_name}'")
    return column_name