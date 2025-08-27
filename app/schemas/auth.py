
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