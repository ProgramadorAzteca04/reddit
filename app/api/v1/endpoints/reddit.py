# app/api/v1/endpoints/reddit.py
from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Depends
from app.schemas.auth import LoginRequest, AutomationRequest, MultiLoginRequest, CreatePostRequest, MultiRegisterRequest
from app.services.reddit.login_service import run_login_flow
from app.services.reddit.registration_service import run_registration_flow
from app.services.reddit.post_creator_service import execute_create_post_flow
from app.services.reddit.multi_account_service import run_multi_login_flow
from app.services.reddit import multi_registration_service

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

@router.post("/multi-register", summary="Registrar Múltiples Cuentas desde Archivo")
async def multi_register_accounts(request: MultiRegisterRequest, background_tasks: BackgroundTasks):
    """
    Inicia un proceso en segundo plano para registrar un número específico de 
    cuentas de Reddit, tomando los correos de forma aleatoria desde un archivo de texto.
    
    - **count**: Número de cuentas que deseas registrar.
    - **file_path**: Ruta al archivo .txt que contiene la lista de correos.
    - **url**: URL de la página de registro.
    """
    try:
        # Usamos BackgroundTasks para que la API responda inmediatamente
        # mientras el proceso de registro (que es lento) se ejecuta en segundo plano.
        background_tasks.add_task(
            multi_registration_service.run_multi_registration_flow,
            count=request.count,
            file_path=request.file_path,
            url=request.url
        )
        
        return {"message": f"Proceso de registro para {request.count} cuentas iniciado en segundo plano. Revisa la consola para ver el progreso."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/login", status_code=202)
async def start_login(request: LoginRequest, background_tasks: BackgroundTasks):
    print(f"🚀 Petición recibida para login del usuario con ID: {request.credential_id}")
    
    background_tasks.add_task(
        run_login_flow,
        credential_id=request.credential_id,
        url=request.url,
        window_title=request.window_title,
        interaction_minutes=request.interaction_minutes,
        upvote_from_database_enabled=request.upvote_from_database_enabled,
        repost_from_feed_enabled=request.repost_from_feed_enabled,
        comment_on_feed_enabled=request.comment_on_feed_enabled # <-- NUEVO PARÁMETRO
    )
    return {"message": "El proceso de login y navegación ha comenzado en segundo plano."}

@router.post("/create-post", status_code=202)
async def start_create_post(request: CreatePostRequest, background_tasks: BackgroundTasks):
    print(f"🚀 Petición recibida para crear un post con la credencial ID: {request.credential_id}")
    
    background_tasks.add_task(
        execute_create_post_flow,
        credential_id=request.credential_id
    )
    return {"message": "El proceso para crear una publicación ha comenzado en segundo plano."}

@router.post("/multi-login", status_code=202)
async def start_multi_login(request: MultiLoginRequest, background_tasks: BackgroundTasks):
    print(f"🚀 Petición recibida para un login múltiple de {len(request.account_ids)} cuentas.")
    
    background_tasks.add_task(
        run_multi_login_flow,
        account_ids=request.account_ids,
        url=request.url,
        window_title=request.window_title,
        interaction_minutes=request.interaction_minutes,
        upvote_from_database_enabled=request.upvote_from_database_enabled,
        repost_from_feed_enabled=request.repost_from_feed_enabled,
        comment_on_feed_enabled=request.comment_on_feed_enabled # <-- NUEVO PARÁMETRO
    )
    return {"message": "El proceso de login múltiple ha comenzado en segundo plano."}


@router.post("/create-post", status_code=202)
async def start_create_post(request: CreatePostRequest, background_tasks: BackgroundTasks):
    """
    Inicia el flujo de creación de un post para una cuenta específica por su ID.
    El tema del post es seleccionado automáticamente por la IA.
    """
    print(f"🚀 Petición recibida para crear un post con la credencial ID: {request.credential_id}")
    
    background_tasks.add_task(
        execute_create_post_flow,
        credential_id=request.credential_id  # <-- Se pasa solo el ID
    )
    return {"message": "El proceso para crear una publicación ha comenzado en segundo plano."}


@router.get("/health")
def health_check():
    """Verifica que el servicio esté activo."""
    return {"status": "ok"}