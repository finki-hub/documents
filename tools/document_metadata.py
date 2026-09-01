import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

REQUIRED_FIELDS: Final = (
    "title",
    "source",
    "document_date",
    "date_kind",
    "date_precision",
    "date_source",
    "date_confidence",
    "current_status",
    "last_verified",
    "authority_url",
)

INGEST_FIELDS: Final = (
    "authority_url",
    "document_date",
    "date_kind",
    "date_precision",
    "date_source",
    "date_confidence",
    "current_status",
    "last_verified",
    "issued",
    "published",
    "effective_from",
    "amended_through",
    "valid_until",
    "coverage_period",
    "source_pages",
)

OFFICIAL_AUTHORITY_HOSTS: Final = frozenset(
    {
        "azlp.mk",
        "finki.ukim.mk",
        "portal.mdt.gov.mk",
        "slvesnik.com.mk",
        "ukim.edu.mk",
    }
)

ALLOWED_VALUES: Final = {
    "date_kind": frozenset(
        {"adopted", "published", "issued", "coverage_period", "unresolved"}
    ),
    "date_precision": frozenset(
        {"day", "month", "year", "academic_year", "gazette_issue", "none"}
    ),
    "date_source": frozenset(
        {"document_text", "official_gazette", "official_webpage", "unresolved"}
    ),
    "date_confidence": frozenset({"high", "medium", "low", "none"}),
    "current_status": frozenset(
        {
            "current",
            "presumed_current",
            "currentness_unresolved",
            "historical",
            "superseded",
            "likely_superseded",
            "stale_review_required",
            "informational",
            "authority_unresolved",
            "foundational",
        }
    ),
}


class MetadataError(ValueError):
    pass


def header_fields(content: str, document_name: str = "document") -> dict[str, str]:
    match = re.match(r"\A\ufeff?\s*<!--(?P<header>.*?)-->", content, re.DOTALL)
    if match is None:
        raise MetadataError(f"{document_name}: missing leading metadata header")

    fields: dict[str, str] = {}
    for segment in match.group("header").split("|"):
        name, separator, value = segment.strip().partition(":")
        if not separator:
            continue
        key = name.strip().casefold()
        if key in fields:
            raise MetadataError(f"{document_name}: duplicate {key}")
        fields[key] = value.strip()
    return fields


def header_value(content: str, name: str) -> str | None:
    return header_fields(content).get(name.casefold())


def source_filenames(content: str) -> tuple[str, ...]:
    fields = header_fields(content)
    values: list[str] = []
    source = fields.get("source")
    if source:
        values.append(source)
    amendments = fields.get("amendments")
    if amendments:
        values.extend(item.strip() for item in amendments.split(","))
    return tuple(dict.fromkeys(value for value in values if value))


def ingest_metadata(content: str) -> dict[str, str]:
    fields = header_fields(content)
    values = {
        field: value
        for field in INGEST_FIELDS
        if (value := fields.get(field)) is not None
    }
    if "document_date" not in values and (issued := values.get("issued")):
        values["document_date"] = issued
    return values


def _is_valid_date(value: str, precision: str) -> bool:
    try:
        if precision == "day":
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
                return False
            date.fromisoformat(value)
        elif precision == "month":
            if re.fullmatch(r"\d{4}-\d{2}", value) is None:
                return False
            year, month = map(int, value.split("-"))
            date(year, month, 1)
        elif precision == "year":
            if re.fullmatch(r"\d{4}", value) is None:
                return False
            date(int(value), 1, 1)
        elif precision == "academic_year":
            if re.fullmatch(r"\d{4}/(?:\d{2}|\d{4})", value) is None:
                return False
            start_text, end_text = value.split("/")
            start = int(start_text)
            end = int(end_text)
            expected = start + 1 if len(end_text) == 4 else (start + 1) % 100
            return start > 0 and end == expected
        elif precision == "gazette_issue":
            if re.fullmatch(r"\d+/\d{4}", value) is None:
                return False
            issue, year = map(int, value.split("/"))
            return issue > 0 and year > 0
        elif precision == "none":
            return value == "unresolved"
        else:
            return False
    except ValueError:
        return False
    return True


