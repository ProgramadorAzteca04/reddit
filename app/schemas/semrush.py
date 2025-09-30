from typing import Optional
from pydantic import BaseModel, Field

class SemrushLoginRequest(BaseModel):
    credential_id: int = Field(..., description="ID de la credencial de Semrush guardada en la base de datos.")
class ConfigAccountRequest(BaseModel):
    credential_id: int = Field(..., description="ID de la credencial específica a la que se le asignará la campaña.")
    id_campaign: int = Field(..., description="ID de la campaña que se asignará y configurará.")
class BatchSignupRequest(BaseModel):
    times: int = Field(..., gt=0, description="Cantidad de veces que se repetirá el proceso de registro")
    delay_seconds: Optional[float] = Field(10.0, ge=0, description="Pausa entre cada intento (segundos)")