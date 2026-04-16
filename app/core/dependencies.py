from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.db.session import SessionLocal
from app.core.video_stream import VidGearStream

if TYPE_CHECKING:
    from app.core.video_stream import VidGearStream

logger = logging.getLogger(__name__)

# Global instance of the VidGear stream
vidgear_stream: VidGearStream | None = None


def initialize_vidgear_stream():
    """Initializes and starts the global VidGear stream instance."""
    global vidgear_stream
    if vidgear_stream is None:
        try:
            vidgear_stream = VidGearStream().start()
        except Exception:
            logger.exception("Failed to initialize VidGear stream.")
            vidgear_stream = None


def get_optional_vidgear_stream() -> VidGearStream | None:
    """Returns the global VidGear stream instance when available."""
    global vidgear_stream
    if vidgear_stream is None:
        initialize_vidgear_stream()
    return vidgear_stream


def shutdown_vidgear_stream():
    """Stops the global VidGear stream instance."""
    global vidgear_stream
    if vidgear_stream:
        vidgear_stream.stop()
        vidgear_stream = None


def get_vidgear_stream() -> VidGearStream:
    """
    Dependency injector that provides the global VidGear stream instance.
    Raises a RuntimeError if the stream is not initialized.
    """
    stream = get_optional_vidgear_stream()
    if stream is None:
        raise RuntimeError("VidGearStream has not been initialized.")
    return stream


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