def _validate_date(
    path: Path, field: str, value: str, precisions: tuple[str, ...]
) -> None:
    if not any(_is_valid_date(value, precision) for precision in precisions):
        raise MetadataError(f"{path.name}: invalid {field} {value!r}")


def _validate_authority_url(path: Path, value: str) -> None:
    if (
        "\\" in value
        or not value.isprintable()
        or any(character.isspace() for character in value)
    ):
        raise MetadataError(f"{path.name}: invalid authority_url {value!r}")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise MetadataError(f"{path.name}: invalid authority_url {value!r}") from error
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or not parsed.netloc.isascii()
        or parsed.query
        or parsed.fragment
    ):
        raise MetadataError(f"{path.name}: invalid authority_url {value!r}")
    hostname = parsed.hostname.lower()
    if parsed.netloc.lower() != hostname:
        raise MetadataError(f"{path.name}: invalid authority_url {value!r}")
    if hostname not in OFFICIAL_AUTHORITY_HOSTS:
        raise MetadataError(f"{path.name}: unofficial authority_url {value!r}")


def validate_document(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    fields = header_fields(content, path.name)
    values: dict[str, str] = {}
    for field in REQUIRED_FIELDS:
        value = fields.get(field)
        if value is None:
            raise MetadataError(f"{path.name}: missing {field}")
        if not value:
            raise MetadataError(f"{path.name}: empty {field}")
        values[field] = value

    _validate_authority_url(path, values["authority_url"])

    for field, allowed in ALLOWED_VALUES.items():
        if values[field] not in allowed:
            choices = ", ".join(sorted(allowed))
            raise MetadataError(
                f"{path.name}: invalid {field} {values[field]!r}; use {choices}"
            )

    unresolved = values["document_date"] == "unresolved"
    if unresolved:
        expected = {
            "date_kind": "unresolved",
            "date_precision": "none",
            "date_source": "unresolved",
            "date_confidence": "none",
        }
        if any(
            values[field] != expected_value
            for field, expected_value in expected.items()
        ):
            raise MetadataError(
                f"{path.name}: unresolved metadata requires unresolved kind/source, none precision/confidence"
            )
    elif any(
        values[field] == unresolved_value
        for field, unresolved_value in {
            "date_kind": "unresolved",
            "date_precision": "none",
            "date_source": "unresolved",
            "date_confidence": "none",
        }.items()
    ):
        raise MetadataError(
            f"{path.name}: resolved metadata cannot use unresolved or none values"
        )

    _validate_date(
        path,
        "document_date",
        values["document_date"],
        (values["date_precision"],),
    )
    _validate_date(path, "last_verified", values["last_verified"], ("day",))
    optional_dates = {
        "issued": ("day", "month", "year"),
        "published": ("day", "month", "year"),
        "effective_from": ("day", "month", "year"),
        "amended_through": ("day", "month", "year", "gazette_issue"),
        "valid_until": ("day", "month", "year"),
        "coverage_period": ("academic_year",),
    }
    for field, precisions in optional_dates.items():
        if field in fields:
            _validate_date(path, field, fields[field], precisions)
    return values["current_status"]


def audit_corpus(directory: Path, raw_directory: Path | None = None) -> dict[str, int]:
    paths = sorted(directory.glob("*.md"))
    if not paths:
        raise MetadataError(f"{directory}: no Markdown documents found")
    if raw_directory is not None:
        for path in paths:
            content = path.read_text(encoding="utf-8")
            for source in source_filenames(content):
                if not (raw_directory / source).is_file():
                    raise MetadataError(f"{path.name}: missing raw source {source!r}")
    return dict(sorted(Counter(validate_document(path) for path in paths).items()))
