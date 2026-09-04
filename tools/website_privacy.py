from __future__ import annotations

import re
import unicodedata
from typing import Final
from urllib.parse import unquote

_EXPLICIT_IDENTIFIER_MARKERS: Final = (
    "first 7 digits",
    "first seven digits",
    "првите 7 бројки",
    "првите седум бројки",
)
_CANDIDATE_MARKERS: Final = ("candidate", "кандидат")
_CODE_MARKERS: Final = ("code", "код")
_MAX_DECODE_PASSES: Final = 20
_FIN_SEVEN_DIGIT_CODE: Final = re.compile(
    r"(?<!\w)f[\W_]*i[\W_]*n[\W_]*\d(?:[\W_]*\d){6}(?!\d)"
)
_CONTIGUOUS_SEVEN_DIGIT_CODE: Final = re.compile(r"(?<!\d)\d{7}(?!\d)")
_DIGIT_CLUSTER: Final = re.compile(r"\d(?:[^\w|]*\d)*")


def _compatibility_text(value: str) -> str | None:
    for _ in range(_MAX_DECODE_PASSES):
        decoded = unquote(unicodedata.normalize("NFKC", value))
        if decoded == value:
            return decoded.casefold()
        value = decoded
    return None


def _contains_fin_identifier(value: str) -> bool:
    return any(_FIN_SEVEN_DIGIT_CODE.search(line) for line in value.splitlines())


def _contains_seven_digit_sequence(value: str) -> bool:
    return any(
        sum(character.isdecimal() for character in match.group()) == 7
        for line in value.splitlines()
        for match in _DIGIT_CLUSTER.finditer(line)
    )


def _contains_candidate_identifier(*, title: str, value: str) -> bool:
    normalized_title = re.sub(r"[\W_]+", " ", title)
    if any(
        marker in normalized_title for marker in _CANDIDATE_MARKERS
    ) and _CONTIGUOUS_SEVEN_DIGIT_CODE.search(value):
        return True
    lines = value.splitlines()
    for index, line in enumerate(lines):
        if not _contains_seven_digit_sequence(line):
            continue
        context = " ".join(lines[max(0, index - 2) : index + 3])
        normalized_context = re.sub(r"[\W_]+", " ", context)
        has_candidate_marker = any(
            marker in normalized_context for marker in _CANDIDATE_MARKERS
        )
        if has_candidate_marker and _CONTIGUOUS_SEVEN_DIGIT_CODE.search(line):
            return True
        if has_candidate_marker and any(
            marker in normalized_context for marker in _CODE_MARKERS
        ):
            return True
    return False


def contains_sensitive_personal_identifier(*, title: str, markdown: str) -> bool:
    compatibility_title = _compatibility_text(title)
    compatibility_text = _compatibility_text(f"{title}\n{markdown}")
    if compatibility_title is None or compatibility_text is None:
        return True
    normalized_text = re.sub(r"[\W_]+", " ", compatibility_text)
    if _contains_fin_identifier(compatibility_text) or any(
        marker in normalized_text for marker in _EXPLICIT_IDENTIFIER_MARKERS
    ):
        return True
    return _contains_candidate_identifier(
        title=compatibility_title,
        value=compatibility_text,
    )
