# app/api/v1/endpoints/reddit.py
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field, EmailStr
from app.schemas.auth import LoginRequest, AutomationRequest, MultiLoginRequest
from app.schemas.auth import LoginRequest, AutomationRequest
from app.services.reddit.login_service import run_login_flow
from app.services.reddit.registration_service import run_registration_flow
from app.services.reddit.post_creator_service import execute_create_post_flow
from app.services.reddit.multi_account_service import run_multi_login_flow

router = APIRouter()

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)

class CreatePostRequest(BaseModel):
    username: str
    password: str

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
    Inicia el proceso de inicio de sesión para una sola cuenta por su ID.
    """
    print(f"🚀 Petición recibida para login del usuario con ID: {request.credential_id}")
    
    background_tasks.add_task(
        run_login_flow,
        credential_id=request.credential_id, # <-- Pasa el ID
        url=request.url,
        window_title=request.window_title,
        interaction_minutes=request.interaction_minutes
    )
    return {"message": "El proceso de login y navegación ha comenzado en segundo plano."}


@router.post("/create-post", status_code=202)
async def start_create_post(request: CreatePostRequest, background_tasks: BackgroundTasks):
    """
    Inicia el flujo de login y, en lugar de navegar, hace clic en el botón
    de "Crear Publicación".
    """
    print(f"🚀 Petición recibida para crear un post con el usuario: {request.username}")
    
    background_tasks.add_task(
        execute_create_post_flow,
        username=request.username,
        password=request.password
    )
    return {"message": "El proceso para iniciar la creación de una publicación ha comenzado en segundo plano."}

@router.post("/multi-login", status_code=202)
async def start_multi_login(request: MultiLoginRequest, background_tasks: BackgroundTasks):
    """
    Inicia un bucle de login e interacción para una lista de IDs de cuentas.
    """
    print(f"🚀 Petición recibida para un login múltiple de {len(request.account_ids)} cuentas.")
    
    background_tasks.add_task(
        run_multi_login_flow,
        account_ids=request.account_ids, # <-- Pasa la lista de IDs
        url=request.url,
        window_title=request.window_title,
        interaction_minutes=request.interaction_minutes
    )
    return {"message": "El proceso de login múltiple ha comenzado en segundo plano."}


@router.get("/health")
def health_check():
    """Verifica que el servicio esté activo."""
    return {"status": "ok"}