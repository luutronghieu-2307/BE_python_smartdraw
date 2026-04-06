from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from threading import Event, RLock, Thread
from typing import Any

import cv2
from vidgear.gears import CamGear

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StreamConfig:
    rtsp_url: str
    use_udp: bool = True
    low_latency: bool = True
    buffer_size: int = 1
    logging: bool = False
    time_delay: int = 0
    open_timeout_ms: int = 5000
    read_timeout_ms: int = 5000
    frame_width: int = 640
    frame_height: int = 360


def _resize_frame(frame: Any) -> Any:
    if frame is None or getattr(frame, "size", 0) == 0:
        return frame

    target_w = max(int(settings.camera_frame_width), 1)
    target_h = max(int(settings.camera_frame_height), 1)
    if frame.shape[1] == target_w and frame.shape[0] == target_h:
        return frame

    return cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)


class ReconnectingVidGearStream:
    def __init__(self, config: StreamConfig, max_reconnect_attempts: int = 5, reconnect_delay: float = 1.0):
        self.config = config
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self._lock = RLock()
        self._stream: CamGear | None = None
        self._last_frame: Any = None
        self._start_stream()

    def _apply_capture_options(self, use_udp: bool | None = None) -> None:
        capture_options: list[str] = []
        transport_use_udp = self.config.use_udp if use_udp is None else use_udp
        if transport_use_udp:
            capture_options.append("rtsp_transport;udp")
        else:
            capture_options.append("rtsp_transport;tcp")
        if self.config.low_latency:
            capture_options.extend(["fflags;nobuffer", "flags;low_delay", "max_delay;0"])

        if settings.camera_disable_autofocus:
            capture_options.append("CAP_PROP_AUTOFOCUS;0")
        if settings.camera_disable_auto_exposure:
            capture_options.append("CAP_PROP_AUTO_EXPOSURE;0.25")
        if settings.camera_disable_auto_white_balance:
            capture_options.append("CAP_PROP_AUTO_WB;0")

        if capture_options:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "|".join(capture_options)

    def _start_stream(self) -> None:
        transports_to_try = [self.config.use_udp, not self.config.use_udp]
        last_error: Exception | None = None

        for transport_use_udp in transports_to_try:
            try:
                self._apply_capture_options(use_udp=transport_use_udp)
                self._stream = CamGear(
                    source=self.config.rtsp_url,
                    logging=self.config.logging,
                    time_delay=self.config.time_delay,
                    **{
                        "CAP_PROP_BUFFERSIZE": self.config.buffer_size,
                        "CAP_PROP_OPEN_TIMEOUT_MSEC": self.config.open_timeout_ms,
                        "CAP_PROP_READ_TIMEOUT_MSEC": self.config.read_timeout_ms,
                        "CAP_PROP_FRAME_WIDTH": self.config.frame_width,
                        "CAP_PROP_FRAME_HEIGHT": self.config.frame_height,
                    },
                ).start()
                return
            except Exception as exc:
                last_error = exc

        raise RuntimeError(f"Failed to start stream with both RTSP transports: {last_error}")

    def read(self):
        with self._lock:
            if self._stream is None:
                return None

            frame = self._stream.read()
            if frame is None:
                return None

            frame = _resize_frame(frame)
            self._last_frame = frame
            return frame

    def stop(self) -> None:
        with self._lock:
            if self._stream is not None:
                self._stream.stop()
                self._stream = None

    @property
    def fps(self) -> float | None:
        if self._stream is None:
            return None
        return getattr(self._stream, "framerate", None)

    @property
    def last_frame(self):
        return self._last_frame


