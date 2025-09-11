from app.services.github.registration import run_github_sign_in_flow
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
