"""
Frame buffer for WebSocket streaming.

Provides an asyncio‑based frame buffer that decouples camera reading from
WebSocket sending, introducing a configurable delay for more stable streaming.
"""

import asyncio
from collections import deque
from typing import Optional, Tuple, Any
import numpy as np

from app.core.logger import get_logger

logger = get_logger(__name__)


class FrameBuffer:
    """Asyncio frame buffer with fixed capacity and automatic old‑frame eviction.

    When the buffer is full, the oldest frame is discarded before inserting the new one,
    ensuring the buffer always contains the most recent frames.

    Attributes:
        maxsize: Maximum number of frames the buffer can hold.
        queue: asyncio.Queue storing (frame, frame_time) tuples.
    """

    def __init__(self, maxsize: int = 5):
        """Initialize the buffer.

        Args:
            maxsize: Maximum number of frames to buffer (default 5).
        """
        if maxsize < 1:
            raise ValueError("maxsize must be at least 1")
        self.maxsize = maxsize
        self._queue: asyncio.Queue[Tuple[np.ndarray, float]] = asyncio.Queue(maxsize=maxsize)
        self._dropped_frames = 0
        self._total_frames = 0

    async def put_frame(self, frame: np.ndarray, frame_time: float) -> None:
        """Insert a frame into the buffer.

        If the buffer is full, the oldest frame is removed before insertion,
        guaranteeing that the newest frame is always stored.

        Args:
            frame: BGR image as numpy array.
            frame_time: Timestamp of the frame (seconds since epoch).
        """
        self._total_frames += 1
        if self._queue.full():
            try:
                self._queue.get_nowait()
                self._dropped_frames += 1
            except asyncio.QueueEmpty:
                pass
        await self._queue.put((frame, frame_time))

    async def get_frame(self, timeout: Optional[float] = None) -> Tuple[np.ndarray, float]:
        """Retrieve the next frame from the buffer.

        Args:
            timeout: Maximum seconds to wait for a frame. If None, waits indefinitely.

        Returns:
            Tuple of (frame, frame_time).

        Raises:
            asyncio.TimeoutError: If timeout is reached and no frame is available.
        """
        if timeout is None:
            return await self._queue.get()
        return await asyncio.wait_for(self._queue.get(), timeout=timeout)

    def clear(self) -> None:
        """Remove all frames from the buffer."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    @property
    def size(self) -> int:
        """Current number of frames in the buffer."""
        return self._queue.qsize()

    @property
    def is_empty(self) -> bool:
        """True if the buffer contains no frames."""
        return self._queue.empty()

    @property
    def is_full(self) -> bool:
        """True if the buffer has reached its capacity."""
        return self._queue.full()

    @property
    def stats(self) -> dict:
        """Return buffer statistics."""
        return {
            "size": self.size,
            "maxsize": self.maxsize,
            "dropped_frames": self._dropped_frames,
            "total_frames": self._total_frames,
            "is_empty": self.is_empty,
            "is_full": self.is_full,
        }


async def frame_producer(
    hub,
    buffer: FrameBuffer,
    stop_event: asyncio.Event,
    poll_interval: float = 0.01,
) -> None:
    """Coroutine that continuously reads frames from a camera hub and pushes them into a buffer.

    This function runs until `stop_event` is set. It reads the latest frame from the hub
    (using a thread‑pool to avoid blocking the asyncio loop) and inserts it into the buffer.

    Args:
        hub: CameraFrameHub instance (must have `get_frame` and `last_frame_time`).
        buffer: FrameBuffer instance.
        stop_event: asyncio.Event that signals the producer to stop.
        poll_interval: Seconds to sleep when no new frame is available.
    """
    logger.info("Frame producer started")
    last_frame_time = None
    loop = asyncio.get_running_loop()

    while not stop_event.is_set():
        try:
            # Read frame from hub in a separate thread to avoid blocking
            frame = await loop.run_in_executor(None, hub.get_frame)
            frame_time = hub.last_frame_time

            if frame is None or frame_time is None:
                await asyncio.sleep(poll_interval)
                continue

            # Skip duplicate frames (same timestamp)
            if frame_time == last_frame_time:
                await asyncio.sleep(poll_interval)
                continue

            last_frame_time = frame_time
            await buffer.put_frame(frame, frame_time)
        except Exception as e:
            logger.warning(f"Error in frame producer: {e}")
            await asyncio.sleep(poll_interval)

    logger.info("Frame producer stopped")