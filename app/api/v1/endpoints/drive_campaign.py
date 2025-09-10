# app/api/v1/endpoints/drive_campaign.py
from fastapi import APIRouter, HTTPException
from app.services.drive_campaign_service import (
    build_drive_client,
    list_accessible_campaign_ids,
    get_campaign_cities,
    get_campaign_phrases_by_city,
)

router = APIRouter(prefix="/drive-campaigns", tags=["Drive Campaigns"])

# ⚠️ IMPORTANTE: el cliente se construye una sola vez.
# Si necesitas recargarlo por cada request, cámbialo por una dependencia.
_drive = build_drive_client()


@router.get("/ids")
def ids_disponibles():
    """Devuelve los campaign_id accesibles en Google Drive."""
    try:
        return {"ids": list_accessible_campaign_ids(_drive)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{campaign_id}/ciudades")
def ciudades_disponibles(campaign_id: int):
    """Devuelve la lista de ciudades disponibles para la campaña seleccionada."""
    try:
        ciudades = get_campaign_cities(_drive, campaign_id)
        return {"campaign_id": campaign_id, "ciudades": ciudades}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{campaign_id}/frases")
def frases_por_ciudad(campaign_id: int, city: str):
    """Devuelve las frases objetivas de una ciudad dentro de la campaña seleccionada."""
    try:
        frases = get_campaign_phrases_by_city(_drive, campaign_id, city)
        return {"campaign_id": campaign_id, "city": city, "frases": frases}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
