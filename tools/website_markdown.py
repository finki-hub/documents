from __future__ import annotations

import html as html_module
import re
from urllib.parse import urljoin, urlsplit

from markdownify import markdownify
from selectolax.parser import HTMLParser, Node

from tools.website_markdown_safety import (
    neutralize_markdown_blocks,
    sanitize_markdown_links,
)
from tools.website_models import (
    RestRecord,
    SourceKind,
    WebsiteDocument,
    language_for_url,
    normalize_url,
)

_REMOVED_SELECTORS = (
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "form",
    "header",
    "footer",
    "nav",
    ".page-sidebar",
    ".quick-icons",
    ".sidebar-events",
    ".breadcrumb",
    ".breadcrumbs",
)


class WebsiteContentError(ValueError):
    reason: str
    url: str | None

    def __init__(self, reason: str, url: str | None = None) -> None:
        self.reason = reason
        self.url = url
        location = f": {url}" if url else ""
        super().__init__(f"{reason}{location}")


def _clean_markdown(value: str) -> str:
    cleaned = value.replace("\xa0", " ").replace("\r\n", "\n")
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _escape_markdown_text(value: str) -> str:
    escaped = html_module.escape(value, quote=False).replace("\\", "\\\\")
    return re.sub(r"([`*_{}\[\]()#+.!|-])", r"\\\1", escaped)


def _clean_title(value: str) -> str:
    return html_module.unescape(value).strip()


def _safe_link(raw_url: str, base_url: str) -> str | None:
    try:
        absolute = urljoin(base_url, raw_url)
        return (
            absolute
            if urlsplit(absolute).scheme in {"http", "https", "mailto"}
            else None
        )
    except ValueError:
        return None


def _safe_image(raw_url: str, base_url: str) -> str | None:
    try:
        absolute = urljoin(base_url, raw_url)
        return absolute if urlsplit(absolute).scheme in {"http", "https"} else None
    except ValueError:
        return None


def _sanitize_html(value: str, base_url: str) -> str:
    parser = HTMLParser(value)
    if parser.root is None:
        return ""
    for selector in _REMOVED_SELECTORS:
        for node in parser.root.css(selector):
            node.decompose()
    for node in parser.root.css("a[href]"):
        href = node.attributes.get("href")
        if href and (safe_link := _safe_link(href, base_url)) is not None:
            node.attrs["href"] = safe_link
        else:
            del node.attrs["href"]
    for node in parser.root.css("img[src]"):
        source = node.attributes.get("src")
        if source and (safe_image := _safe_image(source, base_url)) is not None:
            node.attrs["src"] = safe_image
        else:
            del node.attrs["src"]
    return parser.root.html or ""


def _markdown_from_html(value: str, base_url: str) -> str:
    converted = markdownify(
        _sanitize_html(value, base_url),
        bullets="-",
        heading_style="ATX",
        strip=["script", "style", "noscript", "template", "svg"],
    )
    inert_html = converted.replace("<", "&lt;").replace(">", "&gt;")
    return _clean_markdown(
        neutralize_markdown_blocks(sanitize_markdown_links(inert_html))
    )


def _content_root(parser: HTMLParser) -> Node:
    for selector in ("main", "article", "body"):
        node = parser.css_first(selector)
        if node is not None:
            return node
    if parser.root is None:
        raise WebsiteContentError("HTML document has no root node")
    return parser.root


def _title(parser: HTMLParser, root: Node, url: str) -> str:
    headings = [
        value
        for node in root.css("h1")
        if (value := node.text(separator=" ", strip=True))
    ]
    for value in reversed(headings):
        if title := _clean_title(value):
            return title
    for selector in (".page-title", ".entry-title", "title"):
        node = root.css_first(selector) or parser.css_first(selector)
        if (
            node is not None
            and (value := node.text(separator=" ", strip=True))
            and (title := _clean_title(value))
        ):
            return title
    return url.rstrip("/").rsplit("/", maxsplit=1)[-1].replace("-", " ").title()


def document_from_page(html: str, url: str) -> WebsiteDocument:
    parser = HTMLParser(html)
    root = _content_root(parser)
    for selector in _REMOVED_SELECTORS:
        for node in root.css(selector):
            node.decompose()
    title = _title(parser, root, url)
    for heading in root.css("h1"):
        heading.decompose()
    canonical_url = normalize_url(url)
    if canonical_url is None:
        raise WebsiteContentError("Unsupported source URL", url)
    return WebsiteDocument(
        aliases=(),
        language=language_for_url(canonical_url),
        markdown=_markdown_from_html(root.html or "", canonical_url),
        modified=None,
        source_kind=SourceKind.RENDERED,
        title=title,
        url=canonical_url,
        wordpress_id=None,
        wordpress_type=None,
    )


def document_from_rest(
    record: RestRecord,
    *,
    include_excerpt: bool = True,
) -> WebsiteDocument:
    canonical_url = normalize_url(record.link)
    if canonical_url is None:
        raise WebsiteContentError("Unsupported source URL", record.link)
    content = record.content.rendered if record.content else ""
    markdown = _markdown_from_html(content, canonical_url)
    if not markdown and include_excerpt and record.excerpt:
        markdown = _markdown_from_html(record.excerpt.rendered, canonical_url)
    title = _clean_title(record.title.rendered if record.title else "") or _clean_title(
        record.slug
    )
    return WebsiteDocument(
        aliases=(),
        language=language_for_url(canonical_url),
        markdown=markdown,
        modified=record.modified,
        source_kind=SourceKind.REST,
        title=title,
        url=canonical_url,
        wordpress_id=record.id,
        wordpress_type=record.type,
    )


def render_document(document: WebsiteDocument) -> str:
    def metadata_value(value: str) -> str:
        flattened = " ".join(value.splitlines())
        return flattened.replace("<", "&lt;").replace(">", "&gt;")

    metadata = [
        "<!-- finki-website-source",
        f"url: {metadata_value(document.url)}",
        f"language: {metadata_value(document.language)}",
        f"source_kind: {metadata_value(document.source_kind.value)}",
    ]
    if document.modified:
        metadata.append(f"modified: {metadata_value(document.modified)}")
    if document.wordpress_id is not None:
        metadata.append(f"wordpress_id: {document.wordpress_id}")
    if document.wordpress_type:
        metadata.append(f"wordpress_type: {metadata_value(document.wordpress_type)}")
    safe_title = _escape_markdown_text(document.title)
    safe_markdown = neutralize_markdown_blocks(
        sanitize_markdown_links(document.markdown)
    )
    metadata.extend(("-->", "", f"# {safe_title}", "", safe_markdown, ""))
    return "\n".join(metadata)
