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
from hashlib import sha256
from pathlib import Path
from urllib.parse import unquote, urlsplit

import anyio
import httpx2
from selectolax.parser import HTMLParser

from .website_http import PAGE_FETCH_POLICY, fetch_public
from .website_markdown import WebsiteContentError, document_from_page
from .website_models import normalize_url
from .website_privacy import contains_sensitive_personal_identifier

ALLOWED_LANGUAGES = frozenset({"en"})
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

_TOP_LEVEL_KEYS = frozenset({"version", "sources"})
_SOURCE_KEYS = frozenset(
    {"id", "source_url", "canonical_url", "language", "category", "last_verified"}
)
_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_START_PATTERN = re.compile(
    r"^<!-- finki-static-page:start id=([a-z0-9]+(?:-[a-z0-9]+)*) -->$"
)
_END_MARKER = "<!-- finki-static-page:end -->"
_MARKER_PREFIX = "<!-- finki-static-page:"
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


@dataclass(frozen=True, slots=True)
class ReferenceSource:
    id: str
    source_url: str
    canonical_url: str
    language: str
    category: str
    last_verified: date


@dataclass(frozen=True, slots=True)
class ReferencePage:
    source_id: str
    source_url: str
    canonical_url: str
    language: str
    category: str
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


def _validate_route(raw_url: str, field: str) -> str:
    try:
        parsed = urlsplit(raw_url)
    except ValueError as exc:
        raise _error(f"{field} is not a valid URL") from exc
    if parsed.scheme != "https":
        raise _error(f"{field} must use HTTPS")
    if parsed.hostname != "finki.ukim.mk" or parsed.username or parsed.password:
        raise _error(f"{field} must use the finki.ukim.mk host")
    if parsed.port is not None:
        raise _error(f"{field} must not specify a port")
    if parsed.query or parsed.fragment:
        raise _error(f"{field} must not contain a query or fragment")
    normalized = normalize_url(raw_url)
    if normalized is None:
        raise _error(f"{field} is not an allowed public route")
    segments = tuple(
        unquote(segment).casefold()
        for segment in urlsplit(normalized).path.split("/")
        if segment
    )
    if not segments or segments[0] != "en":
        raise _error(f"{field} must use an English /en/ route")
    if any(
        segment in _FORBIDDEN_ROUTE_SEGMENTS
        or any(
            token in _FORBIDDEN_ROUTE_SEGMENTS
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
        raise _error(f"{field} must not identify a dated page")
    if any(
        token in raw_url.casefold()
        for token in ("candidate=", "student-id", "personal-id")
    ):
        raise _error(f"{field} must not contain a candidate identifier")
    return normalized


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
    if language not in ALLOWED_LANGUAGES:
        raise _error(f"language {language!r} is not allowed")
    category = _text(raw["category"], "category")
    if category not in ALLOWED_CATEGORIES:
        raise _error(f"category {category!r} is not allowed")
    source_url = _text(raw["source_url"], "source_url")
    canonical_url = _text(raw["canonical_url"], "canonical_url")
    normalized_source = _validate_route(source_url, "source_url")
    normalized_canonical = _validate_route(canonical_url, "canonical_url")
    if normalized_source != normalized_canonical:
        raise _error("source_url and canonical_url identify different routes")
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
        last_verified=verified,
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
    if raw_document["version"] != 1:
        raise _error("allowlist version must be 1")
    raw_sources = raw_document["sources"]
    if not isinstance(raw_sources, list):
        raise _error("sources must be an array of tables")
    sources = tuple(_source_from_mapping(raw, today=today) for raw in raw_sources)
    if not 20 <= len(sources) <= 50:
        raise _error("allowlist must contain between 20 and 50 sources")
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
        "last_verified",
        "title",
        "sha256",
    }
    if set(metadata) != required or index >= len(lines) or lines[index] != "":
        raise _error("aggregate metadata is incomplete")
    body = _normalize_body("\n".join(lines[index + 1 :]))
    title = _text(metadata["title"], "title")
    if not body:
        raise _error("aggregate page body cannot be empty")
    source_url = metadata["source_url"]
    canonical_url = metadata["canonical_url"]
    normalized_source = _validate_route(source_url, "source_url")
    normalized_canonical = _validate_route(canonical_url, "canonical_url")
    if normalized_source != normalized_canonical:
        raise _error("aggregate source and canonical URLs differ")
    language = _text(metadata["language"], "language")
    if language not in ALLOWED_LANGUAGES:
        raise _error(f"language {language!r} is not allowed")
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
    if normalized_source != normalized_canonical:
        raise _error("source_url and canonical_url identify different routes")
    language = _text(page.language, "language")
    if language != "en":
        raise _error("language must be English")
    category = _text(page.category, "category")
    if category not in ALLOWED_CATEGORIES:
        raise _error(f"category {category!r} is not allowed")
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
        body = _normalize_body(page.body)
        if not body:
            raise _error(f"aggregate page {page.source_id} has an empty body")
        digest = _content_hash(page.title, body)
        if page.content_sha256 != digest:
            raise _error(f"hash verification failed for {page.source_id}")
        if _MARKER_PREFIX in body:
            raise _error(f"aggregate page {page.source_id} contains a boundary marker")
        rendered.extend(
            [
                f"<!-- finki-static-page:start id={page.source_id} -->",
                f"source_url: {page.source_url}",
                f"canonical_url: {canonical_url}",
                f"language: {page.language}",
                f"category: {page.category}",
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
    for page in pages:
        source = by_id[page.source_id]
        if (
            page.source_url != source.source_url
            or page.canonical_url != source.canonical_url
            or page.language != source.language
            or page.category != source.category
            or page.last_verified != source.last_verified
        ):
            raise _error(f"aggregate metadata differs for {page.source_id}")
    return pages


def validate_aggregate(
    text: str, sources: tuple[ReferenceSource, ...]
) -> tuple[ReferencePage, ...]:
    """Validate an aggregate against its offline source allowlist."""
    return check_aggregate(text, sources)


def _strip_images(html: str) -> str:
    parser = HTMLParser(html)
    if parser.root is None:
        return ""
    for image in parser.root.css("img"):
        image.decompose()
    return parser.root.html or ""


def _normalized_title(title: str) -> str:
    return " ".join(title.replace("\r", " ").replace("\n", " ").split())


def _validate_refresh_sources(sources: Sequence[ReferenceSource]) -> None:
    ids = [source.id for source in sources]
    if len(set(ids)) != len(ids):
        raise _error("refresh source IDs must be unique")
    urls = [source.canonical_url for source in sources]
    if len(set(urls)) != len(urls):
        raise _error("refresh canonical URLs must be unique")
    for source in sources:
        if _validate_route(source.source_url, "source_url") != source.canonical_url:
            raise _error(f"source URL differs from canonical URL for {source.id}")


async def _fetch_reference_pages(
    sources: Sequence[ReferenceSource], client: httpx2.AsyncClient
) -> tuple[ReferencePage, ...]:
    _validate_refresh_sources(sources)
    pages: list[ReferencePage] = []
    seen_hashes: dict[str, str] = {}
    for source in sources:
        response = await fetch_public(client, source.source_url, PAGE_FETCH_POLICY)
        if response.status != 200:
            raise _error(f"page returned HTTP {response.status} for {source.id}")
        if "text/html" not in response.content_type:
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
            document = document_from_page(_strip_images(html), response.url)
        except WebsiteContentError as exc:
            raise _error(f"cannot convert page {source.id}: {exc}") from exc
        title = _normalized_title(document.title)
        body = _normalize_body(document.markdown)
        if not title:
            raise _error(f"page {source.id} has an empty title")
        if not body or body.casefold() in _BOILERPLATE_OUTPUT:
            raise _error(f"page {source.id} has empty or boilerplate output")
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
    tracked = validate_aggregate(aggregate.read_text(encoding="utf-8"), tuple(sources))
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
        validate_aggregate(arguments.aggregate.read_text(encoding="utf-8"), sources)
    elif arguments.refresh:
        refresh_reference(sources, arguments.aggregate)
    else:
        verify_live(sources, arguments.aggregate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
