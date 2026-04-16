from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import cv2
import numpy as np

from app.core.config import settings
from app.services.classification import classify_roi
from app.services.detection import detect_people
from app.services.image_enhancement import enhance_frame_for_ai

logger = logging.getLogger(__name__)


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
    expanded = [x1 - pad_x, y1 - pad_y, x2 + pad_x, y2 + pad_y]
    return _clip_bbox(expanded, width, height)


def _crop_roi(image: np.ndarray, bbox: list[int]) -> np.ndarray | None:
    x1, y1, x2, y2 = bbox
    if x2 <= x1 or y2 <= y1:
        return None
    return image[y1:y2, x1:x2]


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
    box_x1, box_y2 = x1, max(y1 - 6, 0)
    box_x2 = min(x1 + max_text_w + padding * 2, image.shape[1] - 1)
    box_y1 = max(box_y2 - total_text_h - padding * 2, 0)
    cv2.rectangle(image, (box_x1, box_y1), (box_x2, box_y2), color, -1)
    current_y = box_y1 + padding
    for line, ((_, text_h), baseline) in zip(lines, text_sizes):
        current_y += text_h
        cv2.putText(image, line, (box_x1 + padding, current_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)
        current_y += baseline + line_gap


async def execute_inference_pipeline(
    image: np.ndarray, conf: float | None = None
) -> tuple[np.ndarray, dict[str, Any]]:
    """
    Asynchronously executes the AI inference pipeline.
    - Pre-processes the frame (enhancement).
    - Runs person detection (YOLO).
    - Runs attribute classification (MobileNetV2) for each detected person.
    - Annotates the frame with results.
    - Publishes detection status via MQTT.
    """
    if conf is None:
        conf = float(settings.yolo_conf_threshold)

    # 1. Lightweight Preprocessing (just before AI inference)
    enhanced_image = enhance_frame_for_ai(image)

    # 2. Asynchronous AI Detection
    try:
        detections, yolo_device = await asyncio.wait_for(
            asyncio.to_thread(detect_people, enhanced_image, conf),
            timeout=1.0,
        )
    except asyncio.TimeoutError:
        detections, yolo_device = [], "timeout"
    except Exception as e:
        detections, yolo_device = [], f"error: {e}"

    annotated = image.copy()
    objects: list[dict[str, Any]] = []
    mobilenet_device: str | None = None

    for index, detection in enumerate(detections):
        bbox = _clip_bbox(detection["bbox"], image.shape[1], image.shape[0])
        crop_bbox = _expand_bbox(bbox, image.shape[1], image.shape[0])
        roi = _crop_roi(enhanced_image, crop_bbox)
        if roi is None or roi.size == 0:
            continue

        # 3. Asynchronous AI Classification
        try:
            prediction, mobilenet_device = await asyncio.wait_for(
                asyncio.to_thread(classify_roi, roi),
                timeout=0.5,
            )
        except asyncio.TimeoutError:
            prediction = {"DI_XA": "KHONG", "classes": []}
            mobilenet_device = "timeout"
        except Exception as e:
            prediction = {"DI_XA": "KHONG", "classes": []}
            mobilenet_device = f"error: {e}"

        di_xa = prediction.get("DI_XA", "KHONG")
        class_lines = [
            f"person conf: {detection['confidence']:.2f}",
            f"DI_XA: {di_xa}",
            *[f"{item['label']}: {item['status']} ({item['confidence'] * 100:.1f}%)" for item in prediction.get("classes", [])],
        ]
        _draw_label(annotated, crop_bbox, class_lines)
        objects.append({
            "index": index, "bbox": crop_bbox,
            "person": {"label": detection["label"], "conf": detection["confidence"], "DI_XA": di_xa, "classes": prediction.get("classes", [])},
            "mobilenet_device": mobilenet_device,
        })

    if not objects:
        cv2.putText(annotated, "No person detected", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2, cv2.LINE_AA)

    # 4. MQTT Publishing
    _handle_mqtt_publishing(objects)
    _handle_push_notification_decision(objects)

    return annotated, {"objects": objects, "yolo_device": yolo_device}


def _handle_mqtt_publishing(objects: list[dict[str, Any]]) -> None:
    """Handles the logic for publishing detection results to MQTT and sending drawer commands."""
    try:
        from app.services.mqtt_state import get_mqtt_state_manager
        from app.services.mqtt_client import get_mqtt_client
        from app.services.drawer_state import get_drawer_state_manager
        from app.core.config import settings

        has_people = len(objects) > 0
        has_di_xa_co = any(obj.get("person", {}).get("DI_XA") == "CO" for obj in objects)

        state_manager = get_mqtt_state_manager()
        should_publish, message = state_manager.update_detection(has_people, has_di_xa_co)

        # Kiểm tra xem drawer control có bị pause không (user đang điều khiển)
        drawer_manager = get_drawer_state_manager()
        drawer_paused = drawer_manager.is_ai_paused()
        
        if should_publish and message:
            mqtt_client = get_mqtt_client()
            metadata = {
                "people_count": len(objects),
                "has_di_xa_co": has_di_xa_co,
                "detection_time": time.time(),
            }
            
            # Luôn publish detection status (để user biết có người, DI_XA, etc)
            mqtt_client.publish_detection_status(message, metadata)
            
            # Nhưng chỉ gửi drawer command nếu không bị pause
            if not drawer_paused:
                # 5. Gửi lệnh đến drawer nếu enabled
                if settings.drawer_enable_sync:
                    _send_drawer_command_async(message)
            else:
                logger.info(f"Drawer control paused (user command active), skipping drawer command for: {message}")
    except ImportError as e:
        logger.warning(f"MQTT services not available, skipping publish: {e}")
    except Exception as e:
        logger.error(f"Error during MQTT publishing: {e}")


def _handle_push_notification_decision(objects: list[dict[str, Any]]) -> None:
    try:
        from app.services.drawer_item_state import get_drawer_item_state_manager
        from app.services.fcm_token_service import list_active_tokens
        from app.services.notification_service import send_push_notification_to_tokens
        from app.db.session import SessionLocal

        person_detections = [obj for obj in objects if obj.get("person", {}).get("conf", 0.0) > 0.6]
        if not person_detections:
            return

        now = time.time()
        cooldown_seconds = 60
        last_sent_at = getattr(_handle_push_notification_decision, "_last_sent_at", 0.0)
        if now - last_sent_at < cooldown_seconds:
            return

        has_item = get_drawer_item_state_manager().has_item
        if has_item:
            title = "Nhắc bạn"
            body = "Bạn ơi, đừng quên lấy đồ trong ngăn kéo nhé!"
        else:
            title = "Chào mừng"
            body = "Chào mừng bạn về nhà, hãy cất đồ vào ngăn kéo nào!"

        db = SessionLocal()
        try:
            tokens = list_active_tokens(db)
        finally:
            db.close()

        if send_push_notification_to_tokens(title, body, tokens):
            setattr(_handle_push_notification_decision, "_last_sent_at", now)
    except ImportError as exc:
        logger.warning(f"Push notification services not available: {exc}")
    except Exception as exc:
        logger.error(f"Error while deciding push notification: {exc}")


def _send_drawer_command_async(message: str) -> None:
    """
    Gửi lệnh drawer mở/đóng (non-blocking)
    
    Args:
        message: "ON" hoặc "OFF" từ MQTT state manager
    """
    try:
        import asyncio
        from app.services.drawer_controller import send_drawer_command
        
        if message not in ["ON", "OFF"]:
            return
        
        command = "open" if message == "ON" else "close"
        
        # Chạy async command trong background task
        async def _async_wrapper():
            success, msg = await send_drawer_command(command)
            if not success:
                logger.warning(f"Drawer command failed: {command} - {msg}")
            else:
                logger.info(f"Drawer command confirmed: {command}")
        
        # Tạo task mà không chờ
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Không có running loop, tạo task mới
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        asyncio.create_task(_async_wrapper())
        
    except Exception as e:
        logger.error(f"Error sending drawer command: {e}")
