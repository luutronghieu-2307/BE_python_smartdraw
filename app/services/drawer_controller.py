"""
Drawer Controller - gửi lệnh đến ESP32 và chờ confirmation
"""
import asyncio
import logging
from typing import Optional

from app.core.config import settings
from app.services.drawer_state import get_drawer_state_manager, DrawerSyncResult

logger = logging.getLogger(__name__)


async def send_drawer_command(target_state: str, timeout_seconds: Optional[int] = None, is_user_command: bool = False) -> tuple[bool, str]:
    """
    Gửi lệnh mở/đóng tủ kéo từ detection sang ESP32
    
    Args:
        target_state: "open" hoặc "close"
        timeout_seconds: Timeout để chờ response (mặc định từ config)
        is_user_command: True nếu từ user app (pause AI detection), False nếu từ auto detection
        
    Returns:
        tuple: (success, message)
            - success: True nếu ESP32 xác nhận, False nếu timeout/error
            - message: Thông tin chi tiết
    """
    try:
        from app.services.mqtt_client import get_mqtt_client
        
        drawer_manager = get_drawer_state_manager()
        
        # 1. Kiểm tra drawer có enabled không
        if not settings.drawer_enable_sync:
            logger.info(f"Drawer sync disabled, skipping command: {target_state}")
            return False, "drawer_sync_disabled"
        
        # 2. Gửi lệnh cấp cao từ app mà không chờ ESP32 confirm
        if is_user_command:
            should_send, _ = drawer_manager.send_command(
                target_state,
                is_user_command=True,
                wait_for_confirmation=False,
            )
            command = target_state
        else:
            should_send, command = drawer_manager.send_command(target_state, is_user_command=False)
        
        if not should_send:
            logger.warning(f"Drawer already syncing or invalid target_state: {target_state}")
            return False, "already_syncing"
        
        # 3. Publish lệnh sang MQTT
        mqtt_client = get_mqtt_client()
        success = mqtt_client.publish_drawer_control(command) if is_user_command else mqtt_client.publish_drawer_command(command)
        
        if not success:
            logger.error(f"Failed to publish drawer command: {command}")
            if not is_user_command:
                drawer_manager.on_command_timeout()
            return False, "publish_failed"
        
        logger.info(f"Drawer command sent: {command}")

        if is_user_command:
            return True, "success"
        
        # 4. Chờ confirmation từ ESP32 (với timeout)
        timeout = timeout_seconds or settings.drawer_command_timeout_seconds
        start_time = asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else None
        
        # Poll drawer state manager để chờ confirmation
        try:
            # Timeout sẽ được trigger automaticually bởi on_command_timeout() nếu ESP32 không respond
            # Di chuyển timeout check vào một separate monitoring task
            await asyncio.sleep(timeout + 0.5)  # Chờ thêm 0.5s để daemon check timeout
            
            state = drawer_manager.get_state()
            if state["is_syncing"]:
                logger.error(f"Drawer command timeout after {timeout}s: no response from ESP32")
                drawer_manager.on_command_timeout()
                return False, "timeout"
            
            return True, "success"
            
        except asyncio.CancelledError:
            logger.info("Drawer command task cancelled")
            return False, "cancelled"
        except Exception as e:
            logger.error(f"Error waiting for drawer confirmation: {e}")
            drawer_manager.on_command_timeout()
            return False, f"error: {e}"
        
    except Exception as e:
        logger.error(f"Error in send_drawer_command: {e}")
        return False, f"error: {e}"


async def get_drawer_status() -> dict:
    """
    Lấy trạng thái drawer hiện tại
    
    Returns:
        dict: Trạng thái chi tiết (current_state, is_syncing, stats, etc)
    """
    try:
        drawer_manager = get_drawer_state_manager()
        return drawer_manager.get_state()
    except Exception as e:
        logger.error(f"Error getting drawer status: {e}")
        return {"error": str(e)}
