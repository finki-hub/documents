from __future__ import annotations

import re
import unicodedata
from typing import Final

_EXPLICIT_IDENTIFIER_MARKERS: Final = (
    "first 7 digits",
    "first seven digits",
    "првите 7 бројки",
    "првите седум бројки",
)
_CANDIDATE_MARKERS: Final = ("candidate", "кандидат")
_FIN_SEVEN_DIGIT_CODE: Final = re.compile(
    r"\bf(?:[\W_]{0,3})i(?:[\W_]{0,3})n(?:[\W_]{0,3})\d(?:[\W_]{0,3}\d){6}\b"
)
_SEVEN_DIGIT_CODE: Final = re.compile(r"\b\d{7}\b")


def _normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", " ", normalized)


def contains_sensitive_personal_identifier(*, title: str, markdown: str) -> bool:
    value = f"{title}\n{markdown}"
    compatibility_text = unicodedata.normalize("NFKC", value).casefold()
    text = _normalized_text(value)
    if _FIN_SEVEN_DIGIT_CODE.search(compatibility_text) or any(
        marker in text for marker in _EXPLICIT_IDENTIFIER_MARKERS
    ):
        return True
    return bool(
        _SEVEN_DIGIT_CODE.search(text)
        and any(marker in text for marker in _CANDIDATE_MARKERS)
    )
