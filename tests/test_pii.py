# Author: Yogesh Agrawal
"""Tests for PII redaction (Presidio)."""
from app.pii.redactor import redact


def test_credit_card_masked():
    r = redact("My card is 4111 1111 1111 1111 please")
    assert "4111 1111 1111 1111" not in r.text
    assert "CREDIT_CARD" in r.entities
    assert any("4111 1111 1111 1111" == v for v in r.mapping.values())


def test_email_and_phone_masked():
    r = redact("email me at john.doe@example.com or call +1-202-555-0173")
    assert "john.doe@example.com" not in r.text
    assert "EMAIL_ADDRESS" in r.entities


def test_reversible_unmask():
    r = redact("My card is 4111 1111 1111 1111")
    placeholder = next(iter(r.mapping))
    answer = f"Noted card {placeholder}."
    restored = r.unmask(answer)
    assert "4111 1111 1111 1111" in restored


def test_no_pii_passthrough():
    r = redact("What is my balance?")
    assert r.text == "What is my balance?"
    assert r.mapping == {}


def test_empty_text():
    r = redact("")
    assert r.text == ""
