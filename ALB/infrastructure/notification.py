"""SMTP notification adapter with explicit, injectable configuration."""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class SmtpConfig:
    """Connection and addressing data required by :class:`SmtpNotifier`."""

    host: str
    port: int
    sender: str
    recipients: tuple[str, ...]
    username: str | None = None
    password: str | None = None
    use_starttls: bool = True
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.host.strip():
            raise ValueError("SMTP host must be nonempty")
        if not 1 <= self.port <= 65535:
            raise ValueError("SMTP port must be between 1 and 65535")
        if not self.sender.strip():
            raise ValueError("SMTP sender must be nonempty")
        recipients = tuple(item.strip() for item in self.recipients if item.strip())
        if not recipients:
            raise ValueError("at least one SMTP recipient is required")
        if (self.username is None) != (self.password is None):
            raise ValueError("SMTP username and password must be supplied together")
        if self.timeout_seconds <= 0:
            raise ValueError("SMTP timeout_seconds must be positive")
        object.__setattr__(self, "recipients", recipients)

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        prefix: str = "ALB_SMTP_",
    ) -> "SmtpConfig":
        """Load configuration from an injected mapping or the process environment."""

        source = os.environ if env is None else env

        def required(name: str) -> str:
            value = source.get(prefix + name, "").strip()
            if not value:
                raise ValueError(f"missing required environment variable {prefix + name}")
            return value

        host = required("HOST")
        sender = required("SENDER")
        recipients = tuple(
            item.strip() for item in required("RECIPIENTS").split(",") if item.strip()
        )
        starttls_value = source.get(prefix + "STARTTLS", "true").strip().lower()
        if starttls_value not in {"true", "false"}:
            raise ValueError(f"{prefix}STARTTLS must be true or false")
        username = source.get(prefix + "USERNAME") or None
        password = source.get(prefix + "PASSWORD") or None
        return cls(
            host=host,
            port=int(source.get(prefix + "PORT", "587")),
            sender=sender,
            recipients=recipients,
            username=username,
            password=password,
            use_starttls=starttls_value == "true",
            timeout_seconds=float(source.get(prefix + "TIMEOUT_SECONDS", "30")),
        )


class SmtpNotifier:
    """Deliver diagnostic notifications through an injected SMTP configuration."""

    def __init__(self, config: SmtpConfig) -> None:
        self._config = config

    def notify(self, message: str, subject: str | None = None) -> None:
        """Send one plain-text notification without retaining mutable state."""

        email = EmailMessage()
        email["Subject"] = subject or "ALB notification"
        email["From"] = self._config.sender
        email["To"] = ", ".join(self._config.recipients)
        email.set_content(message)

        with smtplib.SMTP(
            self._config.host,
            self._config.port,
            timeout=self._config.timeout_seconds,
        ) as client:
            if self._config.use_starttls:
                client.starttls()
            if self._config.username is not None:
                client.login(self._config.username, self._config.password or "")
            client.send_message(email)


def recipients_from_sequence(values: Sequence[str]) -> tuple[str, ...]:
    """Normalize a caller-provided recipient sequence for explicit construction."""

    return tuple(str(value).strip() for value in values if str(value).strip())
