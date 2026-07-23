"""Infrastructure adapters for persistence, configuration, logging, and remote IO."""

from .logging import configure_logging, logger
from .legacy_signal import LegacySignalAdapter
from .notification import SmtpConfig, SmtpNotifier
from ALB.core.observers import ObserverDispatcher
from .persistence import DirectoryArtifactWriter
from .recording import (
    FieldFilteringRecorder,
    InMemoryResultRecorder,
    RingBufferResultRecorder,
    SamplingRecorder,
)

__all__ = [
    "DirectoryArtifactWriter",
    "FieldFilteringRecorder",
    "InMemoryResultRecorder",
    "LegacySignalAdapter",
    "ObserverDispatcher",
    "RingBufferResultRecorder",
    "SamplingRecorder",
    "SmtpConfig",
    "SmtpNotifier",
    "configure_logging",
    "logger",
]
