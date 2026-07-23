"""Infrastructure adapters for persistence, configuration, logging, and remote IO."""

from .logging import configure_logging, logger
from .notification import SmtpConfig, SmtpNotifier
from .observers import ObserverDispatcher
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
    "ObserverDispatcher",
    "RingBufferResultRecorder",
    "SamplingRecorder",
    "SmtpConfig",
    "SmtpNotifier",
    "configure_logging",
    "logger",
]
