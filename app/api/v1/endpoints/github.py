from app.services.github.registration import run_github_sign_in_flow
from app.services.github.login_service import run_github_login_flow
from app.schemas.github import GitHubLoginRequest
from fastapi import APIRouter, BackgroundTasks, HTTPException

router = APIRouter()

@router.post("/github-sign-up", status_code=202)
async def start_github_registration(background_tasks: BackgroundTasks):
    """
    Inicia el flujo de registro en GitHub en segundo plano.
    """
    print("🚀 Petición recibida para iniciar el registro en GitHub.")
    try:
        background_tasks.add_task(run_github_sign_in_flow)
        return {"message": "El proceso de registro en GitHub ha comenzado en segundo plano. Revisa la consola para ver el progreso."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post("/github-login", status_code=202)
async def start_github_login(request: GitHubLoginRequest, background_tasks: BackgroundTasks):
    """
    Inicia el flujo de inicio de sesión en GitHub en segundo plano para una credencial específica.
    """
    print(f"🚀 Petición recibida para iniciar sesión en GitHub con la credencial ID: {request.credential_id}")
    try:
        background_tasks.add_task(run_github_login_flow, credential_id=request.credential_id)
        return {"message": "El proceso de inicio de sesión en GitHub ha comenzado en segundo plano. Revisa la consola para ver el progreso."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
