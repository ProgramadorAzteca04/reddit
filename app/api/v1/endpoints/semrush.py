# app/api/v1/endpoints/semrush.py
from fastapi import APIRouter, BackgroundTasks

from app.services.semrush.registration_service import run_semrush_signup_flow

router = APIRouter()

@router.post("/signup", status_code=202, summary="Iniciar Navegación a Semrush Signup")
async def start_semrush_signup(background_tasks: BackgroundTasks):
    """
    Inicia un proceso en segundo plano que abre un navegador y navega a la
    página de registro de Semrush utilizando un proxy aleatorio.
    """
    print("🚀 Petición recibida para iniciar la navegación a Semrush.")
    
    background_tasks.add_task(run_semrush_signup_flow)
    
    return {"message": "El proceso de navegación a Semrush ha comenzado en segundo plano."}