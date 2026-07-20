# -- coding: utf-8 --

import logging
import os
import time
import unittest
from io import StringIO

from ALB.infrastructure.logging import configure_logging


class TestLoggingDedup(unittest.TestCase):
    def test_duplicate_logs_are_suppressed(self):
        os.environ["ALB_LOG_LEVEL"] = "INFO"
        os.environ["ALB_LOG_BURST"] = "3"
        os.environ["ALB_LOG_WINDOW_SEC"] = "5"

        logger = configure_logging("INFO")
        self.assertGreaterEqual(len(logger.handlers), 1)

        handler = logger.handlers[0]
        self.assertIsInstance(handler, logging.StreamHandler)

        for f in handler.filters:
            if hasattr(f, "_state"):
                f._state.clear()

        original_stream = handler.stream
        buffer = StringIO()
        handler.setStream(buffer)

        try:
            message = f"dedup-case-{time.time_ns()}"
            for _ in range(10):
                logger.info(message)
        finally:
            handler.flush()
            handler.setStream(original_stream)

        text = buffer.getvalue()
        observed = text.count(message)
        self.assertLessEqual(observed, 3, msg=f"Expected <=3 duplicate logs, got {observed}")
        self.assertGreaterEqual(observed, 1, msg="No logs captured during dedup test")


if __name__ == "__main__":
    unittest.main()
