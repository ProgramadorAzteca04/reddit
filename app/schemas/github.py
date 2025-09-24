# app/schemas/github.py
from pydantic import BaseModel, Field

class GitHubLoginRequest(BaseModel):
    credential_id: int = Field(..., description="ID de la credencial de GitHub guardada en la base de datos.")