from __future__ import annotations

import re


POSITIVE_TERMS = {
    "accelerate",
    "beat",
    "beats",
    "bullish",
    "upgrade",
    "upgraded",
    "growth",
    "profitable",
    "record",
    "raises",
    "raised",
    "strong",
    "surge",
    "outperform",
    "approval",
    "expansion",
}

NEGATIVE_TERMS = {
    "bearish",
    "cut",
    "downgrade",
    "downgraded",
    "fall",
    "falls",
    "miss",
    "misses",
    "probe",
    "lawsuit",
    "weak",
    "slump",
    "decline",
    "warning",
    "loss",
    "fraud",
}


def score_texts(texts: list[str]) -> tuple[float, float]:
    tokens = []
    for text in texts:
        tokens.extend(re.findall(r"[a-zA-Z]+", text.lower()))
    if not tokens:
        return 0.0, 0.0

    positive = sum(1 for token in tokens if token in POSITIVE_TERMS)
    negative = sum(1 for token in tokens if token in NEGATIVE_TERMS)
    mentions = positive + negative
    if mentions == 0:
        return 0.0, 0.15

    raw = (positive - negative) / mentions
    confidence = min(1.0, mentions / 8.0)
    return raw, confidence
