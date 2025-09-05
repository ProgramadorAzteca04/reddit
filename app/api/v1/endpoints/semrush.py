# app/api/v1/endpoints/semrush.py
from app.services.semrush.registration_service import run_semrush_signup_flow
from app.services.semrush.login_service import run_semrush_login_flow
from app.schemas.semrush import SemrushLoginRequest
from fastapi import APIRouter, BackgroundTasks


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

@router.post("/login", status_code=202, summary="Iniciar Sesión en Semrush")
async def start_semrush_login(request: SemrushLoginRequest, background_tasks: BackgroundTasks):
    """
    Inicia un proceso en segundo plano para iniciar sesión en Semrush con una
    credencial específica de la base de datos, usando su proxy asociado.
    """
    print(f"🚀 Petición recibida para iniciar sesión en Semrush con la credencial ID: {request.credential_id}")
    
    background_tasks.add_task(run_semrush_login_flow, credential_id=request.credential_id)
    
    return {"message": "El proceso de login en Semrush ha comenzado en segundo plano."}