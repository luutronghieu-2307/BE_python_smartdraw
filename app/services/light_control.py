from __future__ import annotations

import json
import logging
import os
import socket
from pathlib import Path
from typing import Any

import qrcode

from app.core.config import settings
from app.services.mqtt_client import get_mqtt_client

logger = logging.getLogger(__name__)

_QR_DIR = Path("media") / "qr"
_QR_PATH = _QR_DIR / settings.app_qr_filename


def _normalize_state(state: str) -> str:
    normalized = state.strip().upper()
    if normalized not in {"ON", "OFF"}:
        raise ValueError("state must be ON or OFF")
    return normalized


def _resolve_public_host() -> str:
    if settings.app_public_host.strip():
        return settings.app_public_host.strip()

    env_host = os.environ.get("APP_PUBLIC_HOST", "").strip()
    if env_host:
        return env_host

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def get_public_base_url() -> str:
    host = _resolve_public_host()
    return f"{settings.app_public_scheme}://{host}:{settings.app_port}"


def build_qr_payload() -> dict[str, Any]:
    """Build QR payload with WiFi credentials and server info."""
    base_url = get_public_base_url()
    payload: dict[str, Any] = {
        "server": {
            "u": base_url,
            "e": "/api/v1/light/control",
        }
    }
    
    # Add WiFi credentials if available
    if settings.wifi_ssid and settings.wifi_password:
        payload["wifi"] = {
            "s": settings.wifi_ssid,
            "p": settings.wifi_password,
        }
    
    return payload


def build_qr_text() -> str:
    """Return JSON payload with WiFi credentials and server info for Flutter.
    
    Format:
    {
      "wifi": {
        "s": "SSID",
        "p": "Password",
        "t": "WPA|WEP|nopass"
      },
      "server": {
        "u": "http://192.168.x.x:8000",
        "e": "/api/v1/light/control"
      }
    }
    
    If WiFi not configured, only server info is included.
    """
    return json.dumps(build_qr_payload(), ensure_ascii=False, separators=(",", ":"))


def generate_connection_qr() -> Path:
    _QR_DIR.mkdir(parents=True, exist_ok=True)
    qr_text = build_qr_text()
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=14, border=6)
    qr.add_data(qr_text)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    image.save(_QR_PATH)
    logger.info("QR connection image saved to %s", _QR_PATH)
    return _QR_PATH


def publish_light_state(state: str, source: str = "api", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_state = _normalize_state(state)
    payload: dict[str, Any] = {
        "target": "light",
        "state": normalized_state,
        "source": source,
    }
    if metadata:
        payload.update(metadata)

    mqtt_client = get_mqtt_client()
    success = mqtt_client.publish(
        settings.mqtt_light_topic,
        json.dumps(payload, ensure_ascii=False),
        qos=1,
        retain=False,
    )
    if not success:
        raise RuntimeError("Failed to publish light command to MQTT")

    return payload


def get_qr_path() -> Path:
    return _QR_PATH
