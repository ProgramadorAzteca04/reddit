# app/api/v1/endpoints/semrush.py
from app.services.semrush.login_service import run_semrush_config_account_flow, run_semrush_login_flow
from app.services.semrush.registration_service import run_semrush_signup_flow, run_semrush_signup_flow_batch
from app.schemas.semrush import BatchSignupRequest, ConfigAccountRequest, SemrushLoginRequest
from fastapi import APIRouter, BackgroundTasks, HTTPException


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

@router.post("/signup/batch", status_code=202, summary="Registrar múltiples cuentas de Semrush")
async def start_semrush_signup_batch(request: BatchSignupRequest, background_tasks: BackgroundTasks):
    """
    Lanza en segundo plano un proceso que repetirá el registro en Semrush
    'times' veces de forma secuencial. Usa un delay opcional entre corridas.
    """
    MAX_TIMES = 50
    if request.times > MAX_TIMES:
        raise HTTPException(status_code=400, detail=f"El máximo permitido es {MAX_TIMES} registros por petición.")
    print(f"🚀 Petición recibida para multi-registro: {request.times} vez/veces (delay={request.delay_seconds}s).")
    background_tasks.add_task(run_semrush_signup_flow_batch, request.times, request.delay_seconds or 0.0)
    return {"message": f"Se programó la ejecución de {request.times} registro(s) en segundo plano."}


@router.post("/login", status_code=202, summary="Iniciar Sesión en Semrush")
async def start_semrush_login(request: SemrushLoginRequest, background_tasks: BackgroundTasks):
    """
    Inicia un proceso en segundo plano para iniciar sesión en Semrush con una
    credencial específica de la base de datos, usando su proxy asociado.
    """
    print(f"🚀 Petición recibida para iniciar sesión en Semrush con la credencial ID: {request.credential_id}")
    
    background_tasks.add_task(run_semrush_login_flow, credential_id=request.credential_id)
    
    return {"message": "El proceso de login en Semrush ha comenzado en segundo plano."}

@router.post("/config-account", status_code=202, summary="Configurar y Asignar Cuenta de Semrush")
async def config_account(request: ConfigAccountRequest, background_tasks: BackgroundTasks):
    """
    Busca una cuenta de Semrush sin usar (id_campaigns es nulo), le asigna
    el ID de campaña proporcionado y luego inicia sesión para verificarla.
    """
    print(f"🚀 Petición recibida para configurar una cuenta para la campaña ID: {request.id_campaign}")
    
    background_tasks.add_task(
        run_semrush_config_account_flow, 
        id_campaign=request.id_campaign, 
        city=request.city
    )
    
    return {"message": "El proceso de configuración y login de la cuenta ha comenzado en segundo plano."}