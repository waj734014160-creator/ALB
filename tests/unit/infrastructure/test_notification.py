"""Tests for explicit SMTP configuration without network access."""

import pytest

from ALB.infrastructure.notification import SmtpConfig


def test_smtp_config_requires_environment_addresses() -> None:
    with pytest.raises(ValueError, match="ALB_SMTP_HOST"):
        SmtpConfig.from_env({})


def test_smtp_config_reads_injected_environment() -> None:
    config = SmtpConfig.from_env(
        {
            "ALB_SMTP_HOST": "smtp.example.org",
            "ALB_SMTP_PORT": "2525",
            "ALB_SMTP_SENDER": "sender@example.org",
            "ALB_SMTP_RECIPIENTS": "one@example.org,two@example.org",
            "ALB_SMTP_USERNAME": "service-account",
            "ALB_SMTP_PASSWORD": "injected-secret",
            "ALB_SMTP_STARTTLS": "false",
        }
    )

    assert config.host == "smtp.example.org"
    assert config.port == 2525
    assert config.recipients == ("one@example.org", "two@example.org")
    assert config.use_starttls is False


def test_smtp_config_rejects_partial_credentials() -> None:
    with pytest.raises(ValueError, match="supplied together"):
        SmtpConfig(
            host="smtp.example.org",
            port=587,
            sender="sender@example.org",
            recipients=("operator@example.org",),
            username="service-account",
        )
