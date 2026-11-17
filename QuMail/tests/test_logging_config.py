"""Privacy logging regression coverage."""

from core.logging_config import PrivacyFilter


def test_sensitive_values_are_scrubbed_from_log_text():
    text = (
        "Authorization: Bearer synthetic-token-redaction-fixture "
        "refresh=1//refresh-token-fixture client_secret=synthetic-secret"
    )
    scrubbed = PrivacyFilter.scrub(text)
    assert "synthetic-token-redaction-fixture" not in scrubbed
    assert "1//refresh-token-fixture" not in scrubbed
    assert "synthetic-secret" not in scrubbed
    assert "[REDACTED" in scrubbed
