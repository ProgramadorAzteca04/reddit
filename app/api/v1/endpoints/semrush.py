# app/api/v1/endpoints/semrush.py
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.services.semrush.login_service import (
    run_semrush_config_account_flow,
    run_semrush_login_flow,
    run_semrush_cycle_config_accounts,  # ⬅️ NUEVO: orquestador
)
from app.services.semrush.registration_service import (
    run_semrush_signup_flow,
    run_semrush_signup_flow_batch,
)
from app.schemas.semrush import (
    BatchSignupRequest,
    ConfigAccountRequest,
    SemrushLoginRequest,
)

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


@router.post("/config-account", status_code=202, summary="Configurar Cuenta de Semrush con Credencial Específica")
async def config_account(request: ConfigAccountRequest, background_tasks: BackgroundTasks):
    """
    Usa una credencial específica (por su ID) para configurar un proyecto de Semrush
    asociado a una campaña (por su ID).
    """
    print(f"🚀 Petición recibida para configurar la campaña ID {request.id_campaign} en la credencial ID {request.credential_id}.")
    
    background_tasks.add_task(
        run_semrush_config_account_flow, 
        credential_id=request.credential_id,
        id_campaign=request.id_campaign
    )
    
    return {"message": "El proceso de configuración de la cuenta ha comenzado en segundo plano."}

@router.post(
    "/config-account/cycle",
    status_code=202,
    summary="Configurar cuentas por campaña/ciudad (ciclo maestro)",
)
async def start_semrush_cycle(
    background_tasks: BackgroundTasks,
    delay_seconds: float = 8.0,
    max_total_iterations: Optional[int] = None,
):
    """
    Lanza en segundo plano el ciclo maestro que:
      - Toma credenciales con id_campaigns NULL (libres).
      - Recorre campañas accesibles (orden ascendente) y, para cada una, sus ciudades (ordenadas).
      - Para cada ciudad con frases disponibles, reutiliza `run_semrush_config_account_flow(id_campaign, city)`.
      - Actualiza `note` de la credencial asignada con la ciudad utilizada.
      - Se detiene al agotar credenciales o combinaciones útiles (campaña/ciudad).

    Parámetros:
      - delay_seconds: Pausa entre iteraciones para estabilizar UI (por defecto 8.0).
      - max_total_iterations: Tope de seguridad para cortar el ciclo (None = sin tope).
    """
    MAX_CAP = 500
    if max_total_iterations is not None and max_total_iterations > MAX_CAP:
        raise HTTPException(
            status_code=400,
            detail=f"max_total_iterations no puede exceder {MAX_CAP}.",
        )

    print(f"🧭 Petición recibida para ciclo maestro (delay={delay_seconds}s, max={max_total_iterations}).")
    background_tasks.add_task(
        run_semrush_cycle_config_accounts,
        delay_seconds,
        max_total_iterations,
    )
    return {
        "message": "Ciclo maestro de configuración programado en segundo plano.",
        "params": {"delay_seconds": delay_seconds, "max_total_iterations": max_total_iterations},
    }