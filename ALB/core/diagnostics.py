"""Sanitized runtime diagnostics that never retain raw exception text."""

from __future__ import annotations

import hashlib
import unicodedata


_GENERIC_MESSAGES: dict[type[BaseException], str] = {
    TypeError: "component received an invalid type",
    ValueError: "component received an invalid value",
    ArithmeticError: "component arithmetic failed",
    OSError: "component operating-system operation failed",
    RuntimeError: "component runtime operation failed",
}


def sanitize_exception_message(
    error: BaseException,
    *,
    max_length: int = 160,
) -> str:
    """Return a bounded diagnostic without paths, secrets, or file content.

    Raw third-party exception text is normalized only to compute a short
    correlation fingerprint. It is never retained in runtime snapshots.
    Complete tracebacks belong at the separately controlled logging boundary.
    """

    if not isinstance(error, BaseException):
        raise TypeError("error must be an exception")
    if (
        isinstance(max_length, bool)
        or not isinstance(max_length, int)
        or max_length < 64
    ):
        raise ValueError("max_length must be an integer of at least 64")

    raw = str(error)
    normalized = "".join(
        " " if unicodedata.category(character).startswith("C") else character
        for character in raw
    )
    normalized = " ".join(normalized.split())
    fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    generic = "component operation failed"
    for error_type, message in _GENERIC_MESSAGES.items():
        if isinstance(error, error_type):
            generic = message
            break
    summary = f"{generic}; detail_fingerprint={fingerprint}"
    return summary[:max_length]


__all__ = ["sanitize_exception_message"]
