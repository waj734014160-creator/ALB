"""Infrastructure-neutral notification contract."""

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class NotifierProtocol(Protocol):
    """Optional diagnostic notification port."""

    def notify(self, message: str, subject: Optional[str] = None) -> None:
        """Deliver a diagnostic message."""
