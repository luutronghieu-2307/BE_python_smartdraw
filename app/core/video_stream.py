from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import cv2
import numpy as np
from vidgear.gears import CamGear

from app.core.config import settings

logger = logging.getLogger(__name__)


def _resize_frame(frame: Any) -> Any:
    """Resizes a frame to the target dimensions if necessary."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return None

    target_w = max(int(settings.camera_frame_width), 1)
    target_h = max(int(settings.camera_frame_height), 1)

    if frame.shape[1] == target_w and frame.shape[0] == target_h:
        return frame

    return cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)


class VidGearStream:
    """
    A wrapper around VidGear's CamGear to manage an RTSP stream
    using THREADED_QUEUE_MODE and advanced FFmpeg options for robustness.
    """

    def __init__(self):
        self._stream: CamGear | None = None
        self._capture: cv2.VideoCapture | None = None
        self._reader_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._latest_frame: Any | None = None
        self._lock = threading.Lock()
        self._mode: str | None = None
        self._waiting_for_keyframe = False
        self._corruption_gray_ratio_threshold = 0.80
        self._corruption_std_threshold = 8.0
        self._corruption_tolerance = 12
        source = settings.rtsp_h264_url or settings.rtsp_url

        if not source:
            logger.warning("No RTSP source configured; VidGear stream will not be started.")
            return

        self._apply_ffmpeg_capture_options(source)

        camgear_kwargs: dict[str, Any] = {
            "source": source,
            "backend": cv2.CAP_FFMPEG,
            "time_delay": 1,
            "logging": True,
            **{"THREADED_QUEUE_MODE": True},
        }

        if source.startswith(("http://", "https://")):
            camgear_kwargs["stream_mode"] = True

        source_options: dict[str, Any] = {}
        if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
            source_options["CAP_PROP_BUFFERSIZE"] = 1
        if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
            source_options["CAP_PROP_OPEN_TIMEOUT_MSEC"] = int(settings.camera_capture_warmup_seconds * 1000)
        if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
            source_options["CAP_PROP_READ_TIMEOUT_MSEC"] = 5000

        camgear_kwargs.update(source_options)

        try:
            self._stream = CamGear(**camgear_kwargs)
            self._mode = "camgear"
            logger.info("VidGear stream initialized with CamGear backend.")
        except Exception as exc:
            logger.warning("CamGear initialization failed, falling back to OpenCV VideoCapture: %s", exc)
            self._stream = None
            self._mode = "capture"
            self._capture = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
            if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
                self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not self._capture.isOpened():
                logger.error("OpenCV VideoCapture also failed to open source: %s", source)
                self._capture.release()
                self._capture = None
                self._mode = None
            else:
                logger.info("VidGear stream initialized with OpenCV VideoCapture fallback.")

    def _apply_ffmpeg_capture_options(self, source: str) -> None:
        """Apply OpenCV FFmpeg capture options for RTSP streams."""
        if not source.startswith("rtsp://"):
            return

        transport = "udp" if settings.rtsp_use_udp else "tcp"
        capture_options = self._ffmpeg_discard_policy([f"rtsp_transport;{transport}"])

        if settings.rtsp_low_latency:
            capture_options.extend([
                "fflags;nobuffer",
                "flags;low_delay",
                "max_delay;0",
                "probesize;32",
                "analyzeduration;0",
                "err_detect;ignore_err",
            ])

        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "|".join(capture_options)
        logger.info("Applied OpenCV FFmpeg capture options: %s", os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"])

    def _ffmpeg_discard_policy(self, capture_options: list[str]) -> list[str]:
        """Add FFmpeg discard policy to ignore corrupt packets and incomplete frames."""
        return capture_options + [
            "flags2;+chunks",
            "discardcorrupt;1",
            "err_detect;ignore_err",
        ]

    def check_frame_corruption(self, frame: Any) -> bool:
        """Quick frame-quality check to catch obviously corrupted frames."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return True

        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        gray = np.asarray(gray)
        if gray.size == 0:
            return True

        std_dev = float(gray.std())
        near_gray_ratio = float(np.mean(np.abs(gray.astype(np.int16) - 128) <= self._corruption_tolerance))
        dynamic_range = int(gray.max()) - int(gray.min())

        return (
            std_dev < self._corruption_std_threshold
            or near_gray_ratio >= self._corruption_gray_ratio_threshold
            or dynamic_range < 18
        )

    def clear_stale_buffer(self, max_frames: int = 30) -> None:
        """Flush buffered frames to avoid processing stale or corrupted data."""
        with self._lock:
            self._latest_frame = None

        if self._stream is not None:
            for _ in range(max_frames):
                if self._stream.read() is None:
                    break
            return

        if self._capture is not None:
            for _ in range(max_frames):
                ok, _ = self._capture.read()
                if not ok:
                    break

    def wait_for_next_keyframe(self) -> None:
        """Enter waiting state until a clean I-frame-like frame arrives."""
        if not self._waiting_for_keyframe:
            logger.warning("Corrupted frame detected; waiting for the next keyframe-like clean frame.")
        self._waiting_for_keyframe = True
        self.clear_stale_buffer()

    def start(self) -> "VidGearStream":
        """Starts the stream reading thread."""
        self._stop_event.clear()
        if self._stream:
            self._stream.start()
            logger.info("VidGear stream started in THREADED_QUEUE_MODE.")
        elif self._capture and self._reader_thread is None:
            self._reader_thread = threading.Thread(target=self._capture_loop, name="capture-reader", daemon=True)
            self._reader_thread.start()
            logger.info("OpenCV VideoCapture reader thread started.")
        return self

    def _capture_loop(self) -> None:
        """Continuously read frames from OpenCV VideoCapture into the latest-frame buffer."""
        while not self._stop_event.is_set() and self._capture is not None:
            ok, frame = self._capture.read()
            if not ok or frame is None or getattr(frame, "size", 0) == 0:
                time.sleep(0.05)
                continue

            if self.check_frame_corruption(frame):
                self.wait_for_next_keyframe()
                time.sleep(0.03)
                continue

            if self._waiting_for_keyframe:
                logger.info("Recovered from corrupted frames on a clean keyframe-like frame.")
                self._waiting_for_keyframe = False

            resized = _resize_frame(frame)
            if resized is None:
                time.sleep(0.01)
                continue

            with self._lock:
                self._latest_frame = resized

    def read(self) -> Any | None:
        """
        Reads a frame from VidGear's internal queue.
        This is a non-blocking call. Returns None if queue is empty.
        """
        if self._stream:
            frame = self._stream.read()
            if frame is None:
                return None

            if self.check_frame_corruption(frame):
                self.wait_for_next_keyframe()
                return None

            if self._waiting_for_keyframe:
                logger.info("Recovered from corrupted frames on a clean keyframe-like frame.")
                self._waiting_for_keyframe = False

            # VidGear in threaded mode doesn't always respect capture properties,
            # so we resize manually to ensure consistency.
            return _resize_frame(frame)

        if self._capture is None:
            return None

        if self._waiting_for_keyframe:
            return None

        with self._lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def stop(self) -> None:
        """Stops the stream and cleans up resources."""
        self._stop_event.set()
        if self._stream:
            self._stream.stop()
            self._stream = None
            logger.info("VidGear stream stopped.")
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2.0)
        self._reader_thread = None
        if self._capture is not None:
            self._capture.release()
            self._capture = None
            logger.info("OpenCV VideoCapture stopped.")
        self._waiting_for_keyframe = False

    @property
    def is_running(self) -> bool:
        """Checks if the stream thread is alive."""
        if self._stream is not None:
            return True
        return self._capture is not None and self._reader_thread is not None and self._reader_thread.is_alive()
