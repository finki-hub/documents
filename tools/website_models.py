from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Final
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, TypeAdapter

BASE_URL: Final = "https://finki.ukim.mk/"
PUBLIC_HOSTS: Final = frozenset({"finki.ukim.mk", "www.finki.ukim.mk"})
QUERY_KEYS: Final = frozenset({"kat", "pg"})
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


@dataclass(frozen=True, slots=True)
class CrawlPlan:
    seed_urls: tuple[str, ...]
    excluded_urls: frozenset[str] = frozenset()
    max_pages: int = 10_000


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
    document_count: int
    documents: tuple[ManifestEntry, ...]
    rest_totals: dict[str, int]
    schema_version: int = 1


def normalize_url(raw_url: str, base_url: str = BASE_URL) -> str | None:
    parsed = urlsplit(urljoin(base_url, raw_url))
    if parsed.scheme not in {"http", "https"}:
        return None
    if (parsed.hostname or "").casefold() not in PUBLIC_HOSTS:
        return None
    path = parsed.path or "/"
    if path.startswith(("/wp-admin", "/wp-json")) or "/feed/" in path:
        return None
    query = urlencode(
        sorted((key, value) for key, value in parse_qsl(parsed.query) if key in QUERY_KEYS)
    )
    return urlunsplit(("https", "finki.ukim.mk", path, query, ""))


def language_for_url(url: str) -> str:
    return "en" if urlsplit(url).path.startswith("/en/") else "mk"
