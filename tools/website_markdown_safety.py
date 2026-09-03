from __future__ import annotations

import html
import re
import string
from typing import Final
from urllib.parse import urlsplit

_COMMONMARK_ESCAPABLE: Final = frozenset(string.punctuation)


def _is_escaped(value: str, index: int) -> bool:
    backslashes = 0
    while index > backslashes and value[index - backslashes - 1] == "\\":
        backslashes += 1
    return backslashes % 2 == 1


def _delimiter_pairs(
    value: str,
    opening: str,
    closing: str,
) -> dict[int, int]:
    stack: list[int] = []
    pairs: dict[int, int] = {}
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
        elif character == opening:
            stack.append(index)
        elif character == closing and stack:
            pairs[stack.pop()] = index
    return pairs


def _unescape_commonmark(value: str) -> str:
    output: list[str] = []
    cursor = 0
    while cursor < len(value):
        character = value[cursor]
        if (
            character == "\\"
            and cursor + 1 < len(value)
            and value[cursor + 1] in _COMMONMARK_ESCAPABLE
        ):
            cursor += 1
            character = value[cursor]
        output.append(character)
        cursor += 1
    return "".join(output)


def sanitize_markdown_links(value: str) -> str:
    replacements: list[tuple[int, int]] = []
    inspected_characters = 0
    brackets = _delimiter_pairs(value, "[", "]")
    parentheses = _delimiter_pairs(value, "(", ")")
    for label_start, label_end in brackets.items():
        destination_start = label_end + 1
        if value[destination_start : destination_start + 1] != "(":
            continue
        destination_end = parentheses.get(destination_start)
        if destination_end is None:
            continue
        destination_length = destination_end - destination_start - 1
        if inspected_characters + destination_length > len(value):
            replacements.append((destination_start + 1, destination_end))
            continue
        inspected_characters += destination_length
        destination = html.unescape(value[label_end + 2 : destination_end]).strip()
        destination = _unescape_commonmark(destination)
        destination = re.sub(r"[\x00-\x1f\x7f]+", "", destination)
        target = destination.split(maxsplit=1)[0].strip("<>") if destination else ""
        try:
            scheme = urlsplit(target).scheme.casefold()
        except ValueError:
            replacements.append((destination_start + 1, destination_end))
            continue
        image = (
            label_start > 0
            and value[label_start - 1] == "!"
            and not _is_escaped(value, label_start - 1)
        )
        allowed = {"http", "https"} if image else {"http", "https", "mailto"}
        if scheme and scheme not in allowed:
            replacements.append((destination_start + 1, destination_end))
    output: list[str] = []
    cursor = 0
    for start, end in sorted(replacements):
        if start < cursor:
            continue
        output.extend((value[cursor:start], "#"))
        cursor = end
    output.append(value[cursor:])
    return "".join(output)


def _neutralize_reference_definitions(value: str) -> str:
    openings: set[int] = set()
    brackets = _delimiter_pairs(value, "[", "]")
    line_start = 0
    while line_start < len(value):
        opening = line_start
        while opening < len(value) and opening - line_start < 3:
            if value[opening] != " ":
                break
            opening += 1
        if opening < len(value) and value[opening] == "[":
            closing = brackets.get(opening)
            if closing is not None and value[closing + 1 : closing + 2] == ":":
                openings.add(opening)
        newline = value.find("\n", line_start)
        if newline < 0:
            break
        line_start = newline + 1
    return "".join(
        f"{'\\' if index in openings else ''}{character}"
        for index, character in enumerate(value)
    )


def neutralize_markdown_blocks(value: str) -> str:
    value = _neutralize_reference_definitions(value)
    return re.sub(
        r"(?m)^(?P<indent>[ ]{0,3})(?P<fence>`{3,}|~{3,})",
        lambda match: f"{match.group('indent')}\\{match.group('fence')}",
        value,
    )
