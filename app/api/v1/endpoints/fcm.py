from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.schemas.fcm import FCMTokenRegisterRequest, FCMTokenRegisterResponse
from app.services.fcm_token_service import upsert_fcm_token

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/token", response_model=FCMTokenRegisterResponse)
def register_fcm_token(payload: FCMTokenRegisterRequest, db: Session = Depends(get_db)) -> FCMTokenRegisterResponse:
    upsert_fcm_token(db, payload.token, payload.platform, payload.device_id)
    return FCMTokenRegisterResponse(success=True, message="FCM token registered")