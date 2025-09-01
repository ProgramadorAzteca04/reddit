from pydantic import BaseModel, Field
from typing import List

class AutomationRequest(BaseModel):
    url: str = Field(..., example="https://www.reddit.com/register/")
    email: str = Field(..., example="tu.correo@ejemplo.com")

class LoginRequest(BaseModel):
    credential_id: int = Field(..., description="ID de la credencial guardada en la base de datos.")
    url: str = Field("https://www.reddit.com/login", description="URL de login.")
    window_title: str = Field("Reddit", description="Título de la ventana para PyAutoGUI.")
    interaction_minutes: int = Field(5, description="Duración de la interacción.")
    upvote_from_database_enabled: bool = Field(True, description="Habilita dar upvote a posts guardados en la BD.")
    repost_from_feed_enabled: bool = Field(False, description="Habilita analizar el feed y republicar el mejor post.")

class ElementLocator(BaseModel):
    images: List[str]
    confidence: float = 0.85
    wait_time: int = 0
    attempts: int = 1
    scroll_on_fail: bool = False

class MultiLoginRequest(BaseModel):
    account_ids: List[int] = Field(..., description="Lista de IDs de las credenciales a procesar.")
    url: str = Field("https://www.reddit.com/login", description="URL de login para todas las cuentas.")
    window_title: str = Field("Reddit", description="Título de la ventana para PyAutoGUI.")
    interaction_minutes: int = Field(5, description="Duración de la interacción por cada cuenta.")
    upvote_from_database_enabled: bool = Field(True, description="...")
    repost_from_feed_enabled: bool = Field(False, description="Habilita la interacción de analizar el feed con IA y republicar el mejor post.")


class CreatePostRequest(BaseModel):
    credential_id: int = Field(..., description="ID de la credencial a utilizar para crear el post.")

class MultiRegisterRequest(BaseModel):
    count: int = Field(..., gt=0, description="Número de cuentas a registrar.")
    file_path: str = Field("correos.txt", description="Ruta al archivo de texto con los correos.")
    url: str = Field("https://www.reddit.com/register/", description="URL de registro de Reddit.")

class ScrapeFeedRequest(BaseModel):
    credential_id: int = Field(..., description="ID de la credencial a utilizar para analizar el feed.")
