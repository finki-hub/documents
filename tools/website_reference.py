from __future__ import annotations

import argparse
import html as html_module
import os
import re
import tempfile
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.message import Message
from hashlib import sha256
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

import anyio
import httpx2
from selectolax.parser import HTMLParser

from .website_http import PAGE_FETCH_POLICY, fetch_public
from .website_markdown import WebsiteContentError, document_from_page
from .website_models import WebsiteDocument, _normalized_path, normalize_url
from .website_privacy import contains_sensitive_personal_identifier

ALLOWED_LANGUAGES = frozenset({"en", "mk"})
CURATED_SOURCE_LANGUAGE = "mk"
ALLOWED_CONTENT_KINDS = frozenset({"prose", "structured", "link-catalog"})
LEGACY_HOST = "oldsite.finki.ukim.mk"
_FINKI_HOSTS = frozenset({"finki.ukim.mk", "www.finki.ukim.mk", LEGACY_HOST})
ALLOWED_CATEGORIES = frozenset(
    {
        "studies",
        "programmes",
        "student-support",
        "procedures",
        "forms",
        "erasmus",
        "organizations",
        "thesis-internship",
        "institutional",
        "legal",
        "privacy",
        "public-information",
        "contact",
        "international-study",
    }
)
MAX_REVIEW_AGE = timedelta(days=180)
_DEFAULT_SOURCES = Path("website-reference/sources.toml")
_DEFAULT_AGGREGATE = Path("website-reference/finki-static-pages.md")
_BOILERPLATE_OUTPUT = frozenset(
    {
        "menu",
        "navigation",
        "skip to content",
        "skip to main content",
    }
)
_MARKDOWN_HEADING = re.compile(r"^\s{0,3}#{1,6}(?:\s+.*)?$")
_PROSE_LINE_MIN_LENGTH = 40
_MARKDOWN_LINK_WITH_TARGET = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")

_TOP_LEVEL_KEYS = frozenset({"version", "sources"})
_SOURCE_KEYS = frozenset(
    {
        "id",
        "source_url",
        "canonical_url",
        "language",
        "category",
        "content_kind",
        "last_verified",
        "content_selectors",
    }
)
_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_START_PATTERN = re.compile(
    r"^<!-- finki-static-page:start id=([a-z0-9]+(?:-[a-z0-9]+)*) -->$"
)
_END_MARKER = "<!-- finki-static-page:end -->"
_MARKER_PREFIX = "<!-- finki-static-page:"
_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_CSS_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_-]*"
_CSS_SIMPLE_SELECTOR = (
    rf"(?:{_CSS_IDENTIFIER}|\#{_CSS_IDENTIFIER}|\.{_CSS_IDENTIFIER})"
    rf"(?:\#{_CSS_IDENTIFIER})?(?:\.{_CSS_IDENTIFIER})*"
    rf"(?::nth-child\([1-9][0-9]*\))?"
)
_CSS_SELECTOR = re.compile(
    rf"{_CSS_SIMPLE_SELECTOR}(?:(?:\s+|\s*>\s*){_CSS_SIMPLE_SELECTOR})*"
)
_FORBIDDEN_ROUTE_SEGMENTS = frozenset(
    {
        "admission",
        "admissions",
        "announcement",
        "announcements",
        "archive",
        "archives",
        "assets",
        "asset",
        "call",
        "calls",
        "candidate",
        "candidates",
        "event",
        "events",
        "feed",
        "feeds",
        "jobs",
        "job",
        "media",
        "news",
        "image",
        "images",
        "document",
        "documents",
        "download",
        "downloads",
        "personnel",
        "projects",
        "project",
        "quota",
        "quotas",
        "ranking",
        "rankings",
        "results",
        "schedule",
        "schedules",
        "staff",
        "wp-admin",
        "wp-content",
        "wp-json",
        "wp-login.php",
        "uploads",
        "upload",
        "files",
        "file",
    }
)
_APPROVED_MK_ROUTE_ROOTS = frozenset({"za-nas", "upisi", "studii-2"})
_APPROVED_MK_ROUTE_PATHS = frozenset(
    {
        "/elektronski-dokumenti/",
        "/procedura-za-ponishtuvanje-na-ocena/",
        "/pravila-za-zapishuvanje-na-predmeti/",
    }
)
_APPROVED_TRANSFER_PATH = (
    "/announcements/soopshtenie-za-prefrluvanje-od-drug-fakultet-10/"
)
_APPROVED_INTERNATIONAL_PATHS = frozenset(
    {
        "/internacionalni-studenti/admissions/undergraduate-studies-for-international-students/",
        "/internacionalni-studenti/admissions/masters-studies-for-international-students/",
    }
)


