from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from app.core.config import settings
from app.core.video_stream import get_camera_hub
from app.services.motion import encode_frame_base64, ensure_bgr
from app.services.pipeline import execute_inference_pipeline
from app.core.frame_buffer import FrameBuffer, frame_producer

router = APIRouter()


@router.post("/upload")
async def pipeline_upload(
    request: Request,
    file: UploadFile = File(...),
    conf: float = settings.yolo_conf_threshold,
) -> dict[str, object]:
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    np_buffer = np.frombuffer(contents, dtype=np.uint8)
    image = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    annotated_image, payload = execute_inference_pipeline(image, conf=conf)

    media_path = Path("media") / "pipeline"
    media_path.mkdir(parents=True, exist_ok=True)

    filename = f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
    file_path = media_path / filename
    success = cv2.imwrite(str(file_path), annotated_image)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save annotated image")

    image_url = request.url_for("media", path=f"pipeline/{filename}")

    return {
        **payload,
        "image_url": str(image_url),
    }


@router.get("/ws/view", response_class=HTMLResponse)
def pipeline_websocket_view(request: Request) -> HTMLResponse:
        ws_url = str(request.url_for("pipeline_websocket")).replace("http://", "ws://").replace("https://", "wss://")
        html = f"""
        <!doctype html>
        <html lang="vi">
            <head>
                <meta charset="utf-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
                <title>Pipeline WebSocket Live Preview</title>
                <style>
                    body {{ margin: 0; background: #0b1220; color: #e5e7eb; font-family: Inter, Arial, sans-serif; }}
                    .wrap {{ max-width: 1280px; margin: 0 auto; padding: 20px; }}
                    .card {{ background: #111827; border: 1px solid #243041; border-radius: 16px; padding: 16px; box-shadow: 0 12px 40px rgba(0,0,0,.25); }}
                    img {{ width: 100%; display: block; border-radius: 12px; background: #000; }}
                    .meta {{ margin-top: 12px; display: grid; gap: 8px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }}
                    .pill {{ padding: 10px 12px; border-radius: 999px; background: #1f2937; border: 1px solid #334155; }}
                    a {{ color: #93c5fd; }}
                </style>
            </head>
            <body>
                <div class="wrap">
                    <h2>Pipeline WebSocket AI Preview</h2>
                    <p>WebSocket URL: <a href="{ws_url}">{ws_url}</a></p>
                    <div class="card">
                        <img id="preview" alt="pipeline preview" />
                        <div class="meta">
                            <div class="pill" id="state">State: waiting</div>
                            <div class="pill" id="resolution">Resolution: 640x360</div>
                        </div>
                    </div>
                </div>
                <script>
                    const ws = new WebSocket("{ws_url}?send_frames=true");
                    const preview = document.getElementById('preview');
                    const state = document.getElementById('state');

                    ws.onmessage = (event) => {{
                        const data = JSON.parse(event.data);
                        state.textContent = `State: ${'{'}data.status || data.type{'}'}`;

                        if (data.frame_b64) {{
                            preview.src = `data:image/jpeg;base64,${'{'}data.frame_b64{'}'}`;
                        }}
                    }};

                    ws.onclose = () => {{ state.textContent = 'State: disconnected'; }};
                    ws.onerror = () => {{ state.textContent = 'State: error'; }};
                </script>
            </body>
        </html>
        """
        return HTMLResponse(content=html)


