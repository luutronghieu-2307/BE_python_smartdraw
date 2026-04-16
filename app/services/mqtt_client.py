"""
MQTT Client cho SVIOT với connection management và error handling
"""
import json
import logging
import threading
import time
from typing import Optional, Callable

import paho.mqtt.client as mqtt

from app.core.config import settings

logger = logging.getLogger(__name__)


class MQTTClient:
    """MQTT Client với auto-reconnect và thread-safe publishing"""
    
    def __init__(self):
        self.client_id = f"pythonSVIOT_{int(time.time())}"
        self.client = mqtt.Client(client_id=self.client_id, protocol=mqtt.MQTTv311)
        
        # Setup credentials nếu có
        if settings.mqtt_username:
            self.client.username_pw_set(
                settings.mqtt_username, 
                settings.mqtt_password if settings.mqtt_password else None
            )
        
        # Setup callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish
        self.client.on_message = self._on_message
        
        # State
        self._connected = False
        self._lock = threading.RLock()
        self._connection_attempts = 0
        self._max_reconnect_attempts = 5
        self._reconnect_delay = 2  # seconds
        self._message_handler = None  # Handler cho incoming messages
        
    def _on_connect(self, client, userdata, flags, rc):
        """Callback khi kết nối thành công"""
        if rc == 0:
            self._connected = True
            self._connection_attempts = 0
            logger.info(f"MQTT connected to {settings.mqtt_broker}:{settings.mqtt_port}")
        else:
            self._connected = False
            logger.error(f"MQTT connection failed with code {rc}")
    
    def _on_disconnect(self, client, userdata, rc):
        """Callback khi mất kết nối"""
        self._connected = False
        if rc != 0:
            logger.warning(f"MQTT disconnected unexpectedly (code: {rc})")
        else:
            logger.info("MQTT disconnected gracefully")
    
    def _on_publish(self, client, userdata, mid):
        """Callback khi publish thành công"""
        logger.debug(f"MQTT message published (mid: {mid})")
    
    def _on_message(self, client, userdata, msg):
        """Callback khi nhận message từ subscribed topic"""
        if self._message_handler:
            try:
                payload = msg.payload.decode() if isinstance(msg.payload, bytes) else msg.payload
                self._message_handler(msg.topic, payload)
            except Exception as e:
                logger.error(f"Error handling message from {msg.topic}: {e}")
    
    def set_message_handler(self, handler: Callable[[str, str], None]) -> None:
        """
        Set handler cho incoming messages
        
        Args:
            handler: Callable(topic, payload_str)
        """
        self._message_handler = handler
        logger.info("MQTT message handler registered")
    
    def subscribe(self, topic: str, qos: int = 0) -> bool:
        """
        Subscribe đến topic
        
        Args:
            topic: Topic name
            qos: Quality of Service
            
        Returns:
            True nếu subscribe thành công
        """
        with self._lock:
            if not self._connected:
                if not self.connect():
                    logger.warning(f"Cannot subscribe, MQTT not connected")
                    return False
            
            try:
                result = self.client.subscribe(topic, qos=qos)
                if result[0] == mqtt.MQTT_ERR_SUCCESS:
                    logger.info(f"Subscribed to {topic}")
                    return True
                else:
                    logger.error(f"Subscribe failed for {topic} with code {result[0]}")
                    return False
            except Exception as e:
                logger.error(f"Error subscribing to {topic}: {e}")
                return False
    
    def connect(self) -> bool:
        """Kết nối đến MQTT broker"""
        with self._lock:
            if self._connected:
                return True
            
            try:
                logger.info(f"Connecting to MQTT broker at {settings.mqtt_broker}:{settings.mqtt_port}")
                self.client.connect(
                    settings.mqtt_broker,
                    settings.mqtt_port,
                    keepalive=60
                )
                self.client.loop_start()
                
                # Chờ kết nối thành công (timeout 5 giây)
                for _ in range(50):  # 50 * 0.1 = 5 giây
                    if self._connected:
                        return True
                    time.sleep(0.1)
                
                logger.error("MQTT connection timeout")
                return False
                
            except Exception as e:
                logger.error(f"MQTT connection error: {e}")
                self._connection_attempts += 1
                return False
    
    def disconnect(self):
        """Ngắt kết nối MQTT"""
        with self._lock:
            if self._connected:
                try:
                    self.client.loop_stop()
                    self.client.disconnect()
                    self._connected = False
                    logger.info("MQTT disconnected")
                except Exception as e:
                    logger.error(f"Error disconnecting MQTT: {e}")
    
    def publish(self, topic: str, payload: str, qos: Optional[int] = None, retain: Optional[bool] = None) -> bool:
        """
        Publish message đến MQTT broker
        
        Args:
            topic: MQTT topic
            payload: Message payload (string)
            qos: Quality of Service (0, 1, 2)
            retain: Retain flag
            
        Returns:
            True nếu publish thành công
        """
        with self._lock:
            if not self._connected:
                if not self.connect():
                    logger.warning("Cannot publish, MQTT not connected")
                    return False
            
            try:
                qos_val = qos if qos is not None else settings.mqtt_qos
                retain_val = retain if retain is not None else settings.mqtt_retain
                
                result = self.client.publish(
                    topic,
                    payload,
                    qos=qos_val,
                    retain=retain_val
                )
                
                # Chờ publish hoàn thành (timeout 2 giây)
                result.wait_for_publish(timeout=2.0)
                
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    logger.debug(f"Published to {topic}: {payload}")
                    return True
                else:
                    logger.error(f"Publish failed with code {result.rc}")
                    return False
                    
            except Exception as e:
                logger.error(f"Error publishing to MQTT: {e}")
                self._connected = False
                return False
    
    def publish_detection_status(self, status: str, metadata: Optional[dict] = None) -> bool:
        """
        Publish detection status (ON/OFF) với metadata
        
        Args:
            status: "ON" hoặc "OFF"
            metadata: Thông tin bổ sung
            
        Returns:
            True nếu publish thành công
        """
        payload = {
            "status": status,
            "timestamp": time.time(),
            "source": "pythonSVIOT",
        }
        
        if metadata:
            payload.update(metadata)
        
        return self.publish(
            settings.mqtt_topic,
            json.dumps(payload),
            qos=1,
            retain=False
        )
    
    def publish_drawer_command(self, command: str, metadata: Optional[dict] = None, topic: Optional[str] = None) -> bool:
        """
        Publish drawer command (open/close) đến ESP32
        
        Args:
            command: "open" hoặc "close"
            metadata: Thông tin bổ sung
            
        Returns:
            True nếu publish thành công
        """
        if command not in ["open", "close"]:
            logger.error(f"Invalid drawer command: {command}")
            return False
        
        payload = {
            "status": "ON" if command == "open" else "OFF",
            "timestamp": time.time(),
            "source": "pythonSVIOT",
            "command": command,
        }
        
        if metadata:
            payload.update(metadata)
        
        return self.publish(
            topic or settings.mqtt_drawer_command_topic,
            json.dumps(payload),
            qos=1,
            retain=False
        )

    def publish_drawer_control(self, command: str, metadata: Optional[dict] = None) -> bool:
        """Publish drawer control cấp cao từ app tới ESP32."""
        if command not in ["open", "close"]:
            logger.error(f"Invalid drawer command: {command}")
            return False

        payload = {
            "command": command,
            "status": "ON" if command == "open" else "OFF",
            "timestamp": time.time(),
            "source": "pythonSVIOT",
            "mode": "app_control",
        }

        if metadata:
            payload.update(metadata)

        return self.publish(
            settings.mqtt_drawer_control_topic,
            json.dumps(payload),
            qos=1,
            retain=False
        )
    
    def is_connected(self) -> bool:
        """Kiểm tra xem client có đang kết nối không"""
        with self._lock:
            return self._connected


# Global MQTT client instance
_mqtt_client: Optional[MQTTClient] = None


def get_mqtt_client() -> MQTTClient:
    """Lấy global MQTT client instance (singleton)"""
    global _mqtt_client
    if _mqtt_client is None:
        _mqtt_client = MQTTClient()
    return _mqtt_client


def init_mqtt_client() -> bool:
    """Khởi tạo và kết nối MQTT client"""
    client = get_mqtt_client()
    return client.connect()


def shutdown_mqtt_client():
    """Shutdown MQTT client"""
    global _mqtt_client
    if _mqtt_client:
        _mqtt_client.disconnect()
        _mqtt_client = None