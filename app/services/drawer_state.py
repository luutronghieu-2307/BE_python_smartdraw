"""
Drawer State Manager để quản lý trạng thái tủ kéo và sync với ESP32
"""
import time
import threading
import logging
from typing import Optional
from enum import Enum

from app.core.config import settings

logger = logging.getLogger(__name__)


class DrawerState(str, Enum):
    """Trạng thái của tủ kéo"""
    UNKNOWN = "unknown"      # Chưa biết trạng thái
    CLOSED = "closed"        # Đóng
    OPENING = "opening"      # Đang mở
    OPEN = "open"            # Mở
    CLOSING = "closing"      # Đang đóng
    ERROR = "error"          # Lỗi


class DrawerSyncResult(str, Enum):
    """Kết quả sync với ESP32"""
    SUCCESS = "success"
    TIMEOUT = "timeout"
    MISMATCH = "mismatch"   # Trạng thái ESP32 khác dự kiến
    ERROR = "error"


class DrawerStateManager:
    """Quản lý trạng thái tủ kéo với sync và confirmation từ ESP32"""
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # State
        self.current_state = DrawerState.UNKNOWN
        self.expected_state = DrawerState.UNKNOWN     # Trạng thái dự kiến sau lệnh
        self.last_command_time = 0.0
        self.last_state_update_time = 0.0
        
        # Sync tracking
        self.is_syncing = False              # Điều khiển cấp cao: có đang chờ ESP32 confirm không
        self.pending_command = None          # Lệnh đang chờ được gửi
        self.command_start_time = 0.0        # Thời điểm bắt đầu gửi lệnh
        
        # AI Detection control (pause when user commands)
        self.pause_ai_detection = False      # Có pause AI detection không
        self.pause_until_time = 0.0          # Thời gian bao lâu thì resume AI
        self.ai_pause_duration = 60          # Thời gian pause mặc định (60 giây)
        
        # Stats
        self.total_commands = 0
        self.successful_commands = 0
        self.failed_commands = 0
        
    def send_command(self, target_state: str, is_user_command: bool = False, wait_for_confirmation: bool = True) -> tuple[bool, str]:
        """
        Gửi lệnh mở/đóng tủ kéo
        
        Args:
            target_state: "open" hoặc "close"
            is_user_command: True nếu từ user app (ưu tiên cao), False nếu từ auto detection
            
        Returns:
            tuple: (should_publish, expected_payload)
                - should_publish: có cần publish MQTT không
                - expected_payload: JSON payload để gửi
        """
        with self._lock:
            if not settings.drawer_enable_sync:
                return False, ""
            
            if self.is_syncing and wait_for_confirmation:
                logger.warning(f"Drawer is already syncing, ignoring new command")
                return False, ""
            
            if target_state not in ["open", "close"]:
                logger.error(f"Invalid target state: {target_state}")
                return False, ""
            
            self.total_commands += 1

            # Prepare command
            if wait_for_confirmation:
                self.is_syncing = True
                self.pending_command = target_state
                self.command_start_time = time.time()
                self.expected_state = DrawerState.OPENING if target_state == "open" else DrawerState.CLOSING
            else:
                # App command has highest priority: cancel any pending sync state and apply immediately.
                self.is_syncing = False
                self.pending_command = None
                self.command_start_time = 0.0
                self.expected_state = DrawerState.OPEN if target_state == "open" else DrawerState.CLOSED
                self.current_state = self.expected_state
                self.last_state_update_time = time.time()
            
            # Nếu là user command → pause AI detection
            if is_user_command:
                self.pause_ai_detection = True
                self.pause_until_time = time.time() + self.ai_pause_duration
                logger.info(f"AI detection paused for {self.ai_pause_duration}s (user command)")
            
            logger.info(f"Drawer command: {target_state} (user={is_user_command})")
            return True, self.pending_command
    
    def on_drawer_status_received(self, status: str) -> DrawerSyncResult:
        """
        Callback khi nhận được status từ ESP32
        
        Args:
            status: "open" hoặc "close" từ ESP32
            
        Returns:
            DrawerSyncResult: kết quả sync
        """
        with self._lock:
            if not self.is_syncing or not self.pending_command:
                # Status được nhận nhưng không có lệnh pending, log warning
                logger.warning(f"Received status '{status}' but no pending command")
                # Cập nhật trạng thái hiện tại dù sao
                self.current_state = DrawerState.OPEN if status == "open" else DrawerState.CLOSED
                self.last_state_update_time = time.time()
                return DrawerSyncResult.SUCCESS
            
            current_time = time.time()
            elapsed = current_time - self.command_start_time
            
            # Kiểm tra timeout
            if elapsed > settings.drawer_command_timeout_seconds:
                logger.error(f"Drawer command timeout (elapsed: {elapsed:.1f}s)")
                self.is_syncing = False
                self.failed_commands += 1
                return DrawerSyncResult.TIMEOUT
            
            # Kiểm tra khớp trạng thái
            expected_final = DrawerState.OPEN if self.pending_command == "open" else DrawerState.CLOSED
            actual_state = DrawerState.OPEN if status == "open" else DrawerState.CLOSED
            
            if actual_state != expected_final:
                logger.error(f"Drawer state mismatch: expected {expected_final}, got {actual_state}")
                self.current_state = actual_state
                self.last_state_update_time = current_time
                self.is_syncing = False
                self.failed_commands += 1
                return DrawerSyncResult.MISMATCH
            
            # Success!
            logger.info(f"Drawer sync success: {self.pending_command} -> {actual_state}")
            self.current_state = actual_state
            self.last_state_update_time = current_time
            self.is_syncing = False
            self.pending_command = None
            self.successful_commands += 1
            return DrawerSyncResult.SUCCESS
    
    def on_command_timeout(self):
        """Callback khi timeout chờ response từ ESP32"""
        with self._lock:
            if self.is_syncing:
                logger.error(f"Drawer command timeout, elapsed > {settings.drawer_command_timeout_seconds}s")
                self.is_syncing = False
                self.failed_commands += 1
    
    def _get_pause_until_time(self) -> float:
        """Tính thời gian khi sẽ auto-resume AI"""
        return time.time() + self.ai_pause_duration
    
    def is_ai_paused(self) -> bool:
        """Kiểm tra xem AI detection có đang bị pause không"""
        with self._lock:
            if not self.pause_ai_detection:
                return False
            
            current_time = time.time()
            if current_time >= self.pause_until_time:
                # Hết pause timeout → resume AI
                self.pause_ai_detection = False
                logger.info("AI detection resumed (pause timeout expired)")
                return False
            
            return True
    
    def resume_ai_detection(self):
        """Resume AI detection ngay lập tức"""
        with self._lock:
            self.pause_ai_detection = False
            self.pause_until_time = 0.0
            logger.info("AI detection resumed manually")
    
    def get_state(self) -> dict:
        """Lấy thông tin trạng thái hiện tại"""
        with self._lock:
            is_paused = self.is_ai_paused()
            return {
                "current_state": self.current_state,
                "expected_state": self.expected_state,
                "is_syncing": self.is_syncing,
                "pending_command": self.pending_command,
                "last_state_update_time": self.last_state_update_time,
                "total_commands": self.total_commands,
                "successful_commands": self.successful_commands,
                "failed_commands": self.failed_commands,
                "success_rate": (
                    self.successful_commands / self.total_commands
                    if self.total_commands > 0 else 0.0
                ),
                "ai_paused": is_paused,
                "pause_until_time": self.pause_until_time,
            }


# Global instance
_drawer_state_manager: Optional[DrawerStateManager] = None


def get_drawer_state_manager() -> DrawerStateManager:
    """Lấy global drawer state manager instance (singleton)"""
    global _drawer_state_manager
    if _drawer_state_manager is None:
        _drawer_state_manager = DrawerStateManager()
    return _drawer_state_manager