@dataclass(frozen=True, slots=True)
class ReferenceSource:
    id: str
    source_url: str
    canonical_url: str
    language: str
    category: str
    content_kind: str
    last_verified: date
    content_selectors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReferencePage:
    source_id: str
    source_url: str
    canonical_url: str
    language: str
    category: str
    content_kind: str
    last_verified: date
    title: str
    body: str
    content_sha256: str

    @property
    def id(self) -> str:
        return self.source_id

    @property
    def normalized_body(self) -> str:
        return self.body

    @property
    def sha256(self) -> str:
        return self.content_sha256

    @property
    def content_hash(self) -> str:
        return self.content_sha256


def _error(message: str) -> ValueError:
    return ValueError(f"invalid website reference: {message}")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise _error(f"{field} must be a non-empty single-line string")
    if _MARKER_PREFIX in value:
        raise _error(f"{field} contains an aggregate boundary marker")
    return value


def _parse_date(value: object, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise _error(f"{field} must be an ISO date") from exc
    raise _error(f"{field} must be an ISO date")


def _content_selectors(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise _error("content_selectors must be a non-empty list")
    selectors: list[str] = []
    for selector in value:
        selector_text = _text(selector, "content_selectors")
        if any(
            ord(character) < 32 or ord(character) == 127 for character in selector_text
        ):
            raise _error(f"content_selectors contains invalid CSS: {selector_text!r}")
        stripped = selector_text.strip()
        if not stripped:
            raise _error("content_selectors must not contain blank selectors")
        if _CSS_SELECTOR.fullmatch(stripped) is None:
            raise _error(f"content_selectors contains invalid CSS: {selector_text!r}")
        selectors.append(selector_text)
    return tuple(selectors)


def _content_kind(value: object) -> str:
    kind = _text(value, "content_kind")
    if kind not in ALLOWED_CONTENT_KINDS:
        raise _error(f"content_kind {kind!r} is not allowed")
    return kind


def _validate_route(raw_url: str, field: str) -> str:
    try:
        parsed = urlsplit(raw_url)
    except ValueError as exc:
        raise _error(f"{field} is not a valid URL") from exc
    if parsed.scheme != "https":
        raise _error(f"{field} must use HTTPS")
    host = (parsed.hostname or "").casefold()
    if host not in _FINKI_HOSTS or parsed.username or parsed.password:
        raise _error(f"{field} must use an approved FINKI host")
    if parsed.port is not None:
        raise _error(f"{field} must not specify a port")
    if parsed.query or parsed.fragment:
        raise _error(f"{field} must not contain a query or fragment")
    normalized = normalize_url(raw_url)
    if normalized is None and host == LEGACY_HOST:
        path = _normalized_path(parsed.path)
        if path is not None:
            normalized = urlunsplit(("https", LEGACY_HOST, path, "", ""))
    if normalized is None:
        raise _error(f"{field} is not an allowed public route")
    normalized_path = urlsplit(normalized).path
    normalized_path_casefold = normalized_path.casefold()
    segments = tuple(
        unquote(segment).casefold() for segment in normalized_path.split("/") if segment
    )
    route_language = _route_language_for_path(normalized_path_casefold)
    if route_language is None:
        raise _error(f"{field} is not an approved curated route")
    if host == LEGACY_HOST and segments[0] != CURATED_SOURCE_LANGUAGE:
        raise _error(f"{field} must use a MK /mk/ route on the legacy host")
    ignored_forbidden_segments = set[str]()
    if normalized_path_casefold == _APPROVED_TRANSFER_PATH:
        ignored_forbidden_segments.add("announcements")
    if normalized_path_casefold in _APPROVED_INTERNATIONAL_PATHS:
        ignored_forbidden_segments.add("admissions")
    if any(
        (
            segment in _FORBIDDEN_ROUTE_SEGMENTS
            and segment not in ignored_forbidden_segments
        )
        or any(
            token in _FORBIDDEN_ROUTE_SEGMENTS
            and token not in ignored_forbidden_segments
            for token in re.split(r"[-_.]+", segment)
            if token
        )
        for segment in segments
    ):
        raise _error(f"{field} uses a forbidden route class")
    final_segment = segments[-1]
    if "." in final_segment and not final_segment.endswith(".html"):
        raise _error(f"{field} must identify an HTML route, not an asset")
    if any(
        segment.isdigit() or re.fullmatch(r"\d{4}[-_]\d{1,2}", segment)
        for segment in segments
    ):
        raise _error(f"{field} must not identify a dated page route")
    if any(
        token in raw_url.casefold()
        for token in ("candidate=", "student-id", "personal-id")
    ):
        raise _error(f"{field} must not contain a candidate identifier")
    return normalized


def _language_for_route(url: str) -> str:
    language = _route_language_for_path(urlsplit(url).path.casefold())
    if language is None:
        raise _error("route language cannot be derived")
    return language


def _route_language_for_path(path: str) -> str | None:
    first_segment = path.strip("/").split("/", maxsplit=1)[0]
    if first_segment in ALLOWED_LANGUAGES:
        return first_segment
    if path in _APPROVED_INTERNATIONAL_PATHS:
        return "en"
    if path == _APPROVED_TRANSFER_PATH or path in _APPROVED_MK_ROUTE_PATHS:
        return "mk"
    if first_segment in _APPROVED_MK_ROUTE_ROOTS:
        return "mk"
    return None


def _routes_match(source_url: str, canonical_url: str) -> bool:
    normalized_source = _validate_route(source_url, "source_url")
    normalized_canonical = _validate_route(canonical_url, "canonical_url")
    if normalized_source == normalized_canonical:
        return True
    source_host = (urlsplit(source_url).hostname or "").casefold()
    canonical_host = (urlsplit(canonical_url).hostname or "").casefold()
    return (
        source_host in {"finki.ukim.mk", "www.finki.ukim.mk"}
        and canonical_host == LEGACY_HOST
        and urlsplit(normalized_source).path == urlsplit(normalized_canonical).path
    )


def _source_from_mapping(raw: object, *, today: date) -> ReferenceSource:
    if not isinstance(raw, Mapping):
        raise _error("each source must be a table")
    if set(raw) != _SOURCE_KEYS:
        missing = sorted(_SOURCE_KEYS - set(raw))
        extra = sorted(set(raw) - _SOURCE_KEYS)
        detail = f"missing {missing}" if missing else f"unknown fields {extra}"
        raise _error(f"source has {detail}")
    source_id = _text(raw["id"], "id")
    if _ID_PATTERN.fullmatch(source_id) is None:
        raise _error("id must be a stable lowercase hyphenated identifier")
    language = _text(raw["language"], "language")
    category = _text(raw["category"], "category")
    if category not in ALLOWED_CATEGORIES:
        raise _error(f"category {category!r} is not allowed")
    content_kind = _content_kind(raw["content_kind"])
    source_url = _text(raw["source_url"], "source_url")
    canonical_url = _text(raw["canonical_url"], "canonical_url")
    content_selectors = _content_selectors(raw["content_selectors"])
    normalized_source = _validate_route(source_url, "source_url")
    normalized_canonical = _validate_route(canonical_url, "canonical_url")
    if not _routes_match(source_url, canonical_url):
        raise _error("source_url and canonical_url identify different routes")
    if language != _language_for_route(normalized_source):
        raise _error("language does not match the source route")
    if language not in ALLOWED_LANGUAGES:
        raise _error(f"language {language!r} is not allowed")
    verified = _parse_date(raw["last_verified"], "last_verified")
    if verified > today:
        raise _error("last_verified cannot be in the future")
    if today - verified > MAX_REVIEW_AGE:
        raise _error("last_verified exceeds the review age")
    return ReferenceSource(
        id=source_id,
        source_url=source_url,
        canonical_url=normalized_canonical,
        language=language,
        category=category,
        content_kind=content_kind,
        last_verified=verified,
        content_selectors=content_selectors,
    )


def load_sources(path: Path, *, today: date) -> tuple[ReferenceSource, ...]:
    """Load and validate the offline curated source allowlist."""
    try:
        raw_document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise _error(f"cannot read TOML allowlist: {exc}") from exc
    if set(raw_document) != _TOP_LEVEL_KEYS:
        missing = sorted(_TOP_LEVEL_KEYS - set(raw_document))
        extra = sorted(set(raw_document) - _TOP_LEVEL_KEYS)
        detail = f"missing {missing}" if missing else f"unknown fields {extra}"
        raise _error(f"allowlist has {detail}")
    if raw_document["version"] != 2:
        raise _error("allowlist version must be 2")
    raw_sources = raw_document["sources"]
    if not isinstance(raw_sources, list):
        raise _error("sources must be an array of tables")
    sources = tuple(_source_from_mapping(raw, today=today) for raw in raw_sources)
    if not 2 <= len(sources) <= 50:
        raise _error("allowlist must contain between 2 and 50 sources")
    ids = [source.id for source in sources]
    if len(set(ids)) != len(ids):
        raise _error("source IDs must be unique")
    urls = [source.canonical_url for source in sources]
    if len(set(urls)) != len(urls):
        raise _error("canonical URLs must be unique")
    return tuple(sorted(sources, key=lambda source: source.id))


def _normalize_body(body: str) -> str:
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    return "\n".join(lines).strip()


def _has_substantive_markdown(body: str) -> bool:
    return any(
        line and _MARKDOWN_HEADING.fullmatch(line) is None for line in body.splitlines()
    )


def _without_markdown_links(markdown: str) -> tuple[str, tuple[str, ...]]:
    labels = tuple(match.group(1) for match in _MARKDOWN_LINK.finditer(markdown))
    return _MARKDOWN_LINK.sub("", markdown), labels


def _has_substantive_non_link_prose(markdown: str) -> bool:
    non_link, _ = _without_markdown_links(markdown)
    letter_digits = sum(character.isalnum() for character in non_link)
    prose_lines = (
        " ".join(line.split())
        for line in non_link.splitlines()
        if " ".join(line.split())
    )
    return letter_digits >= 160 and any(
        len(line) >= _PROSE_LINE_MIN_LENGTH for line in prose_lines
    )


def has_substantive_prose(markdown: str) -> bool:
    """Return whether markdown meets the curated page prose threshold."""
    non_link, labels = _without_markdown_links(markdown)
    prose_characters = len(non_link)
    link_label_characters = sum(len(label) for label in labels)
    return (
        _has_substantive_non_link_prose(markdown)
        and link_label_characters < prose_characters
    )


def is_navigation_shaped(markdown: str, *, ignore_headings: bool = False) -> bool:
    """Return whether normalized non-link labels repeat at least three times."""
    labels: dict[str, int] = {}
    for line in markdown.splitlines():
        if ignore_headings and _MARKDOWN_HEADING.fullmatch(line):
            continue
        line = _MARKDOWN_LINK.sub(r"\1", line)
        normalized = " ".join(re.sub(r"^[\s>*#-]+", "", line).split()).casefold()
        if normalized:
            labels[normalized] = labels.get(normalized, 0) + 1
    return any(
        count >= 3 and len(label) < _PROSE_LINE_MIN_LENGTH
        for label, count in labels.items()
    )


def _link_catalog_links(markdown: str) -> tuple[tuple[str, str], ...]:
    matches = tuple(_MARKDOWN_LINK_WITH_TARGET.finditer(markdown))
    links: list[tuple[str, str]] = []
    for match in matches:
        label = " ".join(match.group(1).split())
        target = match.group(2).strip().strip("<>")
        parsed = urlsplit(target)
        if (
            not label
            or parsed.scheme.casefold() not in {"http", "https"}
            or not parsed.hostname
            or any(character.isspace() for character in target)
        ):
            raise _error("link-catalog contains an unsafe or placeholder link")
        links.append((target, label))
    if len({target for target, _ in links}) < 3:
        raise _error("link-catalog requires at least three distinct links")
    if sum(character.isalnum() for _, label in links for character in label) < 160:
        raise _error("link-catalog link labels are too short")
    return tuple(links)


def _validate_reference_body(markdown: str, page_id: str, *, content_kind: str) -> str:
    body = _normalize_body(markdown)
    _content_kind(content_kind)
    common_failure = (
        not body
        or body.casefold() in _BOILERPLATE_OUTPUT
        or not _has_substantive_markdown(body)
    )
    if content_kind == "prose":
        quality_failure = (
            common_failure
            or not has_substantive_prose(body)
            or is_navigation_shaped(body)
        )
    elif content_kind == "structured":
        link_dominated = False
        non_link, labels = _without_markdown_links(body)
        if non_link:
            link_dominated = sum(len(label) for label in labels) >= len(non_link)
        quality_failure = (
            common_failure
            or not _has_substantive_non_link_prose(body)
            or (link_dominated and is_navigation_shaped(body, ignore_headings=True))
        )
    else:
        quality_failure = common_failure or is_navigation_shaped(body)
        if not quality_failure:
            _link_catalog_links(body)
    if quality_failure:
        raise _error(
            f"page {page_id} has empty, markup-only, boilerplate, or navigation-shaped output"
        )
    if _MARKER_PREFIX in body:
        raise _error(f"page {page_id} contains an aggregate boundary marker")
    return body


def validate_reference_body(markdown: str, page_id: str, *, content_kind: str) -> str:
    """Validate and return one normalized body using its declared content kind."""
    return _validate_reference_body(markdown, page_id, content_kind=content_kind)


def _content_hash(title: str, body: str) -> str:
    return sha256(f"{title}\n\n{body}".encode()).hexdigest()


def _page_from_block(lines: list[str], source_id: str) -> ReferencePage:
    if len(lines) < 8 or lines[0] != f"<!-- finki-static-page:start id={source_id} -->":
        raise _error("malformed aggregate block start")
    metadata: dict[str, str] = {}
    index = 1
    while index < len(lines) and lines[index]:
        key, separator, value = lines[index].partition(": ")
        if not separator or key not in {
            "source_url",
            "canonical_url",
            "language",
            "category",
            "content_kind",
            "last_verified",
            "title",
            "sha256",
        }:
            raise _error("malformed aggregate metadata")
        if key in metadata:
            raise _error(f"duplicate aggregate metadata field {key}")
        metadata[key] = value
        index += 1
    required = {
        "source_url",
        "canonical_url",
        "language",
        "category",
        "content_kind",
        "last_verified",
        "title",
        "sha256",
    }
    if set(metadata) != required or index >= len(lines) or lines[index] != "":
        raise _error("aggregate metadata is incomplete")
    content_kind = _content_kind(metadata["content_kind"])
    body = _validate_reference_body(
        "\n".join(lines[index + 1 :]), source_id, content_kind=content_kind
    )
    title = _text(metadata["title"], "title")
    source_url = metadata["source_url"]
    canonical_url = metadata["canonical_url"]
    normalized_source = _validate_route(source_url, "source_url")
    normalized_canonical = _validate_route(canonical_url, "canonical_url")
    if not _routes_match(source_url, canonical_url):
        raise _error("aggregate source and canonical URLs differ")
    language = _text(metadata["language"], "language")
    if language not in ALLOWED_LANGUAGES:
        raise _error(f"language {language!r} is not allowed")
    if language != _language_for_route(normalized_source):
        raise _error("language does not match the aggregate route")
    category = _text(metadata["category"], "category")
    if category not in ALLOWED_CATEGORIES:
        raise _error(f"category {category!r} is not allowed")
    verified = _parse_date(metadata["last_verified"], "last_verified")
    digest = metadata["sha256"]
    if _HASH_PATTERN.fullmatch(digest) is None or digest != _content_hash(title, body):
        raise _error(f"hash verification failed for {source_id}")
    return ReferencePage(
        source_id=source_id,
        source_url=source_url,
        canonical_url=normalized_canonical,
        language=language,
        category=category,
        content_kind=content_kind,
        last_verified=verified,
        title=title,
        body=body,
        content_sha256=digest,
    )


def parse_aggregate(text: str) -> tuple[ReferencePage, ...]:
    """Parse and verify the deterministic, offline aggregate contract."""
    if "\r" in text:
        raise _error("aggregate must use LF-only line endings")
    lines = text.split("\n")
    pages: list[ReferencePage] = []
    index = 0
    while index < len(lines):
        if not lines[index]:
            index += 1
            continue
        match = _START_PATTERN.fullmatch(lines[index])
        if match is None:
            raise _error("unexpected content outside aggregate block")
        source_id = match.group(1)
        start = index
        try:
            end = lines.index(_END_MARKER, start + 1)
        except ValueError as exc:
            raise _error("aggregate block boundary is incomplete") from exc
        block_body = lines[start + 1 : end]
        if any(_MARKER_PREFIX in line for line in block_body):
            raise _error("aggregate block boundary injection")
        index = end + 1
        while index < len(lines) and not lines[index]:
            index += 1
        if index < len(lines) and _START_PATTERN.fullmatch(lines[index]) is None:
            raise _error("aggregate block boundary injection")
        pages.append(_page_from_block(lines[start:end], source_id))
    ids = [page.source_id for page in pages]
    if len(set(ids)) != len(ids):
        raise _error("aggregate source IDs must be unique")
    return tuple(pages)


def _validate_page_for_render(page: ReferencePage) -> str:
    source_id = _text(page.source_id, "source_id")
    if _ID_PATTERN.fullmatch(source_id) is None:
        raise _error("source_id must be a stable lowercase hyphenated identifier")
    source_url = _text(page.source_url, "source_url")
    canonical_url = _text(page.canonical_url, "canonical_url")
    normalized_source = _validate_route(source_url, "source_url")
    normalized_canonical = _validate_route(canonical_url, "canonical_url")
    if not _routes_match(source_url, canonical_url):
        raise _error("source_url and canonical_url identify different routes")
    language = _text(page.language, "language")
    if language not in ALLOWED_LANGUAGES:
        raise _error(f"language {language!r} is not allowed")
    if language != _language_for_route(normalized_source):
        raise _error("language does not match the route")
    category = _text(page.category, "category")
    if category not in ALLOWED_CATEGORIES:
        raise _error(f"category {category!r} is not allowed")
    _content_kind(page.content_kind)
    if not isinstance(page.last_verified, date) or isinstance(
        page.last_verified, datetime
    ):
        raise _error("last_verified must be an ISO date")
    _text(page.title, "title")
    return normalized_canonical


def render_aggregate(pages: Iterable[ReferencePage]) -> str:
    """Render pages in stable ID order using LF-only boundaries."""
    ordered = sorted(pages, key=lambda page: page.source_id)
    rendered: list[str] = []
    for page in ordered:
        canonical_url = _validate_page_for_render(page)
        body = _validate_reference_body(
            page.body, page.source_id, content_kind=page.content_kind
        )
        digest = _content_hash(page.title, body)
        if page.content_sha256 != digest:
            raise _error(f"hash verification failed for {page.source_id}")
        rendered.extend(
            [
                f"<!-- finki-static-page:start id={page.source_id} -->",
                f"source_url: {page.source_url}",
                f"canonical_url: {canonical_url}",
                f"language: {page.language}",
                f"category: {page.category}",
                f"content_kind: {page.content_kind}",
                f"last_verified: {page.last_verified.isoformat()}",
                f"title: {page.title}",
                f"sha256: {digest}",
                "",
                body,
                _END_MARKER,
                "",
            ]
        )
    return "\n".join(rendered)


def check_aggregate(
    text: str, sources: tuple[ReferenceSource, ...]
) -> tuple[ReferencePage, ...]:
    """Check that an aggregate contains exactly the supplied source metadata."""
    pages = parse_aggregate(text)
    by_id = {source.id: source for source in sources}
    if set(by_id) != {page.source_id for page in pages}:
        raise _error("aggregate sources do not match the allowlist")
    seen_hashes: dict[str, str] = {}
    for page in pages:
        source = by_id[page.source_id]
        if (
            page.source_url != source.source_url
            or page.canonical_url != source.canonical_url
            or page.language != source.language
            or page.category != source.category
            or page.content_kind != source.content_kind
            or page.last_verified != source.last_verified
        ):
            raise _error(f"aggregate metadata differs for {page.source_id}")
        if contains_sensitive_personal_identifier(title=page.title, markdown=page.body):
            raise _error(f"page {page.source_id} contains a sensitive identifier")
        digest = _content_hash(page.title, page.body)
        duplicate_id = seen_hashes.get(digest)
        if duplicate_id is not None:
            raise _error(
                f"duplicate normalized content for {page.source_id} and {duplicate_id}"
            )
        seen_hashes[digest] = page.source_id
    return pages


def validate_aggregate(
    text: str, sources: tuple[ReferenceSource, ...]
) -> tuple[ReferencePage, ...]:
    """Validate an aggregate against its offline source allowlist."""
    pages = check_aggregate(text, sources)
    if text != render_aggregate(pages):
        raise _error("aggregate serialization is not canonical")
    return pages


def _strip_images(html: str) -> str:
    parser = HTMLParser(html)
    if parser.root is None:
        return ""
    for image in parser.root.css("img"):
        image.decompose()
    return parser.root.html or ""


def _normalized_title(title: str) -> str:
    return " ".join(title.replace("\r", " ").replace("\n", " ").split())


def _is_html_content_type(value: str) -> bool:
    header = Message()
    header["content-type"] = value
    return header.get_content_type().casefold() == "text/html"


def extract_reference_document(html: str, source: ReferenceSource) -> WebsiteDocument:
    """Convert one curated source using only its configured content roots."""
    document_url = source.canonical_url
    if normalize_url(document_url) is None:
        parsed = urlsplit(document_url)
        document_url = urlunsplit(
            ("https", "finki.ukim.mk", parsed.path, parsed.query, parsed.fragment)
        )
    return document_from_page(
        _strip_images(html),
        document_url,
        content_selectors=source.content_selectors,
    )


def _read_aggregate(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return stream.read()


def _validate_refresh_sources(sources: Sequence[ReferenceSource]) -> None:
    ids = [source.id for source in sources]
    if len(set(ids)) != len(ids):
        raise _error("refresh source IDs must be unique")
    urls = [source.canonical_url for source in sources]
    if len(set(urls)) != len(urls):
        raise _error("refresh canonical URLs must be unique")
    for source in sources:
        _content_kind(source.content_kind)
        if not _routes_match(source.source_url, source.canonical_url):
            raise _error(f"source URL differs from canonical URL for {source.id}")
        if not isinstance(source.content_selectors, tuple):
            raise _error(f"content_selectors must be a tuple for {source.id}")
        _content_selectors(list(source.content_selectors))


async def _fetch_reference_pages(
    sources: Sequence[ReferenceSource], client: httpx2.AsyncClient
) -> tuple[ReferencePage, ...]:
    _validate_refresh_sources(sources)
    pages: list[ReferencePage] = []
    seen_hashes: dict[str, str] = {}
    for source in sources:
        response = await fetch_public(
            client,
            source.source_url,
            PAGE_FETCH_POLICY,
            allowed_redirect_urls=frozenset({source.canonical_url}),
            allowed_hosts=frozenset({urlsplit(source.canonical_url).hostname or ""}),
        )
        if response.status != 200:
            raise _error(f"page returned HTTP {response.status} for {source.id}")
        if not _is_html_content_type(response.content_type):
            raise _error(f"page is not HTML for {source.id}")
        if response.url != source.canonical_url:
            raise _error(
                f"page canonical URL differs for {source.id}: "
                f"expected {source.canonical_url}, got {response.url}"
            )
        html = response.body.decode(response.encoding, errors="replace")
        if _MARKER_PREFIX in html or _MARKER_PREFIX in html_module.unescape(html):
            raise _error(f"page {source.id} contains an aggregate boundary marker")
        try:
            document = extract_reference_document(html, source)
        except WebsiteContentError as exc:
            raise _error(f"cannot convert page {source.id}: {exc}") from exc
        title = _normalized_title(document.title)
        body = _validate_reference_body(
            document.markdown, source.id, content_kind=source.content_kind
        )
        if not title:
            raise _error(f"page {source.id} has an empty title")
        if _MARKER_PREFIX in title or _MARKER_PREFIX in body:
            raise _error(f"page {source.id} contains an aggregate boundary marker")
        if contains_sensitive_personal_identifier(title=title, markdown=body):
            raise _error(f"page {source.id} contains a sensitive identifier")
        digest = _content_hash(title, body)
        duplicate_id = seen_hashes.get(digest)
        if duplicate_id is not None:
            raise _error(
                f"duplicate normalized content for {source.id} and {duplicate_id}"
            )
        seen_hashes[digest] = source.id
        pages.append(
            ReferencePage(
                source_id=source.id,
                source_url=source.source_url,
                canonical_url=source.canonical_url,
                language=source.language,
                category=source.category,
                content_kind=source.content_kind,
                last_verified=source.last_verified,
                title=title,
                body=body,
                content_sha256=digest,
            )
        )
    return tuple(pages)


def _replace_atomically(output: Path, text: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as staged:
            temporary = staged.name
            staged.write(text)
            staged.flush()
            os.fsync(staged.fileno())
        os.replace(temporary, output)
        temporary = None
    finally:
        if temporary is not None:
            with suppress(FileNotFoundError):
                os.unlink(temporary)


def refresh_reference(
    sources: Sequence[ReferenceSource],
    output: Path,
    *,
    client: httpx2.AsyncClient | None = None,
) -> None:
    """Fetch the fixed allowlist and atomically replace its aggregate."""

    async def refresh() -> None:
        if client is None:
            async with httpx2.AsyncClient() as live_client:
                pages = await _fetch_reference_pages(sources, live_client)
        else:
            pages = await _fetch_reference_pages(sources, client)
        _replace_atomically(output, render_aggregate(pages))

    anyio.run(refresh)


def verify_live(
    sources: Sequence[ReferenceSource],
    aggregate: Path,
    *,
    client: httpx2.AsyncClient | None = None,
) -> None:
    """Compare live normalized page hashes with an aggregate without writing."""
    tracked = validate_aggregate(_read_aggregate(aggregate), tuple(sources))
    tracked_by_id = {page.source_id: page for page in tracked}

    async def verify() -> None:
        if client is None:
            async with httpx2.AsyncClient() as live_client:
                live = await _fetch_reference_pages(sources, live_client)
        else:
            live = await _fetch_reference_pages(sources, client)
        for page in live:
            tracked_page = tracked_by_id[page.source_id]
            if page.content_sha256 != tracked_page.content_sha256:
                raise _error(f"live hash differs for {page.source_id}")

    anyio.run(verify)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the curated website reference")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true", help="validate offline files")
    modes.add_argument("--refresh", action="store_true", help="refresh the aggregate")
    modes.add_argument(
        "--verify-live", action="store_true", help="compare live page hashes"
    )
    parser.add_argument("--sources", type=Path, default=_DEFAULT_SOURCES)
    parser.add_argument("--aggregate", type=Path, default=_DEFAULT_AGGREGATE)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _build_parser().parse_args(argv)
    sources = load_sources(arguments.sources, today=datetime.now(tz=UTC).date())
    if arguments.check:
        validate_aggregate(_read_aggregate(arguments.aggregate), sources)
    elif arguments.refresh:
        refresh_reference(sources, arguments.aggregate)
    else:
        verify_live(sources, arguments.aggregate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
