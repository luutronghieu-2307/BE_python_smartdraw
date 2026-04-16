from __future__ import annotations

import logging
from fastapi import APIRouter
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/status")
async def get_drawer_status() -> dict:
    """Lấy trạng thái drawer hiện tại"""
    try:
        from app.services.drawer_state import get_drawer_state_manager
        from app.services.drawer_item_state import get_drawer_item_state_manager
        
        drawer_manager = get_drawer_state_manager()
        drawer_item_manager = get_drawer_item_state_manager()
        state = drawer_manager.get_state()
        state["has_item"] = drawer_item_manager.has_item
        state["item_updated_at"] = drawer_item_manager.updated_at
        return state
    except Exception as e:
        logger.error(f"Error getting drawer status: {e}")
        return {"error": str(e)}


@router.post("/command/{command}")
async def send_drawer_command(command: str) -> dict:
    """
    Gửi lệnh mở/đóng tủ kéo từ App
    Lệnh từ user app sẽ pause AI detection để tránh conflict
    
    Args:
        command: "open" hoặc "close"
    """
    try:
        from app.services.drawer_controller import send_drawer_command as send_drawer_cmd
        from app.services.drawer_state import get_drawer_state_manager
        
        if command not in ["open", "close"]:
            return {"error": f"Invalid command: {command}, must be 'open' or 'close'"}
        
        # Gọi drawer_controller với is_user_command=True
        # Nó sẽ gọi drawer_manager.send_command(command, is_user_command=True)
        # → Pause AI detection
        success, message = await send_drawer_cmd(command, is_user_command=True)
        
        drawer_manager = get_drawer_state_manager()
        
        if success:
            return {
                "success": True, 
                "command": command, 
                "message": message,
                "ai_paused_until": drawer_manager.pause_until_time
            }
        else:
            return {"success": False, "command": command, "error": message}
            
    except Exception as e:
        logger.error(f"Error sending drawer command: {e}")
        return {"error": str(e)}


@router.post("/app-opened")
async def app_opened() -> dict:
    """
    Flutter gửi signal khi app vừa được mở
    → BE pause drawer control tự động (AI vẫn hoạt động)
    
    Response:
        - paused: True
        - pause_until_time: timestamp khi sẽ auto-resume (60s)
    """
    try:
        from app.services.drawer_state import get_drawer_state_manager
        
        drawer_manager = get_drawer_state_manager()
        
        # Pause ngay lập tức (không cần send MQTT command)
        drawer_manager.pause_ai_detection = True
        drawer_manager.pause_until_time = drawer_manager._get_pause_until_time()
        
        logger.info(f"[Flutter App Opened] Drawer control paused until {drawer_manager.pause_until_time}")
        
        return {
            "success": True,
            "paused": True,
            "pause_until_time": drawer_manager.pause_until_time,
            "message": "Drawer control paused, AI still active for notifications"
        }
    except Exception as e:
        logger.error(f"Error on app opened: {e}")
        return {"success": False, "error": str(e)}


@router.post("/app-closed")
async def app_closed() -> dict:
    """
    Flutter gửi signal khi app được đóng/thoát
    → BE resume drawer control tự động
    
    Response:
        - resumed: True
        - paused: False
    """
    try:
        from app.services.drawer_state import get_drawer_state_manager
        
        drawer_manager = get_drawer_state_manager()
        
        # Resume ngay lập tức
        drawer_manager.pause_ai_detection = False
        drawer_manager.pause_until_time = 0
        
        logger.info("[Flutter App Closed] Drawer control resumed, AI can send commands again")
        
        return {
            "success": True,
            "resumed": True,
            "paused": False,
            "message": "Drawer control resumed"
        }
    except Exception as e:
        logger.error(f"Error on app closed: {e}")
        return {"success": False, "error": str(e)}


@router.get("/wifi-qr")
def get_wifi_qr() -> FileResponse:
    """
    Get WiFi QR code with credentials + server connection info
    Flutter calls this to get QR for auto WiFi connect + backend connection
    """
    try:
        from app.services.light_control import get_qr_path, generate_connection_qr
        
        qr_path = get_qr_path()
        if not qr_path.exists():
            qr_path = generate_connection_qr()
        
        logger.info(f"[Drawer] Returning WiFi QR code from {qr_path}")
        return FileResponse(path=qr_path, media_type="image/png", filename=qr_path.name)
    except Exception as e:
        logger.error(f"Error getting WiFi QR: {e}")
        raise
