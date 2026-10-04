# Author: Yogesh Agrawal
"""PII redaction using Microsoft Presidio.

Masks personally identifiable information (credit cards, phone, email, names,
and bank-account numbers) BEFORE any text is sent to an LLM — even the local,
self-hosted one — per the security design.

Masking is REVERSIBLE within a single request: each detected entity is replaced
with a stable placeholder token (e.g. <CREDIT_CARD_1>) and the mapping is
returned so the final LLM answer can be de-masked for the authenticated
customer before display.

The engines are heavy to construct, so they are lazily built once and cached.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.config import get_settings

# Entities we detect/mask.
PII_ENTITIES = [
    "CREDIT_CARD",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "PERSON",
    "IBAN_CODE",
    "US_BANK_NUMBER",
]

# Custom bank-account pattern (e.g. "A1234567" or 9-18 digit account numbers).
_ACCOUNT_RE = re.compile(r"\b(?:AC|ACC|A)?\d{9,18}\b")


@dataclass
class RedactionResult:
    text: str                        # masked text (safe to send to LLM)
    mapping: dict[str, str] = field(default_factory=dict)  # placeholder -> original
    entities: list[str] = field(default_factory=list)       # entity types found

    def unmask(self, text: str) -> str:
        """Restore original values in an LLM response for the real customer."""
        for placeholder, original in self.mapping.items():
            text = text.replace(placeholder, original)
        return text


@lru_cache
def _engines():
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_anonymizer import AnonymizerEngine

    settings = get_settings()
    # Use the configured spaCy model (default en_core_web_sm) so we don't pull
    # the ~560MB large model into the image.
    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": settings.pii_spacy_model}],
        }
    )
    nlp_engine = provider.create_engine()
    analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])
    anonymizer = AnonymizerEngine()
    return analyzer, anonymizer


def redact(text: str) -> RedactionResult:
    """Analyze and mask PII in `text`, returning a reversible result."""
    settings = get_settings()
    if not settings.pii_enabled or not text.strip():
        return RedactionResult(text=text)

    analyzer, _ = _engines()
    results = analyzer.analyze(text=text, entities=PII_ENTITIES, language="en")

    # Add custom account-number matches not caught by Presidio.
    spans = [(r.start, r.end, r.entity_type) for r in results]
    for m in _ACCOUNT_RE.finditer(text):
        if not any(s <= m.start() < e for s, e, _ in spans):
            spans.append((m.start(), m.end(), "BANK_ACCOUNT"))

    if not spans:
        return RedactionResult(text=text)

    # Replace from the end so indices stay valid; build reversible mapping.
    spans.sort(key=lambda x: x[0])
    counters: dict[str, int] = {}
    mapping: dict[str, str] = {}
    entities_found: list[str] = []

    # Build masked text left-to-right with stable placeholders.
    out = []
    last = 0
    for start, end, etype in spans:
        if start < last:
            continue  # skip overlaps
        counters[etype] = counters.get(etype, 0) + 1
        placeholder = f"<{etype}_{counters[etype]}>"
        original = text[start:end]
        mapping[placeholder] = original
        entities_found.append(etype)
        out.append(text[last:start])
        out.append(placeholder)
        last = end
    out.append(text[last:])

    return RedactionResult(
        text="".join(out), mapping=mapping, entities=sorted(set(entities_found))
    )
