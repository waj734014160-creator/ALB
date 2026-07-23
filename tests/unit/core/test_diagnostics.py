"""Tests for runtime diagnostics that never persist raw exception text."""

from ALB.core.diagnostics import sanitize_exception_message


def test_exception_sanitizer_omits_secret_path_content_and_controls() -> None:
    error = RuntimeError(
        "password=hunter2\nC:\\private\\config.json token=sk-secret-value"
    )

    message = sanitize_exception_message(error)

    assert len(message) <= 160
    assert "hunter2" not in message
    assert "private" not in message
    assert "sk-secret-value" not in message
    assert "\n" not in message
    assert "detail_fingerprint=" in message