@router.websocket("/ws")
async def pipeline_websocket(
    websocket: WebSocket,
    send_frames: bool = True,
) -> None:
    await websocket.accept()

    try:
        hub = get_camera_hub()
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "status": "camera_connection_failed",
            "detail": f"Failed to connect to camera: {str(e)}",
            "suggestion": "Check RTSP URL and network connection"
        })
        await asyncio.sleep(1)
        await websocket.close()
        return

    # Buffer configuration
    buffer_maxsize = settings.pipeline_buffer_maxsize
    buffer = FrameBuffer(maxsize=buffer_maxsize)
    stop_event = asyncio.Event()
    producer_task = asyncio.create_task(
        frame_producer(hub, buffer, stop_event, poll_interval=0.01)
    )

    warmup_seconds = max(float(settings.pipeline_stream_warmup_seconds), 0.0)
    ai_stride = max(int(settings.pipeline_ai_frame_stride), 1)
    start_time = asyncio.get_running_loop().time()
    last_sent_frame_time: float | None = None
    last_preview_sent_at = 0.0
    frame_index = 0
    last_ai_frame = None
    last_ai_payload: dict[str, object] | None = None

    try:
        while True:
            now = asyncio.get_running_loop().time()
            elapsed = now - start_time

            if elapsed < warmup_seconds:
                await websocket.send_json(
                    {
                        "type": "status",
                        "status": "warming_up_stream",
                        "ai_active": False,
                        "sleeping": True,
                        "warmup_seconds": warmup_seconds,
                        "warmup_remaining": max(warmup_seconds - elapsed, 0.0),
                    }
                )
                await asyncio.sleep(0.2)
                continue

            # Get frame from buffer (non‑blocking with short timeout)
            try:
                frame, frame_time = await buffer.get_frame(timeout=0.1)
            except asyncio.TimeoutError:
                # No frame available, send status and continue
                await websocket.send_json(
                    {
                        "type": "status",
                        "status": "waiting_for_frame",
                        "frame_received": False,
                        "last_error": hub.last_error,
                    }
                )
                await asyncio.sleep(0.1)
                continue
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "status": "frame_read_error",
                    "detail": str(e),
                    "last_error": hub.last_error if hasattr(hub, 'last_error') else None
                })
                await asyncio.sleep(0.5)
                continue

            if frame is None or frame_time is None:
                await websocket.send_json(
                    {
                        "type": "status",
                        "status": "waiting_for_frame",
                        "frame_received": False,
                        "last_error": hub.last_error,
                    }
                )
                await asyncio.sleep(0.1)
                continue

            # Skip duplicate frames (same timestamp)
            if frame_time == last_sent_frame_time:
                continue

            last_sent_frame_time = frame_time
            frame = ensure_bgr(frame)
            frame_index += 1

            if last_ai_frame is None or frame_index % ai_stride == 0:
                ai_frame, ai_payload = execute_inference_pipeline(frame, conf=float(settings.yolo_conf_threshold))
                last_ai_frame = ai_frame
                last_ai_payload = ai_payload
            else:
                ai_frame = last_ai_frame
                ai_payload = last_ai_payload or {
                    "status": "ok",
                    "people_count": 0,
                    "objects": [],
                }

            # Rate limit sending (max 30 FPS)
            if now - last_preview_sent_at < 0.033:
                continue

            last_preview_sent_at = now
            response = {
                "type": "ai_preview",
                "status": "ok",
                "ai_active": True,
                "sleeping": False,
                "frame_time": frame_time,
                "resolution": [int(ai_frame.shape[1]), int(ai_frame.shape[0])],
                "people_count": ai_payload.get("people_count", 0),
                "objects": ai_payload.get("objects", []),
                "yolo_device": ai_payload.get("yolo_device"),
                "mobilenet_device": ai_payload.get("mobilenet_device"),
            }

            if send_frames:
                response["frame_b64"] = encode_frame_base64(ai_frame)

            await websocket.send_json(response)
    except WebSocketDisconnect:
        # Normal client disconnect
        pass
    except Exception as exc:
        await websocket.send_json(
            {
                "type": "error",
                "status": "error",
                "detail": str(exc),
                "last_error": hub.last_error if "hub" in locals() else None,
            }
        )
    finally:
        # Signal producer to stop and wait for it to finish
        stop_event.set()
        try:
            await asyncio.wait_for(producer_task, timeout=2.0)
        except asyncio.TimeoutError:
            producer_task.cancel()
            try:
                await producer_task
            except (asyncio.CancelledError, Exception):
                pass
