"""
Drawer item state manager để lưu trạng thái has_item từ ESP32.
"""
from __future__ import annotations

import threading
import time
from typing import Optional


class DrawerItemStateManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.has_item: bool = False
        self.updated_at: float = 0.0

    def update_has_item(self, has_item: bool) -> None:
        with self._lock:
            self.has_item = bool(has_item)
            self.updated_at = time.time()

    def get_state(self) -> dict:
        with self._lock:
            return {
                "has_item": self.has_item,
                "updated_at": self.updated_at,
            }


_drawer_item_state_manager: Optional[DrawerItemStateManager] = None


def get_drawer_item_state_manager() -> DrawerItemStateManager:
    global _drawer_item_state_manager
    if _drawer_item_state_manager is None:
        _drawer_item_state_manager = DrawerItemStateManager()
    return _drawer_item_state_manager