from __future__ import annotations

import cv2
import numpy as np

from app.core.config import settings
from app.services.motion import ensure_bgr


def enhance_camera_frame(image: np.ndarray) -> np.ndarray:
    frame = ensure_bgr(image)

    if not settings.camera_preprocess_enabled:
        return frame

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray_mean = float(gray.mean())
    gray_std = float(gray.std())

    if (
        gray_std >= float(settings.camera_enhance_min_std)
        and float(settings.camera_enhance_min_mean) <= gray_mean <= float(settings.camera_enhance_max_mean)
    ):
        return frame

    enhanced = frame

    if gray_mean < float(settings.camera_enhance_min_mean):
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)

        tile_size = max(int(settings.camera_clahe_tile_grid_size), 1)
        clahe = cv2.createCLAHE(
            clipLimit=float(settings.camera_clahe_clip_limit),
            tileGridSize=(tile_size, tile_size),
        )
        l_channel = clahe.apply(l_channel)

        merged = cv2.merge((l_channel, a_channel, b_channel))
        enhanced = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)

    elif gray_mean > float(settings.camera_enhance_max_mean):
        enhanced = cv2.convertScaleAbs(
            frame,
            alpha=float(settings.camera_brightness_alpha),
            beta=int(settings.camera_brightness_beta),
        )

    if settings.camera_sharpen_enabled and gray_std < float(settings.camera_enhance_min_std):
        kernel = np.array(
            [
                [0, -1, 0],
                [-1, 5, -1],
                [0, -1, 0],
            ],
            dtype=np.float32,
        )
        enhanced = cv2.filter2D(enhanced, -1, kernel)

    return enhanced