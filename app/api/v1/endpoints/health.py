from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
from fastapi import APIRouter, Depends, Request

from app.core.dependencies import (
    get_optional_vidgear_stream,
    initialize_vidgear_stream,
)
from app.core.video_stream import VidGearStream

router = APIRouter()


def _frame_sharpness(frame: Any) -> float:
    """Return a simple sharpness score based on Laplacian variance."""
    if len(frame.shape) == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        gray = frame
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


@router.get("")
def health_check() -> dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "ok"}


@router.get("/camera", response_model=None)
def camera_health_check(stream: VidGearStream | None = Depends(get_optional_vidgear_stream)) -> dict[str, Any]:
    """
    Checks the health of the camera stream by attempting to read a frame.
    """
    if stream is None:
        return {
            "status": "error",
            "stream_running": False,
            "frame_received": False,
            "detail": "VidGearStream is not available.",
        }

    try:
        # In THREADED_QUEUE_MODE, read() is non-blocking.
        # We can try reading a few times to see if a frame is available.
        frame = None
        for _ in range(10):
            frame = stream.read()
            if frame is not None:
                break
            time.sleep(0.01)

        is_running = stream.is_running
        is_ok = frame is not None
        shape = list(frame.shape) if is_ok else None

        return {
            "status": "ok" if is_ok and is_running else "error",
            "stream_running": is_running,
            "frame_received": is_ok,
            "frame_shape": shape,
        }
    except Exception as exc:
        return {
            "status": "error",
            "stream_running": False,
            "frame_received": False,
            "detail": str(exc),
        }



@router.get("/camera/frame")
def camera_first_frame(request: Request) -> dict[str, str | bool | float | list[int] | None]:
    stream = None
    try:
        stream = initialize_vidgear_stream()

        frame = None
        frame_std = None
        frame_mean = None
        best_frame = None
        best_sharpness = -1.0

        for _ in range(40):
            frame = stream.read()
            if frame is None or getattr(frame, "size", 0) == 0:
                time.sleep(0.2)
                continue

            frame_mean = float(frame.mean())
            frame_std = float(frame.std())
            sharpness = _frame_sharpness(frame)

            if frame_std > 5.0 and sharpness > best_sharpness:
                best_sharpness = sharpness
                best_frame = frame.copy()

            time.sleep(0.2)

        if best_frame is not None:
            frame = best_frame

        if frame is None:
            return {
                "status": "error",
                "frame_received": False,
                "frame_shape": None,
                "image_url": None,
                "frame_mean": frame_mean,
                "frame_std": frame_std,
                "sharpness": None,
                "detail": "No usable frame received from camera.",
            }

        media_path = Path("media") / "camera"
        media_path.mkdir(parents=True, exist_ok=True)

        filename = f"frame_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
        file_path = media_path / filename

        if len(frame.shape) == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif len(frame.shape) == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

        sharpness = _frame_sharpness(frame)

        success = cv2.imwrite(str(file_path), frame)
        if not success:
            return {
                "status": "error",
                "frame_received": True,
                "frame_shape": list(frame.shape),
                "image_url": None,
                "frame_mean": frame_mean,
                "frame_std": frame_std,
                "sharpness": sharpness,
            }

        image_url = request.url_for("media", path=f"camera/{filename}")
        return {
            "status": "ok",
            "frame_received": True,
            "frame_shape": list(frame.shape),
            "image_url": str(image_url),
            "frame_mean": frame_mean,
            "frame_std": frame_std,
            "sharpness": sharpness,
        }
    except Exception as exc:
        return {
            "status": "error",
            "frame_received": False,
            "frame_shape": None,
            "image_url": None,
            "frame_mean": frame_mean if "frame_mean" in locals() else None,
            "frame_std": frame_std if "frame_std" in locals() else None,
            "sharpness": None,
            "detail": str(exc),
        }
    finally:
        if stream is not None:
            stream.stop()


@router.get("/camera/stability")
def camera_stream_stability(
    duration_seconds: int = 10,
    max_empty_reads: int = 5,
) -> dict[str, str | bool | float | int | None]:
    stream = None
    try:
        stream = initialize_vidgear_stream()

        start_time = time.time()
        received_frames = 0
        empty_reads = 0
        first_frame_time = None
        last_frame_time = None
        frame_intervals: list[float] = []

        while time.time() - start_time < duration_seconds:
            frame = stream.read()
            now = time.time()

            if frame is None or getattr(frame, "size", 0) == 0:
                empty_reads += 1
                if empty_reads >= max_empty_reads:
                    break
                time.sleep(0.1)
                continue

            empty_reads = 0
            received_frames += 1

            if first_frame_time is None:
                first_frame_time = now
            if last_frame_time is not None:
                frame_intervals.append(now - last_frame_time)
            last_frame_time = now

            time.sleep(0.03)

        elapsed = max(time.time() - start_time, 0.001)
        avg_interval = sum(frame_intervals) / len(frame_intervals) if frame_intervals else None
        estimated_fps = received_frames / elapsed

        return {
            "status": "ok" if received_frames > 0 else "error",
            "stream_open": True,
            "received_frames": received_frames,
            "empty_reads": empty_reads,
            "duration_seconds": float(elapsed),
            "estimated_fps": float(estimated_fps),
            "avg_frame_interval": float(avg_interval) if avg_interval is not None else None,
            "first_frame_delay": float(first_frame_time - start_time) if first_frame_time is not None else None,
        }
    except Exception as exc:
        return {
            "status": "error",
            "stream_open": False,
            "received_frames": 0,
            "empty_reads": 0,
            "duration_seconds": None,
            "estimated_fps": None,
            "avg_frame_interval": None,
            "first_frame_delay": None,
            "detail": str(exc),
        }
    finally:
        if stream is not None:
            stream.stop()


