from __future__ import annotations

from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.services.detection import detect_people_and_annotate

router = APIRouter()


@router.post("/person/upload")
async def detect_people_from_upload(
    request: Request,
    file: UploadFile = File(...),
    conf: float = 0.25,
) -> dict[str, object]:
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    np_buffer = np.frombuffer(contents, dtype=np.uint8)
    image = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    annotated_image, detections, device = detect_people_and_annotate(image, conf=conf)

    media_path = Path("media") / "detections"
    media_path.mkdir(parents=True, exist_ok=True)

    filename = f"people_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
    file_path = media_path / filename
    success = cv2.imwrite(str(file_path), annotated_image)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save annotated image")

    image_url = request.url_for("media", path=f"detections/{filename}")

    return {
        "status": "ok",
        "device": device,
        "people_count": len(detections),
        "image_url": str(image_url),
        "detections": detections,
    }
