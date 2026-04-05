from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.services.classification import classify_roi
from app.services.detection import detect_people


def _clip_bbox(bbox: list[int], width: int, height: int) -> list[int]:
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(int(x1), width - 1))
    y1 = max(0, min(int(y1), height - 1))
    x2 = max(0, min(int(x2), width))
    y2 = max(0, min(int(y2), height))
    return [x1, y1, x2, y2]


def _expand_bbox(bbox: list[int], width: int, height: int, padding_ratio: float = 0.2) -> list[int]:
    x1, y1, x2, y2 = bbox
    box_w = x2 - x1
    box_h = y2 - y1

    pad_x = int(box_w * padding_ratio)
    pad_y = int(box_h * padding_ratio)

    expanded = [
        x1 - pad_x,
        y1 - pad_y,
        x2 + pad_x,
        y2 + pad_y,
    ]
    return _clip_bbox(expanded, width, height)


def _crop_roi(image: np.ndarray, bbox: list[int]) -> np.ndarray | None:
    x1, y1, x2, y2 = bbox
    if x2 <= x1 or y2 <= y1:
        return None
    roi = image[y1:y2, x1:x2]
    if roi is None or getattr(roi, "size", 0) == 0:
        return None
    return roi


def _draw_label(image: np.ndarray, bbox: list[int], lines: list[str], color: tuple[int, int, int] = (0, 255, 0)) -> None:
    x1, y1, x2, y2 = bbox
    cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
    if not lines:
        return

    font_scale = 0.38
    thickness = 1
    line_gap = 3
    padding = 4

    text_sizes = [cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness) for line in lines]
    max_text_w = max((size[0][0] for size in text_sizes), default=0)
    total_text_h = sum(size[0][1] for size in text_sizes) + line_gap * (len(lines) - 1)

    box_x1 = x1
    box_x2 = min(x1 + max_text_w + padding * 2, image.shape[1] - 1)
    box_y2 = max(y1 - 6, 0)
    box_y1 = max(box_y2 - total_text_h - padding * 2, 0)

    cv2.rectangle(image, (box_x1, box_y1), (box_x2, box_y2), color, -1)

    current_y = box_y1 + padding
    for line, ((text_w, text_h), baseline) in zip(lines, text_sizes):
        current_y += text_h
        cv2.putText(
            image,
            line,
            (box_x1 + padding, current_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (0, 0, 0),
            thickness,
            cv2.LINE_AA,
        )
        current_y += baseline + line_gap


def execute_inference_pipeline(image: np.ndarray, conf: float = 0.25) -> tuple[np.ndarray, dict[str, Any]]:
    detections, yolo_device = detect_people(image, conf=conf)
    annotated = image.copy()
    objects: list[dict[str, Any]] = []
    mobilenet_device: str | None = None

    for index, detection in enumerate(detections):
        bbox = _clip_bbox(detection["bbox"], image.shape[1], image.shape[0])
        crop_bbox = _expand_bbox(bbox, image.shape[1], image.shape[0], padding_ratio=0.2)
        roi = _crop_roi(image, crop_bbox)
        if roi is None:
            continue

        prediction, mobilenet_device = classify_roi(roi)
        di_xa = prediction.get("DI_XA", "KHONG")
        class_lines = [
            f"person conf: {detection['confidence']:.2f}",
            f"DI_XA: {di_xa}",
        ]

        class_lines.extend(
            [
                f"{item['label']}: {item['status']} ({item['confidence'] * 100:.1f}%)"
                for item in prediction.get("classes", [])
            ]
        )

        _draw_label(annotated, crop_bbox, class_lines)

        objects.append(
            {
                "index": index,
                "bbox": crop_bbox,
                "person": {
                    "label": detection["label"],
                    "conf": detection["confidence"],
                    "DI_XA": di_xa,
                    "classes": prediction.get("classes", []),
                },
                "mobilenet_device": mobilenet_device,
            }
        )

    if not objects:
        cv2.putText(
            annotated,
            "No person detected",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

    return annotated, {
        "status": "ok",
        "people_count": len(objects),
        "yolo_device": yolo_device,
        "mobilenet_device": mobilenet_device,
        "objects": objects,
    }


def save_pipeline_result(image: np.ndarray, result: dict[str, Any], output_dir: str = "media/pipeline") -> str:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    filename = f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
    file_path = path / filename
    cv2.imwrite(str(file_path), image)
    return filename
