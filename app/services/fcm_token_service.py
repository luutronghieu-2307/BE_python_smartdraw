from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.fcm_token import FCMToken


def upsert_fcm_token(
    db: Session,
    token: str,
    platform: str | None = None,
    device_id: str | None = None,
) -> FCMToken:
    token = token.strip()
    existing = db.query(FCMToken).filter(FCMToken.token == token).first()
    if existing:
        existing.platform = platform
        existing.device_id = device_id
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing

    record = FCMToken(token=token, platform=platform, device_id=device_id, is_active=True)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_active_tokens(db: Session) -> list[str]:
    rows = db.query(FCMToken.token).filter(FCMToken.is_active.is_(True)).all()
    return [row[0] for row in rows]
