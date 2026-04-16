"""
Firebase Cloud Messaging helper.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _init_firebase() -> bool:
    import firebase_admin
    from firebase_admin import credentials

    if firebase_admin._apps:
        return True

    cred_path = settings.firebase_credentials_path.strip()
    if not cred_path:
        raise RuntimeError("firebase_credentials_path is not configured")

    path = Path(cred_path)
    if not path.exists():
        raise FileNotFoundError(f"Firebase credentials not found at: {path}")

    firebase_admin.initialize_app(credentials.Certificate(str(path)))
    return True


def send_push_notification(title: str, body: str, topic: str | None = None) -> bool:
    try:
        from firebase_admin import messaging

        _init_firebase()
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            topic=topic or settings.firebase_default_topic,
        )
        messaging.send(message)
        logger.info("Push notification sent: %s", title)
        return True
    except Exception as exc:
        logger.error(f"Failed to send push notification: {exc}")
        return False


def send_push_notification_to_tokens(title: str, body: str, tokens: list[str]) -> int:
    try:
        from firebase_admin import messaging

        if not tokens:
            return 0

        _init_firebase()
        messages = [
            messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                token=token,
            )
            for token in tokens
        ]
        response = messaging.send_each(messages)
        logger.info("FCM sent: success=%s failure=%s", response.success_count, response.failure_count)
        return response.success_count
    except Exception as exc:
        logger.error(f"Failed to send push notification to tokens: {exc}")
        return 0