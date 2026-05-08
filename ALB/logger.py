# coding: utf-8
import logging
import os
import threading
import time


class DuplicateLogFilter(logging.Filter):
    """Suppress repeated log records in a short window to avoid log flooding."""

    def __init__(self, burst=3, window_sec=5.0):
        super().__init__()
        self.burst = max(1, int(burst))
        self.window_sec = max(0.1, float(window_sec))
        self._state = {}
        self._lock = threading.Lock()

    def filter(self, record):
        """Execute filter."""
        now = time.monotonic()
        key = (record.name, record.levelno, record.getMessage())
        with self._lock:
            item = self._state.get(key)
            if item is None or (now - item["start"]) > self.window_sec:
                self._state[key] = {"start": now, "count": 1}
                return True

            item["count"] += 1
            if item["count"] <= self.burst:
                return True

            return False


def _level_from_name(level_name):
    if isinstance(level_name, int):
        return level_name
    return getattr(logging, str(level_name).upper(), logging.WARNING)


def configure_logging(level=None):
    """Execute configure_logging."""
    logger_obj = logging.getLogger("ALB")
    if not logger_obj.handlers:
        formatter = logging.Formatter(
            "%(levelname)s %(asctime)s [%(name)s] %(message)s"
        )
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        dedup_burst = os.getenv("ALB_LOG_BURST", "3")
        dedup_window_sec = os.getenv("ALB_LOG_WINDOW_SEC", "5")
        console.addFilter(
            DuplicateLogFilter(burst=dedup_burst, window_sec=dedup_window_sec)
        )
        logger_obj.addHandler(console)
        logger_obj.propagate = False

    default_level = os.getenv("ALB_LOG_LEVEL", "WARNING")
    logger_obj.setLevel(_level_from_name(level or default_level))
    return logger_obj


logger = configure_logging()

