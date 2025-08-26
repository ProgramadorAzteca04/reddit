
from pydantic import BaseModel, Field
from typing import List

class AutomationRequest(BaseModel):
    url: str = Field(..., example="https://www.reddit.com/register/")
    email: str = Field(..., example="tu.correo@ejemplo.com")

class LoginRequest(BaseModel):
    url: str = Field(..., example="https://www.reddit.com/login")
    username: str
    password: str
    window_title: str = Field("Reddit", description="Título de la ventana para PyAutoGUI.")
    interaction_minutes: int = Field(5, description="Duración aproximada de la interacción en minutos.")

class ElementLocator(BaseModel):
    images: List[str]
    confidence: float = 0.85
    wait_time: int = 0
    attempts: int = 1
    scroll_on_fail: bool = False