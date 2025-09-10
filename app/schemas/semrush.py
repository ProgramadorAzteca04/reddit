from typing import Optional
from pydantic import BaseModel, Field

class SemrushLoginRequest(BaseModel):
    credential_id: int = Field(..., description="ID de la credencial de Semrush guardada en la base de datos.")

class ConfigAccountRequest(BaseModel):
    id_campaign: int = Field(..., description="ID de la campaña para asignar a la cuenta.")
    city: str = Field(..., description="Ciudad para la configuración de la campaña (actualmente no se usa en la lógica, pero está disponible).")

class BatchSignupRequest(BaseModel):
    times: int = Field(..., gt=0, description="Cantidad de veces que se repetirá el proceso de registro")
    delay_seconds: Optional[float] = Field(10.0, ge=0, description="Pausa entre cada intento (segundos)")