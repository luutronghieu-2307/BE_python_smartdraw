from __future__ import annotations

import os
import time
from dataclasses import dataclass
from threading import Event, RLock, Thread
from typing import Any

from vidgear.gears import CamGear

from app.core.config import settings


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


class ReconnectingVidGearStream:
    def __init__(self, config: StreamConfig, max_reconnect_attempts: int = 5, reconnect_delay: float = 1.0):
        self.config = config
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self._lock = RLock()
        self._stream: CamGear | None = None
        self._last_frame: Any = None
        self._start_stream()

    def _apply_capture_options(self) -> None:
        capture_options: list[str] = []
        if self.config.use_udp:
            capture_options.append("rtsp_transport;udp")
        if self.config.low_latency:
            capture_options.extend(["fflags;nobuffer", "flags;low_delay", "max_delay;0"])

        if capture_options:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "|".join(capture_options)

    def _start_stream(self) -> None:
        self._apply_capture_options()
        self._stream = CamGear(
            source=self.config.rtsp_url,
            logging=self.config.logging,
            time_delay=self.config.time_delay,
            **{
                "CAP_PROP_BUFFERSIZE": self.config.buffer_size,
                "CAP_PROP_OPEN_TIMEOUT_MSEC": self.config.open_timeout_ms,
                "CAP_PROP_READ_TIMEOUT_MSEC": self.config.read_timeout_ms,
            },
        ).start()

    def reconnect(self) -> bool:
        with self._lock:
            self.stop()
            for _ in range(self.max_reconnect_attempts):
                try:
                    self._start_stream()
                    frame = self._stream.read() if self._stream is not None else None
                    if frame is not None:
                        self._last_frame = frame
                        return True
                except Exception:
                    pass
                time.sleep(self.reconnect_delay)
            return False

    def read(self):
        with self._lock:
            if self._stream is None:
                return None

            frame = self._stream.read()
            if frame is None:
                if self.reconnect():
                    return self._last_frame
                return None

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
        self._last_error: str | None = None
        self._open_stream()
        self._start_reader()

    def _apply_capture_options(self) -> None:
        capture_options: list[str] = []
        if self.config.use_udp:
            capture_options.append("rtsp_transport;udp")
        if self.config.low_latency:
            capture_options.extend(["fflags;nobuffer", "flags;low_delay", "max_delay;0"])

        if capture_options:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "|".join(capture_options)

    def _open_stream(self) -> None:
        self._apply_capture_options()
        self._stream = CamGear(
            source=self.config.rtsp_url,
            logging=self.config.logging,
            time_delay=self.config.time_delay,
            **{
                "CAP_PROP_BUFFERSIZE": self.config.buffer_size,
                "CAP_PROP_OPEN_TIMEOUT_MSEC": self.config.open_timeout_ms,
                "CAP_PROP_READ_TIMEOUT_MSEC": self.config.read_timeout_ms,
            },
        ).start()

    def _start_reader(self) -> None:
        self._reader_thread = Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def _reader_loop(self) -> None:
        consecutive_failures = 0
        while not self._stop_event.is_set():
            try:
                if self._stream is None:
                    raise RuntimeError("stream not initialized")

                frame = self._stream.read()
                if frame is None or getattr(frame, "size", 0) == 0:
                    consecutive_failures += 1
                    if consecutive_failures >= self.max_reconnect_attempts:
                        self._reconnect()
                        consecutive_failures = 0
                    time.sleep(self.reconnect_delay)
                    continue

                consecutive_failures = 0
                with self._lock:
                    self._latest_frame = frame.copy()
                    self._latest_frame_time = time.time()
            except Exception as exc:
                self._last_error = str(exc)
                self._reconnect()
                time.sleep(self.reconnect_delay)

    def _reconnect(self) -> None:
        with self._lock:
            try:
                if self._stream is not None:
                    self._stream.stop()
            except Exception:
                pass
            self._stream = None

        for _ in range(self.max_reconnect_attempts):
            if self._stop_event.is_set():
                return
            try:
                self._open_stream()
                return
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
        rtsp_url = rtsp_url or settings.rtsp_url
        if not rtsp_url:
            raise ValueError("rtsp_url is required in arguments or in .env as RTSP_URL")

        config = StreamConfig(
            rtsp_url=rtsp_url,
            use_udp=True,
            low_latency=True,
            buffer_size=1,
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
    use_udp: bool = True,
    low_latency: bool = True,
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

    rtsp_url = rtsp_url or settings.rtsp_url
    if not rtsp_url:
        raise ValueError("rtsp_url is required in arguments or in .env as RTSP_URL")

    config = StreamConfig(
        rtsp_url=rtsp_url,
        use_udp=use_udp,
        low_latency=low_latency,
        buffer_size=buffer_size,
        logging=logging,
        time_delay=time_delay,
        open_timeout_ms=open_timeout_ms,
        read_timeout_ms=read_timeout_ms,
    )
    return ReconnectingVidGearStream(config=config)
