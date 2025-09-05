from pydantic import BaseModel, Field

class SemrushLoginRequest(BaseModel):
    credential_id: int = Field(..., description="ID de la credencial de Semrush guardada en la base de datos.")