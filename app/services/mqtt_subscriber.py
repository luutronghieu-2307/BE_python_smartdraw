"""
MQTT Subscriber Handlers để xử lý messages từ các topics
"""
import json
import logging
import time
from typing import Callable, Optional, Dict

from app.core.config import settings

logger = logging.getLogger(__name__)


class MQTTSubscriber:
    """Quản lý MQTT subscriptions và callbacks"""
    
    def __init__(self):
        self._callbacks: Dict[str, Callable] = {}
        self._health_last_update: Dict[str, float] = {}
    
    def register_callback(self, topic: str, callback: Callable[[str, dict], None]) -> None:
        """
        Đăng ký callback cho topic cụ thể
        
        Args:
            topic: Topic name
            callback: Callable(topic, payload_dict)
        """
        self._callbacks[topic] = callback
        logger.info(f"Registered callback for topic: {topic}")
    
    def handle_message(self, topic: str, payload: str) -> None:
        """
        Xử lý message từ broker MQTT
        
        Args:
            topic: Topic name
            payload: Raw payload string
        """
        try:
            data = json.loads(payload)
            logger.debug(f"Received message on {topic}: {data}")
            
            if topic in self._callbacks:
                self._callbacks[topic](topic, data)
            else:
                logger.warning(f"No handler registered for topic: {topic}")
                
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON on {topic}: {payload}")
        except Exception as e:
            logger.error(f"Error handling message on {topic}: {e}")
    
    def health_check(self, topic: str, timeout_seconds: int = 60) -> bool:
        """
        Kiểm tra xem device có còn sống (respond) không
        
        Args:
            topic: Device health topic
            timeout_seconds: Thời gian timeout
            
        Returns:
            True nếu device còn sống, False nếu timeout
        """
        now = time.time()
        last_update = self._health_last_update.get(topic, 0)
        if now - last_update > timeout_seconds:
            logger.warning(f"Health check failed for {topic}: timeout > {timeout_seconds}s")
            return False
        return True
    
    def update_health(self, topic: str) -> None:
        """Cập nhật thời điểm nhận heartbeat từ device"""
        self._health_last_update[topic] = time.time()


# Global subscriber instance
_mqtt_subscriber: Optional[MQTTSubscriber] = None


def get_mqtt_subscriber() -> MQTTSubscriber:
    """Lấy global MQTT subscriber instance"""
    global _mqtt_subscriber
    if _mqtt_subscriber is None:
        _mqtt_subscriber = MQTTSubscriber()
    return _mqtt_subscriber


# Handler cho drawer status (từ ESP32)
def handle_drawer_status(topic: str, payload: dict) -> None:
    """
    Callback khi nhận status từ drawer ESP32
    
    Payload expected: {"status": "ON" | "OFF"}
    """
    try:
        from app.services.drawer_state import get_drawer_state_manager
        
        status = payload.get("status", "").upper()
        if status not in ["ON", "OFF"]:
            logger.warning(f"Invalid drawer status: {status}")
            return
        
        drawer_manager = get_drawer_state_manager()
        result = drawer_manager.on_drawer_status_received(
            "open" if status == "ON" else "close"
        )
        logger.info(f"Drawer status sync result: {result}")
        
    except Exception as e:
        logger.error(f"Error handling drawer status: {e}")


# Handler cho drawer health (ESP32 heartbeat)
def handle_drawer_health(topic: str, payload: dict) -> None:
    """
    Callback khi nhận heartbeat từ drawer ESP32
    
    Payload expected: {"ts": timestamp, "distance": mm}
    """
    try:
        subscriber = get_mqtt_subscriber()
        subscriber.update_health(settings.mqtt_drawer_health_topic)
        logger.debug(f"Drawer health check: OK (distance: {payload.get('distance', 'N/A')}mm)")
        
    except Exception as e:
        logger.error(f"Error handling drawer health: {e}")


def handle_item_status(topic: str, payload: dict) -> None:
    """
    Callback khi nhận trạng thái item trong ngăn kéo từ ESP32.

    Payload expected: {"status": "CO_DO" | "TRONG"}
    """
    try:
        from app.services.drawer_item_state import get_drawer_item_state_manager

        status = payload.get("status", "").upper()
        if status not in ["CO_DO", "TRONG"]:
            logger.warning(f"Invalid item status: {status}")
            return

        item_manager = get_drawer_item_state_manager()
        item_manager.update_has_item(status == "CO_DO")
        logger.info(f"Item status updated from MQTT: has_item={item_manager.has_item}")
    except Exception as e:
        logger.error(f"Error handling item status: {e}")


def register_all_handlers() -> None:
    """Đăng ký tất cả handlers"""
    subscriber = get_mqtt_subscriber()
    subscriber.register_callback(settings.mqtt_drawer_status_topic, handle_drawer_status)
    subscriber.register_callback(settings.mqtt_drawer_health_topic, handle_drawer_health)
    subscriber.register_callback(settings.mqtt_item_status_topic, handle_item_status)
    logger.info("All MQTT handlers registered")
