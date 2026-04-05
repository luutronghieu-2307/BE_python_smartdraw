from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from app.core.config import settings


@lru_cache(maxsize=2)
def load_detection_model(model_path: str | None = None, prefer_gpu: bool = True) -> tuple[YOLO, str]:
    path = Path(model_path or settings.yolo_model_path)
    if not path.exists():
        raise FileNotFoundError(f"YOLO model not found at: {path}")

    device = "cuda:0" if prefer_gpu and torch.cuda.is_available() else "cpu"
    model = YOLO(str(path))

    if hasattr(model, "to"):
        model.to(device)

    return model, device


def _extract_people_detections(image: np.ndarray, result: Any) -> list[dict[str, Any]]:
    detections: list[dict[str, Any]] = []

    names = result.names if hasattr(result, "names") else {}
    boxes = result.boxes

    if boxes is None:
        return detections

    for box in boxes:
        cls_id = int(box.cls[0].item())
        if cls_id != 0:
            continue

        conf = float(box.conf[0].item())
        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
        x1 = max(0, min(x1, image.shape[1] - 1))
        y1 = max(0, min(y1, image.shape[0] - 1))
        x2 = max(0, min(x2, image.shape[1]))
        y2 = max(0, min(y2, image.shape[0]))
        if x2 <= x1 or y2 <= y1:
            continue

        label = names.get(cls_id, "person") if isinstance(names, dict) else "person"
        detections.append(
            {
                "class_id": cls_id,
                "label": label,
                "confidence": conf,
                "bbox": [x1, y1, x2, y2],
            }
        )

    detections.sort(key=lambda item: (item["bbox"][0], item["bbox"][1]))
    return detections


def _draw_people_boxes(image: np.ndarray, result: Any) -> tuple[np.ndarray, list[dict[str, Any]]]:
    annotated = image.copy()
    detections = _extract_people_detections(image, result)

    for detection in detections:
        x1, y1, x2, y2 = detection["bbox"]
        conf = detection["confidence"]
        label = detection["label"]

        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
        text = f"{label} {conf:.2f}"
        (text_w, text_h), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        y_text = max(y1 - 10, text_h + 10)
        cv2.rectangle(annotated, (x1, y_text - text_h - baseline), (x1 + text_w + 4, y_text + baseline), (0, 255, 0), -1)
        cv2.putText(
            annotated,
            text,
            (x1 + 2, y_text),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )

    return annotated, detections


def detect_people_and_annotate(image: np.ndarray, conf: float = 0.25) -> tuple[np.ndarray, list[dict[str, Any]], str]:
    model, device = load_detection_model()
    use_half = device.startswith("cuda")
    results = model.predict(source=image, conf=conf, classes=[0], device=device, half=use_half, verbose=False)
    result = results[0]
    annotated, detections = _draw_people_boxes(image, result)
    return annotated, detections, device


def detect_people(image: np.ndarray, conf: float = 0.25) -> tuple[list[dict[str, Any]], str]:
    model, device = load_detection_model()
    use_half = device.startswith("cuda")
    results = model.predict(source=image, conf=conf, classes=[0], device=device, half=use_half, verbose=False)
    result = results[0]
    detections = _extract_people_detections(image, result)
    return detections, device
