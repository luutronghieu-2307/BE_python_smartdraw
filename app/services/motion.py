from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


def ensure_bgr(frame: np.ndarray) -> np.ndarray:
    if frame is None:
        raise ValueError("frame is required")

    if len(frame.shape) == 2:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    if len(frame.shape) == 3 and frame.shape[2] == 4:
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    return frame


def frame_quality_metrics(frame: np.ndarray) -> dict[str, float]:
    bgr = ensure_bgr(frame)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return {
        "mean": float(gray.mean()),
        "std": float(gray.std()),
        "laplacian_var": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
    }


def is_usable_frame(
    frame: np.ndarray,
    *,
    min_std: float = 8.0,
    min_laplacian_var: float = 20.0,
    min_mean: float = 5.0,
    max_mean: float = 250.0,
) -> tuple[bool, dict[str, float]]:
    metrics = frame_quality_metrics(frame)
    usable = (
        metrics["std"] >= min_std
        and metrics["laplacian_var"] >= min_laplacian_var
        and min_mean <= metrics["mean"] <= max_mean
    )
    return usable, metrics


def encode_frame_base64(frame: np.ndarray) -> str:
    ok, buffer = cv2.imencode(".jpg", frame)
    if not ok:
        raise ValueError("failed to encode frame")

    import base64

    return base64.b64encode(buffer.tobytes()).decode("utf-8")


@dataclass(frozen=True)
class MotionConfig:
    diff_threshold: int = 25
    min_motion_area: float = 1500.0
    activation_frames: int = 2
    release_frames: int = 8
    preview_interval_seconds: float = 0.2
    min_frame_std: float = 8.0
    min_frame_laplacian_var: float = 20.0


def detect_motion(
    previous_frame: np.ndarray,
    current_frame: np.ndarray,
    *,
    diff_threshold: int = 25,
    min_motion_area: float = 1500.0,
) -> dict[str, float | bool]:
    prev = ensure_bgr(previous_frame)
    curr = ensure_bgr(current_frame)

    prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    curr_gray = cv2.cvtColor(curr, cv2.COLOR_BGR2GRAY)

    prev_gray = cv2.GaussianBlur(prev_gray, (21, 21), 0)
    curr_gray = cv2.GaussianBlur(curr_gray, (21, 21), 0)

    frame_delta = cv2.absdiff(prev_gray, curr_gray)
    thresh = cv2.threshold(frame_delta, diff_threshold, 255, cv2.THRESH_BINARY)[1]
    thresh = cv2.dilate(thresh, None, iterations=2)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    largest_area = max((cv2.contourArea(contour) for contour in contours), default=0.0)
    motion_pixels = float(cv2.countNonZero(thresh))
    motion_ratio = motion_pixels / float(thresh.size or 1)

    return {
        "motion_detected": largest_area >= min_motion_area,
        "motion_area": float(largest_area),
        "motion_pixels": motion_pixels,
        "motion_ratio": motion_ratio,
    }
