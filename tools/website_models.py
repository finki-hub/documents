from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from posixpath import normpath
from typing import ClassVar, Final, Literal
from urllib.parse import (
    parse_qsl,
    quote,
    unquote,
    urlencode,
    urljoin,
    urlsplit,
    urlunsplit,
)

from pydantic import BaseModel, ConfigDict, TypeAdapter

BASE_URL: Final = "https://finki.ukim.mk/"
PUBLIC_HOSTS: Final = frozenset({"finki.ukim.mk", "www.finki.ukim.mk"})
QUERY_KEYS: Final = frozenset({"kat", "pg"})
NON_CONTENT_SEGMENTS: Final = frozenset(
    {"feed", "trackback", "wp-admin", "wp-json", "wp-login.php"}
)
TEXT_REST_BASES: Final = frozenset(
    {
        "announcement",
        "event",
        "jobs-and-internships",
        "nastaven_kadar",
        "pages",
        "partneri",
        "posts",
        "project",
        "schedule",
    }
)


class RenderedField(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)

    rendered: str = ""


class RestType(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)

    rest_base: str | None = None
    viewable: bool = False


class RestRecord(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore", frozen=True)

    content: RenderedField | None = None
    excerpt: RenderedField | None = None
    id: int
    link: str
    modified: str | None = None
    slug: str
    template: str = ""
    title: RenderedField | None = None
    type: str


REST_TYPES: Final = TypeAdapter(dict[str, RestType])
REST_RECORDS: Final = TypeAdapter(list[RestRecord])


class SourceKind(StrEnum):
    REST = "rest"
    RENDERED = "rendered"


@dataclass(frozen=True, slots=True)
class RestInventory:
    records_by_url: dict[str, RestRecord]
    totals: dict[str, int]


@dataclass(frozen=True, slots=True)
class PageSnapshot:
    final_url: str
    html: str
    links: tuple[str, ...]
    requested_url: str
    status: int
    aliases: tuple[str, ...] = ()
    size_bytes: int = 0


@dataclass(frozen=True, slots=True)
class CrawlPlan:
    seed_urls: tuple[str, ...]
    discovery_only_urls: frozenset[str] = frozenset()
    max_pages: int = 10_000


@dataclass(frozen=True, slots=True)
class CrawlResult:
    pages: tuple[PageSnapshot, ...]
    requested_count: int
    truncated: bool
    redirects: tuple[tuple[str, str], ...] = ()

    def __iter__(self) -> Iterator[PageSnapshot]:
        return iter(self.pages)


class GenerationMetadata(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    crawled_pages: int = 0
    crawl_truncated: bool = False
    rest_totals: dict[str, int]


@dataclass(frozen=True, slots=True)
class WebsiteDocument:
    aliases: tuple[str, ...]
    language: str
    markdown: str
    modified: str | None
    source_kind: SourceKind
    title: str
    url: str
    wordpress_id: int | None
    wordpress_type: str | None


class ManifestEntry(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    aliases: tuple[str, ...]
    language: str
    modified: str | None
    path: str
    source_kind: SourceKind
    title: str
    url: str
    wordpress_id: int | None
    wordpress_type: str | None


class WebsiteManifest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    base_url: str
    crawled_pages: int = 0
    crawl_truncated: bool = False
    document_count: int
    documents: tuple[ManifestEntry, ...]
    generator: Literal["finki-website-content"]
    rest_totals: dict[str, int]
    schema_version: Literal[2]


def _normalized_path(raw_path: str) -> str | None:
    decoded = raw_path or "/"
    for _ in range(5):
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            break
        decoded = next_decoded
    else:
        return None
    normalized = normpath(f"/{decoded.lstrip('/')}")
    if decoded.endswith("/") and normalized != "/":
        normalized = f"{normalized}/"
    return quote(normalized, safe="/!$&'()*+,-.;=:@_~")


def _public_url(raw_url: str, base_url: str) -> tuple[str, str] | None:
    try:
        parsed = urlsplit(urljoin(base_url, raw_url))
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    if (parsed.hostname or "").casefold() not in PUBLIC_HOSTS:
        return None
    path = _normalized_path(parsed.path)
    return (path, parsed.query) if path is not None else None


def normalize_url(raw_url: str, base_url: str = BASE_URL) -> str | None:
    public_url = _public_url(raw_url, base_url)
    if public_url is None:
        return None
    path, raw_query = public_url
    segments = frozenset(
        unquote(segment).casefold() for segment in path.split("/") if segment
    )
    if segments & NON_CONTENT_SEGMENTS:
        return None
    query = urlencode(
        sorted((key, value) for key, value in parse_qsl(raw_query) if key in QUERY_KEYS)
    )
    return urlunsplit(("https", "finki.ukim.mk", path, query, ""))


def normalize_rest_url(raw_url: str, base_url: str = BASE_URL) -> str | None:
    public_url = _public_url(raw_url, base_url)
    if public_url is None:
        return None
    path, query = public_url
    folded_path = path.casefold().rstrip("/")
    if folded_path != "/wp-json/wp/v2" and not folded_path.startswith(
        "/wp-json/wp/v2/"
    ):
        return None
    return urlunsplit(("https", "finki.ukim.mk", path, query, ""))


def language_for_url(url: str) -> str:
    return "en" if urlsplit(url).path.startswith("/en/") else "mk"
