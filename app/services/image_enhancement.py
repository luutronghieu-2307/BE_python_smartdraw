from __future__ import annotations

import cv2
import numpy as np

from app.core.config import settings


def enhance_frame_for_ai(frame: np.ndarray) -> np.ndarray:
    """
    Apply lightweight preprocessing to a frame just before AI inference.
    This can include CLAHE or brightness adjustments.
    """
    if not settings.camera_preprocess_enabled:
        return frame

    processed_frame = frame.copy()

    # Apply CLAHE if enabled
    if settings.camera_clahe_clip_limit > 0:
        clahe = cv2.createCLAHE(
            clipLimit=settings.camera_clahe_clip_limit,
            tileGridSize=(settings.camera_clahe_tile_grid_size, settings.camera_clahe_tile_grid_size),
        )
        # Convert to LAB color space, apply CLAHE to L-channel, and convert back
        lab = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l_clahe = clahe.apply(l)
        lab_clahe = cv2.merge((l_clahe, a, b))
        processed_frame = cv2.cvtColor(lab_clahe, cv2.COLOR_LAB2BGR)

    # Apply brightness/contrast adjustment if enabled
    if settings.camera_brightness_alpha != 1.0 or settings.camera_brightness_beta != 0:
        processed_frame = cv2.convertScaleAbs(
            processed_frame,
            alpha=settings.camera_brightness_alpha,
            beta=settings.camera_brightness_beta,
        )

    return processed_frame