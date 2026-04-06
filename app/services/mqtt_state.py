"""
MQTT State Manager với rate limiting và logic ON/OFF
"""
import time
import threading
from typing import Optional
from app.core.config import settings


class MQTTStateManager:
    """Quản lý trạng thái MQTT với rate limiting và logic ON/OFF"""
    
    def __init__(self, cooldown_seconds: Optional[int] = None):
        """
        Khởi tạo state manager
        
        Args:
            cooldown_seconds: Thời gian giữa các lần gửi ON (mặc định từ config)
        """
        self.cooldown = cooldown_seconds or settings.mqtt_cooldown_seconds
        self._lock = threading.RLock()
        
        # State variables
        self.current_state = "OFF"  # "ON" hoặc "OFF"
        self.last_publish_time = 0.0  # Thời gian gửi cuối cùng
        self.last_on_time = 0.0  # Thời gian gửi ON cuối cùng
        self.has_sent_off_after_on = False  # Đã gửi OFF sau ON chưa?
        self.last_detection_time = 0.0  # Thời gian detection cuối cùng
        self.last_di_xa_co_time = 0.0  # Thời gian có DI_XA = "CO" cuối cùng
        
    def update_detection(self, has_people: bool, has_di_xa_co: bool) -> tuple[bool, str]:
        """
        Cập nhật trạng thái detection và trả về xem có cần publish không
        
        Args:
            has_people: Có detection người không
            has_di_xa_co: Có ít nhất một người với DI_XA = "CO" không
            
        Returns:
            tuple: (should_publish, message)
                - should_publish: True nếu cần gửi MQTT
                - message: "ON" hoặc "OFF"
        """
        with self._lock:
            current_time = time.time()
            self.last_detection_time = current_time
            
            # Trường hợp 1: Có người và có DI_XA = "CO"
            if has_people and has_di_xa_co:
                # Cập nhật thời gian có DI_XA CO cuối cùng (reset timer OFF)
                self.last_di_xa_co_time = current_time
                # Kiểm tra xem đã qua cooldown chưa
                if current_time - self.last_on_time >= self.cooldown:
                    self.current_state = "ON"
                    self.last_on_time = current_time
                    self.last_publish_time = current_time
                    self.has_sent_off_after_on = False  # Reset flag
                    return True, "ON"
                else:
                    # Vẫn trong cooldown, không gửi gì cả
                    return False, ""
            
            # Trường hợp 2: Không có người HOẶC không có DI_XA = "CO"
            else:
                # Chỉ gửi OFF nếu:
                # 1. Trước đó đang là ON
                # 2. Chưa gửi OFF sau ON
                # 3. Đã qua cooldown kể từ lần có DI_XA CO cuối cùng
                if self.current_state == "ON" and not self.has_sent_off_after_on:
                    if current_time - self.last_di_xa_co_time >= self.cooldown:
                        self.current_state = "OFF"
                        self.last_publish_time = current_time
                        self.has_sent_off_after_on = True
                        return True, "OFF"
                    else:
                        # Chưa đủ cooldown, giữ nguyên ON (không gửi OFF)
                        return False, ""
                else:
                    # Đã là OFF rồi hoặc đã gửi OFF rồi, không gửi lại
                    return False, ""
    
    def force_off(self) -> bool:
        """
        Buộc gửi OFF message (dùng khi shutdown hoặc error)
        
        Returns:
            True nếu cần gửi OFF (trạng thái hiện tại là ON)
        """
        with self._lock:
            if self.current_state == "ON":
                self.current_state = "OFF"
                self.last_publish_time = time.time()
                self.has_sent_off_after_on = True
                return True
            return False
    
    def get_state(self) -> dict:
        """Lấy thông tin trạng thái hiện tại"""
        with self._lock:
            return {
                "current_state": self.current_state,
                "last_publish_time": self.last_publish_time,
                "last_on_time": self.last_on_time,
                "has_sent_off_after_on": self.has_sent_off_after_on,
                "last_detection_time": self.last_detection_time,
                "cooldown_seconds": self.cooldown,
            }


# Global instance để sử dụng trong toàn bộ ứng dụng
_mqtt_state_manager: Optional[MQTTStateManager] = None


def get_mqtt_state_manager() -> MQTTStateManager:
    """Lấy global MQTT state manager instance (singleton)"""
    global _mqtt_state_manager
    if _mqtt_state_manager is None:
        _mqtt_state_manager = MQTTStateManager()
    return _mqtt_state_manager