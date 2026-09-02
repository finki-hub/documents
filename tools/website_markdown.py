from __future__ import annotations

import html as html_module
import re
from urllib.parse import urljoin

from markdownify import markdownify
from selectolax.parser import HTMLParser, Node

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


def _markdown_from_html(value: str) -> str:
    return _clean_markdown(
        markdownify(
            value,
            bullets="-",
            heading_style="ATX",
            strip=["script", "style", "noscript", "template", "svg"],
        )
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
    if headings:
        return html_module.unescape(headings[-1])
    for selector in (".page-title", ".entry-title", "title"):
        node = root.css_first(selector) or parser.css_first(selector)
        if node is not None and (value := node.text(separator=" ", strip=True)):
            return html_module.unescape(value)
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
    for node in root.css("a[href]"):
        href = node.attributes.get("href")
        if href:
            node.attrs["href"] = urljoin(url, href)
    canonical_url = normalize_url(url)
    if canonical_url is None:
        raise WebsiteContentError("Unsupported source URL", url)
    return WebsiteDocument(
        aliases=(),
        language=language_for_url(canonical_url),
        markdown=_markdown_from_html(root.html or ""),
        modified=None,
        source_kind=SourceKind.RENDERED,
        title=title,
        url=canonical_url,
        wordpress_id=None,
        wordpress_type=None,
    )


def document_from_rest(record: RestRecord) -> WebsiteDocument:
    canonical_url = normalize_url(record.link)
    if canonical_url is None:
        raise WebsiteContentError("Unsupported source URL", record.link)
    body = record.content.rendered if record.content else ""
    if not body and record.excerpt:
        body = record.excerpt.rendered
    title = html_module.unescape(record.title.rendered if record.title else record.slug)
    return WebsiteDocument(
        aliases=(),
        language=language_for_url(canonical_url),
        markdown=_markdown_from_html(body),
        modified=record.modified,
        source_kind=SourceKind.REST,
        title=title,
        url=canonical_url,
        wordpress_id=record.id,
        wordpress_type=record.type,
    )


def render_document(document: WebsiteDocument) -> str:
    metadata = [
        "<!-- finki-website-source",
        f"url: {document.url}",
        f"language: {document.language}",
        f"source_kind: {document.source_kind.value}",
    ]
    if document.modified:
        metadata.append(f"modified: {document.modified}")
    if document.wordpress_id is not None:
        metadata.append(f"wordpress_id: {document.wordpress_id}")
    if document.wordpress_type:
        metadata.append(f"wordpress_type: {document.wordpress_type}")
    metadata.extend(("-->", "", f"# {document.title}", "", document.markdown, ""))
    return "\n".join(metadata)
