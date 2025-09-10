from typing import Dict, List, Optional, Tuple
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

# Mapa original (puedes moverlo a tu settings si prefieres)
CAMPAIGN_TO_FOLDER_MAP: Dict[int, str] = {
    1:   '1USPG1OiA3VNvgjXJqGRqZOkbDFPTyUih',
    2:   '1K7Sz-6aA0HMDmVtqQAS9A8n12eT9veIK',
    3:   '1uOTuodJMoHXO-w_kGddy3LTmJi_RtAUN',
    4:   '1kDAZrpfb_L4kkxwBdkSKte9XoNtVjBB5',
    5:   '1JfbnUNTlTYwKDB_5F57T1eUhd5RtOzUy',
    6:   '1m4b3BJ3CCdldHIrArkJG3-w-DaTUI69F',
    7:   '1T17NooEgccdIyvMcYOxUkXVGDZleVejs',
    8:   '1Is9XIHGERN436WkfLmXDTIb16Zbf_OfZ',
    9:   '1SfJS6nwCGUvrmioDBLcDG01zKt8GB1z-',
    10:  '1mOM4p84hqkF2mwo7mTJwHrH0VUhEeJMq',
    12:  '1go_XE8fDrEzexQpRoX9HUXs8FR03aEBK',
    13:  '1eXaBx8r_qijDmEyqVFudckpqd8lEA1W-',
    40:  '199sJiYJxKxdC1-Usf3301mY4hHKPNUPY',
    42:  '1yNcAr9uvOsZ4OGBg3b8SugClZ89JSklQ',
    43:  '1oVGosUBx7j_t36iAORrTW9eVeuTq2O6-',
    44:  '12sfC6Hp9LLDeKYBMxGyvVApT6g2_AygA',
    58:  '1NA8Ytw9nZt1riC47DYh6bIkezUqHXa1Y',
    59:  '1xOqoPpM9xXQA8uXkCXsdjG2VGEncrXpO',
    71:  '1auUzEVlCGkYj30OAE3R7AbPniR3bkgoj',
    72:  '13tVWVJ-OlxJJU3Oipk1d79wA7uBekHl8',
    75:  '1K7eNmb_L29lInFgJ1lkDT76CMCZWtyMf',
    109: '1BJGhVlLhmqO4L9LGWwjcDGeq3Al3IbpD',
    110: '1VBznDJS0sUgX70EZNVB4KV7FXEzoyK3v',
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
    """
    Crea el cliente de Google Drive (v3). Maneja token refresh y primer login (InstalledAppFlow).
    """
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
            # Nota: en entorno server headless, reemplaza por flow.run_console() si lo prefieres
            creds = flow.run_local_server(port=0)

        with open(token_json_path, "w") as token:
            token.write(creds.to_json())

    return build('drive', 'v3', credentials=creds)


# === Core logic (reutilizable) ===
def list_available_campaign_folders(
    drive: Resource,
    campaign_map: Dict[int, str] = CAMPAIGN_TO_FOLDER_MAP
) -> List[CampaignFolder]:
    """
    Valida qué carpetas del mapa son accesibles y devuelve metadatos.
    """
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
        except HttpError as e:
            # Inaccesible o no existe → se omite
            continue
    return out


def _list_folder_files(drive: Resource, folder_id: str) -> List[DriveFile]:
    """
    Lista archivos dentro de una carpeta de Drive.
    """
    res = drive.files().list(
        q=f"'{folder_id}' in parents",
        fields="files(id, name, mimeType)"
    ).execute()
    files = res.get('files', []) or []
    return [DriveFile(id=f['id'], name=f['name'], mime_type=f['mimeType']) for f in files]


def _pick_programacion_file(files: List[DriveFile]) -> Optional[DriveFile]:
    """
    Emula tu prioridad:
      1) PROGRAMACION BACKLINS
      2) PROGRAMACION BACKLINKS
      3) BACKLINS
      4) BACKLINKS
    """
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
    campaign_map: Dict[int, str] = CAMPAIGN_TO_FOLDER_MAP
) -> Optional[DriveFile]:
    """
    Dado un campaign_id, retorna el archivo a usar según tu prioridad de nombres.
    """
    if campaign_id not in campaign_map:
        raise KeyError(f"campaign_id {campaign_id} no existe en el mapa configurado.")

    folder_id = campaign_map[campaign_id]

    # Validar acceso a la carpeta (opcional)
    drive.files().get(fileId=folder_id, fields='id').execute()

    files = _list_folder_files(drive, folder_id)
    return _pick_programacion_file(files)


def download_excel_bytes(drive: Resource, file: DriveFile) -> bytes:
    """
    Si es Google Sheet, exporta a XLSX. Si es binario (xlsx, etc.), lo descarga.
    Devuelve los bytes del archivo Excel.
    """
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
        # No prints; si necesitas logs, integra logging.debug aquí

    return bio.getvalue()


def read_programacion_dataframe(xlsx_bytes: bytes, header_row_index: int = 1) -> pd.DataFrame:
    """
    Lee el Excel a DataFrame. Usa header=1 (segunda fila) como en tu script.
    """
    df = pd.read_excel(io.BytesIO(xlsx_bytes), header=header_row_index)
    if 'CIUDAD' in df.columns:
        df['CIUDAD'] = df['CIUDAD'].ffill()
    return df


def get_available_cities(df: pd.DataFrame) -> List[str]:
    """
    Devuelve ciudades únicas, limpias y ordenadas.
    """
    if 'CIUDAD' not in df.columns:
        return []
    serie = df['CIUDAD'].dropna().astype(str).map(str.strip)
    serie = serie[serie != ""]
    return sorted(set(serie.tolist()))


def get_phrases_for_city(df: pd.DataFrame, city: str) -> List[str]:
    """
    Filtra por ciudad (case-insensitive) y devuelve FRASE OBJETIVA (no nulas).
    """
    for col in ('CIUDAD', 'FRASE OBJETIVA'):
        if col not in df.columns:
            return []

    mask = df['CIUDAD'].astype(str).str.strip().str.lower() == str(city).strip().lower()
    sub = df.loc[mask]
    if sub.empty:
        return []

    frases = sub['FRASE OBJETIVA'].dropna().astype(str).map(str.strip)
    frases = [f for f in frases.tolist() if f]
    return frases


# === High-level helpers para FastAPI ===
def list_accessible_campaign_ids(drive: Resource) -> List[int]:
    """
    Devuelve solo los campaign_id accesibles (carpeta existe y/o es visible).
    """
    folders = list_available_campaign_folders(drive)
    return [f.campaign_id for f in folders]


def get_campaign_cities(
    drive: Resource,
    campaign_id: int
) -> List[str]:
    """
    Retorna las ciudades disponibles dentro del archivo de la campaña.
    """
    f = select_campaign_programacion_file(drive, campaign_id)
    if not f:
        return []
    xlsx = download_excel_bytes(drive, f)
    df = read_programacion_dataframe(xlsx)
    return get_available_cities(df)


def get_campaign_phrases_by_city(
    drive: Resource,
    campaign_id: int,
    city: str
) -> List[str]:
    """
    Retorna las frases objetivas de una ciudad para la campaña dada.
    """
    f = select_campaign_programacion_file(drive, campaign_id)
    if not f:
        return []
    xlsx = download_excel_bytes(drive, f)
    df = read_programacion_dataframe(xlsx)
    return get_phrases_for_city(df, city)