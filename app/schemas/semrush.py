from pydantic import BaseModel, Field

class SemrushLoginRequest(BaseModel):
    credential_id: int = Field(..., description="ID de la credencial de Semrush guardada en la base de datos.")

class ConfigAccountRequest(BaseModel):
    id_campaign: int = Field(..., description="ID de la campaña para asignar a la cuenta.")
    city: str = Field(..., description="Ciudad para la configuración de la campaña (actualmente no se usa en la lógica, pero está disponible).")
