from __future__ import annotations

import html
import re
from urllib.parse import urlsplit


def _is_escaped(value: str, index: int) -> bool:
    backslashes = 0
    while index > backslashes and value[index - backslashes - 1] == "\\":
        backslashes += 1
    return backslashes % 2 == 1


def _closing_delimiter(
    value: str,
    start: int,
    opening: str,
    closing: str,
) -> int | None:
    depth = 1
    for index in range(start + 1, len(value)):
        if _is_escaped(value, index):
            continue
        if value[index] == opening:
            depth += 1
        elif value[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


def sanitize_markdown_links(value: str) -> str:
    output: list[str] = []
    cursor = 0
    scan = 0
    while (label_start := value.find("[", scan)) >= 0:
        if _is_escaped(value, label_start):
            scan = label_start + 1
            continue
        label_end = _closing_delimiter(value, label_start, "[", "]")
        if label_end is None or value[label_end + 1 : label_end + 2] != "(":
            scan = label_start + 1
            continue
        destination_end = _closing_delimiter(value, label_end + 1, "(", ")")
        if destination_end is None:
            scan = label_end + 1
            continue
        destination = html.unescape(value[label_end + 2 : destination_end]).strip()
        target = destination.split(maxsplit=1)[0].strip("<>") if destination else ""
        scheme = urlsplit(target).scheme.casefold()
        image = (
            label_start > 0
            and value[label_start - 1] == "!"
            and not _is_escaped(value, label_start - 1)
        )
        allowed = {"http", "https"} if image else {"http", "https", "mailto"}
        if scheme and scheme not in allowed:
            markup_start = label_start - 1 if image else label_start
            output.extend(
                (value[cursor:markup_start], value[label_start + 1 : label_end])
            )
            cursor = destination_end + 1
        scan = destination_end + 1
    output.append(value[cursor:])
    return "".join(output)


def _neutralize_reference_definitions(value: str) -> str:
    openings: set[int] = set()
    line_start = 0
    while line_start < len(value):
        opening = line_start
        while opening < len(value) and opening - line_start < 3:
            if value[opening] != " ":
                break
            opening += 1
        if opening < len(value) and value[opening] == "[":
            closing = _closing_delimiter(value, opening, "[", "]")
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
