from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Any

import cv2

from app.core.config import settings
from app.core.video_stream import VidGearStream
from app.services.pipeline import execute_inference_pipeline

logger = logging.getLogger(__name__)

TARGET_FPS = 15.0
TARGET_FRAME_INTERVAL = 1.0 / TARGET_FPS

_viewer_thread: threading.Thread | None = None
_viewer_stop_event = threading.Event()


def _has_display() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _draw_status(frame: Any, status: str, fps: float, frame_index: int) -> Any:
    overlay = frame.copy()
    cv2.putText(overlay, f"Status: {status}", (16, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(overlay, f"FPS: {fps:.1f} / target {TARGET_FPS:.0f}", (16, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
    cv2.putText(overlay, f"Frame: {frame_index}", (16, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    return overlay


def _viewer_loop() -> None:
    stream: VidGearStream | None = None

    window_name = f"{settings.app_name} - Live Stream"
    try:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, settings.camera_frame_width, settings.camera_frame_height)
    except Exception as exc:
        logger.exception("OpenCV window initialization failed: %s", exc)
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    frame_index = 0
    last_display = None
    next_frame_time = time.monotonic()

    try:
        while not _viewer_stop_event.is_set():
            loop_start = time.monotonic()
            next_frame_time = max(next_frame_time, loop_start)

            if stream is None or not stream.is_running:
                if stream is not None:
                    stream.stop()
                try:
                    stream = VidGearStream().start()
                except Exception as exc:
                    logger.warning("Failed to initialize camera stream, retrying: %s", exc)
                    stream = None
                    time.sleep(2.0)
                    continue

                if not stream.is_running:
                    logger.warning("Camera stream is not ready yet, retrying...")
                    stream.stop()
                    stream = None
                    time.sleep(2.0)
                    continue

            frame = stream.read()
            if frame is None or getattr(frame, "size", 0) == 0:
                time.sleep(0.01)
                continue

            frame_index += 1
            display_frame = frame

            if frame_index % max(int(settings.pipeline_ai_frame_stride), 1) == 0:
                try:
                    display_frame, payload = loop.run_until_complete(execute_inference_pipeline(frame))
                    status = f"AI OK | people={len(payload.get('objects', []))}"
                except Exception as exc:
                    logger.exception("Live viewer inference failed")
                    display_frame = frame
                    status = f"AI error: {exc}"
            else:
                status = "Camera live"

            display_frame = _draw_status(display_frame, status, TARGET_FPS, frame_index)
            last_display = display_frame
            cv2.imshow(window_name, display_frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break

            # Calculate how long the processing took
            loop_end = time.monotonic()
            processing_time = loop_end - loop_start
            
            # Calculate remaining time to maintain TARGET_FPS
            sleep_time = TARGET_FRAME_INTERVAL - processing_time
            if sleep_time > 0:
                time.sleep(sleep_time)
    finally:
        _viewer_stop_event.set()
        if stream is not None:
            stream.stop()
        cv2.destroyAllWindows()
        loop.close()
        if last_display is not None:
            logger.info("Desktop viewer closed after %s frames.", frame_index)


def start_desktop_viewer() -> bool:
    """Start the local desktop viewer window once."""
    global _viewer_thread

    if not _has_display():
        logger.warning("No DISPLAY/WAYLAND_DISPLAY found; skipping desktop viewer.")
        return False

    if _viewer_thread and _viewer_thread.is_alive():
        return True

    _viewer_stop_event.clear()
    _viewer_thread = threading.Thread(target=_viewer_loop, name="desktop-live-viewer", daemon=True)
    _viewer_thread.start()
    return True


def stop_desktop_viewer() -> None:
    """Stop the desktop viewer window."""
    global _viewer_thread
    _viewer_stop_event.set()
    if _viewer_thread and _viewer_thread.is_alive():
        _viewer_thread.join(timeout=2.0)
    _viewer_thread = None