class CameraFrameHub:
    def __init__(self, config: StreamConfig, max_reconnect_attempts: int = 5, reconnect_delay: float = 1.0):
        self.config = config
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self._lock = RLock()
        self._stop_event = Event()
        self._stream: CamGear | None = None
        self._reader_thread: Thread | None = None
        self._latest_frame: Any = None
        self._latest_frame_time: float | None = None
        self._warmup_start = time.time()
        self._last_error: str | None = None
        self._open_stream()
        self._start_reader()

    def _apply_capture_options(self, use_udp: bool | None = None) -> None:
        capture_options: list[str] = []
        transport_use_udp = self.config.use_udp if use_udp is None else use_udp
        if transport_use_udp:
            capture_options.append("rtsp_transport;udp")
        else:
            capture_options.append("rtsp_transport;tcp")
        if self.config.low_latency:
            capture_options.extend(["fflags;nobuffer", "flags;low_delay", "max_delay;0"])

        if settings.camera_disable_autofocus:
            capture_options.append("CAP_PROP_AUTOFOCUS;0")
        if settings.camera_disable_auto_exposure:
            capture_options.append("CAP_PROP_AUTO_EXPOSURE;0.25")
        if settings.camera_disable_auto_white_balance:
            capture_options.append("CAP_PROP_AUTO_WB;0")

        if capture_options:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "|".join(capture_options)

    def _open_stream(self) -> None:
        # Camera chỉ hỗ trợ UDP, chỉ thử UDP với các low_latency options
        transport_options = [
            {"use_udp": True, "low_latency": True},
            {"use_udp": True, "low_latency": False},
        ]
        
        last_error: Exception | None = None

        for options in transport_options:
            try:
                # Apply options
                self._apply_capture_options(use_udp=options["use_udp"])
                
                # Tạo stream với buffer nhỏ hơn cho UDP real-time
                self._stream = CamGear(
                    source=self.config.rtsp_url,
                    logging=self.config.logging,
                    time_delay=0,  # Không delay
                    **{
                        "CAP_PROP_BUFFERSIZE": 2,  # Buffer nhỏ hơn cho UDP real-time
                        "CAP_PROP_OPEN_TIMEOUT_MSEC": 5000,  # 5 giây cho UDP
                        "CAP_PROP_READ_TIMEOUT_MSEC": 5000,
                        "CAP_PROP_FRAME_WIDTH": 640,
                        "CAP_PROP_FRAME_HEIGHT": 360,
                    },
                ).start()
                
                # Test đọc 1 frame để xác nhận stream hoạt động
                test_frame = self._stream.read()
                if test_frame is not None:
                    logger.info(f"Stream opened successfully with UDP=true, low_latency={options['low_latency']}")
                    return
                else:
                    self._stream.stop()
                    self._stream = None
            except Exception as exc:
                if self._stream:
                    try:
                        self._stream.stop()
                    except:
                        pass
                    self._stream = None
                last_error = exc
                logger.warning(f"Failed with UDP=true, low_latency={options['low_latency']}: {exc}")

        raise RuntimeError(f"Failed to open UDP stream: {last_error}")

    def _start_reader(self) -> None:
        self._reader_thread = Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def _reader_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self._stream is None:
                    raise RuntimeError("stream not initialized")

                frame = self._stream.read()
                if frame is None or getattr(frame, "size", 0) == 0:
                    time.sleep(self.reconnect_delay)
                    continue

                frame = _resize_frame(frame)
                now = time.time()
                warmup_elapsed = now - self._warmup_start
                if warmup_elapsed < max(float(settings.camera_capture_warmup_seconds), 0.0):
                    time.sleep(0.05)
                    continue

                with self._lock:
                    self._latest_frame = frame.copy()
                    self._latest_frame_time = now
            except Exception as exc:
                self._last_error = str(exc)
                time.sleep(self.reconnect_delay)

    def get_frame(self):
        with self._lock:
            return None if self._latest_frame is None else self._latest_frame.copy()

    @property
    def fps(self) -> float | None:
        if self._stream is None:
            return None
        return getattr(self._stream, "framerate", None)

    @property
    def last_frame_time(self) -> float | None:
        return self._latest_frame_time

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def stop(self) -> None:
        self._stop_event.set()
        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)
        if self._stream is not None:
            try:
                self._stream.stop()
            finally:
                self._stream = None


_camera_hub: CameraFrameHub | None = None


def get_camera_hub(rtsp_url: str | None = None) -> CameraFrameHub:
    global _camera_hub
    if _camera_hub is None:
        rtsp_url = rtsp_url or settings.rtsp_h264_url or settings.rtsp_url
        if not rtsp_url:
            raise ValueError("rtsp_url is required in arguments or in .env as RTSP_H264_URL or RTSP_URL")

        config = StreamConfig(
            rtsp_url=rtsp_url,
            use_udp=bool(settings.rtsp_use_udp),
            low_latency=bool(settings.rtsp_low_latency),
            buffer_size=3,  # Tăng buffer để giảm mất frame
            logging=False,
            time_delay=1,
            open_timeout_ms=5000,
            read_timeout_ms=5000,
        )
        _camera_hub = CameraFrameHub(config=config)
    return _camera_hub


def initialize_vidgear_stream(
    rtsp_url: str | None = None,
    *,
    use_udp: bool | None = None,
    low_latency: bool | None = None,
    buffer_size: int = 1,
    logging: bool = False,
    time_delay: int = 0,
    open_timeout_ms: int = 5000,
    read_timeout_ms: int = 5000,
) -> ReconnectingVidGearStream:
    """Create and start a VidGear CamGear stream for RTSP cameras.

    The implementation follows VidGear's documented CamGear API:
    - direct RTSP URL via `source`
    - `options` for OpenCV VideoCapture properties such as `CAP_PROP_BUFFERSIZE`

    Low-latency RTSP is applied as a best-effort combination of:
    - OpenCV FFmpeg capture options via `OPENCV_FFMPEG_CAPTURE_OPTIONS`
    - reduced buffer size
    """

    rtsp_url = rtsp_url or settings.rtsp_h264_url or settings.rtsp_url
    if not rtsp_url:
        raise ValueError("rtsp_url is required in arguments or in .env as RTSP_H264_URL or RTSP_URL")

    config = StreamConfig(
        rtsp_url=rtsp_url,
        use_udp=bool(settings.rtsp_use_udp if use_udp is None else use_udp),
        low_latency=bool(settings.rtsp_low_latency if low_latency is None else low_latency),
        buffer_size=buffer_size,
        logging=logging,
        time_delay=time_delay,
        open_timeout_ms=open_timeout_ms,
        read_timeout_ms=read_timeout_ms,
    )
    return ReconnectingVidGearStream(config=config)
