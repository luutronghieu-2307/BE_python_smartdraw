from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time
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


def execute_inference_pipeline(image: np.ndarray, conf: float | None = None) -> tuple[np.ndarray, dict[str, Any]]:
    if conf is None:
        from app.core.config import settings

        conf = float(settings.yolo_conf_threshold)
    
    # Thêm timeout cho detection để tránh block stream
    detections = []
    yolo_device = "cpu"
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(detect_people, image, conf)
            detections, yolo_device = future.result(timeout=1.0)  # Timeout 1 giây
    except concurrent.futures.TimeoutError:
        # Nếu timeout, trả về kết quả rỗng nhưng stream vẫn chạy
        detections = []
        yolo_device = "timeout"
    except Exception as e:
        detections = []
        yolo_device = f"error: {str(e)}"
    
    annotated = image.copy()
    objects: list[dict[str, Any]] = []
    mobilenet_device: str | None = None

    for index, detection in enumerate(detections):
        bbox = _clip_bbox(detection["bbox"], image.shape[1], image.shape[0])
        crop_bbox = _expand_bbox(bbox, image.shape[1], image.shape[0], padding_ratio=0.2)
        roi = _crop_roi(image, crop_bbox)
        if roi is None:
            continue

        # Thêm timeout cho classification
        prediction = {"DI_XA": "KHONG", "classes": []}
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(classify_roi, roi)
                prediction, mobilenet_device = future.result(timeout=0.5)  # Timeout 0.5 giây
        except concurrent.futures.TimeoutError:
            mobilenet_device = "timeout"
        except Exception as e:
            mobilenet_device = f"error: {str(e)}"
        
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

    # MQTT Publishing logic
    try:
        from app.services.mqtt_state import get_mqtt_state_manager
        from app.services.mqtt_client import get_mqtt_client
        
        # Tính toán trạng thái DI_XA
        has_people = len(objects) > 0
        has_di_xa_co = any(obj.get("person", {}).get("DI_XA") == "CO" for obj in objects)
        
        # Cập nhật state và kiểm tra xem có cần publish không
        state_manager = get_mqtt_state_manager()
        should_publish, message = state_manager.update_detection(has_people, has_di_xa_co)
        
        if should_publish and message:
            # Publish đến MQTT
            mqtt_client = get_mqtt_client()
            metadata = {
                "people_count": len(objects),
                "has_di_xa_co": has_di_xa_co,
                "detection_time": time.time(),
                "objects_count": len(objects),
            }
            success = mqtt_client.publish_detection_status(message, metadata)
            
            if success:
                logger = logging.getLogger(__name__)
                logger.info(f"MQTT published: {message} (people: {len(objects)}, DI_XA_CO: {has_di_xa_co})")
            else:
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to publish MQTT: {message}")
                
    except ImportError as e:
        # MQTT module chưa được cài đặt
        pass
    except Exception as e:
        # Log lỗi nhưng không làm crash pipeline
        logger = logging.getLogger(__name__)
        logger.error(f"Error in MQTT publishing: {e}", exc_info=True)
    
    # Thu thập thông tin MQTT state nếu có
    mqtt_state_info = {}
    try:
        from app.services.mqtt_state import get_mqtt_state_manager
        state_manager = get_mqtt_state_manager()
        mqtt_state_info = {
            "current_state": state_manager.current_state,
            "last_publish_time": state_manager.last_publish_time,
            "last_on_time": state_manager.last_on_time,
            "has_sent_off_after_on": state_manager.has_sent_off_after_on,
            "last_detection_time": state_manager.last_detection_time,
            "cooldown_seconds": state_manager.cooldown_seconds,
        }
    except Exception:
        pass
    
    return annotated, {
        "status": "ok",
        "people_count": len(objects),
        "yolo_device": yolo_device,
        "mobilenet_device": mobilenet_device,
        "objects": objects,
        "mqtt_state": mqtt_state_info,
    }


def save_pipeline_result(image: np.ndarray, result: dict[str, Any], output_dir: str = "media/pipeline") -> str:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    filename = f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
    file_path = path / filename
    cv2.imwrite(str(file_path), image)
    return filename
