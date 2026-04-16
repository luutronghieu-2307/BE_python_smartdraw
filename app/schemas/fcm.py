from __future__ import annotations

from pydantic import BaseModel, Field


class FCMTokenRegisterRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    platform: str | None = Field(default=None, max_length=32)
    device_id: str | None = Field(default=None, max_length=128)


class FCMTokenRegisterResponse(BaseModel):
    success: bool
    message: str