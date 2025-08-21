# endpoints.py
from fastapi import APIRouter, BackgroundTasks

# Se importan los flujos y modelos actualizados del servicio de autenticación
from app.services.reddit.auth import (
    run_registration_flow,
    run_login_flow,
    AutomationRequest,
    LoginRequest, # Este modelo ahora es más simple
)

router = APIRouter()

@router.post("/register", status_code=202)
async def start_reddit_registration(request: AutomationRequest, background_tasks: BackgroundTasks):
    """
    Inicia el proceso de registro en Reddit.
    Se ejecuta en segundo plano para no bloquear la respuesta.
    """
    print(f"🚀 Petición recibida para registrar el correo: {request.email}")
    background_tasks.add_task(run_registration_flow, request.email, request.url)
    return {"message": "El proceso de registro ha comenzado en segundo plano."}


@router.post("/login", status_code=202)
async def start_login(request: LoginRequest, background_tasks: BackgroundTasks):
    """
    Inicia el proceso de inicio de sesión en Reddit y la navegación posterior,
    que ahora es automática y aleatoria.
    """
    print(f"🚀 Petición recibida para login del usuario: {request.username}")
    
    # --- CAMBIO CLAVE ---
    # La tarea en segundo plano ahora se llama con 'interaction_minutes',
    # que es el único parámetro necesario para la navegación.
    background_tasks.add_task(
        run_login_flow,
        username=request.username,
        password=request.password,
        url=request.url,
        window_title=request.window_title,
        interaction_minutes=request.interaction_minutes
    )
    return {"message": "El proceso de login y navegación automática ha comenzado en segundo plano."}


@router.get("/health")
def health_check():
    """Verifica que el servicio esté activo."""
    return {"status": "ok"}