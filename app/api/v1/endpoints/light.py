from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import settings
from app.schemas.light import LightControlRequest, LightControlResponse
from app.services.light_control import (
    build_qr_payload,
    generate_connection_qr,
    get_qr_path,
    publish_light_state,
)

router = APIRouter()


@router.post("/control", response_model=LightControlResponse)
def control_light(payload: LightControlRequest) -> LightControlResponse:
    try:
        mqtt_payload = publish_light_state(payload.state)
        return LightControlResponse(
            status="ok",
            state=mqtt_payload["state"],
            topic=settings.mqtt_light_topic,
            payload=mqtt_payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/bootstrap")
def get_light_bootstrap() -> dict[str, object]:
    qr_path = get_qr_path()
    return {
        "status": "ok",
        "qr_payload": build_qr_payload(),
        "qr_image": "/media/qr/" + qr_path.name,
    }


@router.get("/qr")
def download_light_qr() -> FileResponse:
    qr_path = get_qr_path()
    if not qr_path.exists():
        qr_path = generate_connection_qr()
    return FileResponse(path=qr_path, media_type="image/png", filename=qr_path.name)
