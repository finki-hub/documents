from time import perf_counter

from tools.website_markdown import (
    document_from_page,
    document_from_rest,
    render_document,
)
from tools.website_models import RestRecord, SourceKind, WebsiteDocument


def test_document_from_page_extracts_main_content_and_absolute_links() -> None:
    document = document_from_page(
        """
        <html><head><title>Fallback</title></head><body>
          <header>Site navigation</header>
          <main><article><h1>Study programmes</h1>
            <p>Choose a <a href="/dodiplomski-studii/">programme</a>.</p>
            <script>ignored()</script>
          </article></main>
          <footer>Copyright</footer>
        </body></html>
        """,
        "https://finki.ukim.mk/en/studies/",
    )

    assert document.title == "Study programmes"
    assert document.language == "en"
    assert document.source_kind is SourceKind.RENDERED
    assert "Site navigation" not in document.markdown
    assert "Copyright" not in document.markdown
    assert "ignored" not in document.markdown
    assert "[programme](https://finki.ukim.mk/dodiplomski-studii/)" in document.markdown


def test_document_from_page_strips_whitespace_after_decoding_title() -> None:
    document = document_from_page(
        """
        <main><h1>
          Bioinformatics
          <span>(BI23_1)</span>
        </h1></main>
        """,
        "https://finki.ukim.mk/en/master-program/BI23_1/",
    )

    assert document.title == "Bioinformatics (BI23_1)"
    assert all(line == line.rstrip() for line in render_document(document).splitlines())


def test_document_from_page_removes_unsafe_link_targets() -> None:
    document = document_from_page(
        '<main><h1>Notice</h1><a href="javascript:alert(1)">click</a></main>',
        "https://finki.ukim.mk/notice/",
    )

    assert "javascript:" not in document.markdown
    assert "click" in document.markdown


def test_document_from_page_removes_unsafe_image_targets() -> None:
    document = document_from_page(
        """
        <main><h1>Notice</h1>
          <img src="javascript:alert(1)" alt="script">
          <img src="data:text/html,boom" alt="data">
        </main>
        """,
        "https://finki.ukim.mk/notice/",
    )

    assert "javascript:" not in document.markdown
    assert "data:text/html" not in document.markdown


def test_document_from_page_keeps_encoded_html_inert() -> None:
    document = document_from_page(
        "<main><h1>Notice</h1><p>&lt;script&gt;alert(1)&lt;/script&gt;</p></main>",
        "https://finki.ukim.mk/notice/",
    )

    assert "<script>" not in document.markdown
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in document.markdown


def test_document_from_page_preserves_all_articles_in_main() -> None:
    document = document_from_page(
        """
        <main><h1>News</h1>
          <article><h2>First</h2><p>First story.</p></article>
          <article><h2>Second</h2><p>Second story.</p></article>
        </main>
        """,
        "https://finki.ukim.mk/news/",
    )

    assert "First story." in document.markdown
    assert "Second story." in document.markdown


def test_document_from_page_removes_shared_sidebar_and_uses_specific_title() -> None:
    document = document_from_page(
        """
        <main><h1>Subject</h1>
          <section class="sidebar-events hide-on-mobile">
            <h2>Events</h2><p>Shared event.</p>
          </section>
          <section><h1>Data Processing</h1><p>Course details.</p></section>
          <section class="quick-icons"><a href="/office/">Dean's Office</a></section>
        </main>
        """,
        "https://finki.ukim.mk/en/subject/BI-I-02/",
    )

    assert document.title == "Data Processing"
    assert "Course details." in document.markdown
    assert "Shared event." not in document.markdown
    assert "Dean's Office" not in document.markdown


def test_document_from_rest_prefers_content_and_decodes_title() -> None:
    record = RestRecord.model_validate(
        {
            "id": 42,
            "link": "https://finki.ukim.mk/announcement/example/",
            "modified": "2026-08-31T10:30:00",
            "slug": "example",
            "title": {"rendered": "Research &amp; teaching"},
            "content": {"rendered": "<p>Official <strong>details</strong>.</p>"},
            "excerpt": {"rendered": "<p>Summary</p>"},
            "type": "announcement",
        }
    )

    document = document_from_rest(record)

    assert document.title == "Research & teaching"
    assert document.markdown == "Official **details**."
    assert document.wordpress_id == 42
    assert document.source_kind is SourceKind.REST


def test_document_from_rest_uses_excerpt_when_content_cleans_to_empty() -> None:
    record = RestRecord.model_validate(
        {
            "id": 43,
            "link": "https://finki.ukim.mk/announcement/summary/",
            "slug": "summary",
            "title": {"rendered": "Summary"},
            "content": {"rendered": "<script>ignored()</script>"},
            "excerpt": {"rendered": "<p>Useful summary.</p>"},
            "type": "announcement",
        }
    )

    document = document_from_rest(record)

    assert document.markdown == "Useful summary."


def test_render_document_records_source_provenance() -> None:
    record = RestRecord.model_validate(
        {
            "id": 42,
            "link": "https://finki.ukim.mk/announcement/example/",
            "slug": "example",
            "title": {"rendered": "Notice"},
            "content": {"rendered": "<p>Details</p>"},
            "type": "announcement",
        }
    )

    rendered = render_document(document_from_rest(record))

    assert rendered.startswith("<!-- finki-website-source\n")
    assert "url: https://finki.ukim.mk/announcement/example/" in rendered
    assert "source_kind: rest" in rendered
    assert rendered.endswith("# Notice\n\nDetails\n")


def test_render_document_escapes_untrusted_metadata_and_title() -> None:
    record = RestRecord.model_validate(
        {
            "id": 44,
            "link": "https://finki.ukim.mk/announcement/unsafe/",
            "modified": "today\n-->\n<script>alert(1)</script>",
            "slug": "unsafe",
            "title": {"rendered": "<script>alert(1)</script>"},
            "content": {"rendered": "<p>Safe body.</p>"},
            "type": "announcement",
        }
    )

    rendered = render_document(document_from_rest(record))

    assert rendered.count("-->") == 1
    assert "<script>" not in rendered


def test_document_from_rest_strips_title_whitespace() -> None:
    record = RestRecord.model_validate(
        {
            "id": 7,
            "link": "https://finki.ukim.mk/master-program/BI23_1/",
            "slug": "BI23_1",
            "title": {"rendered": "Биоинформатика (BI23_1) \n"},
            "content": {"rendered": "<p>Programme details.</p>"},
            "type": "pages",
        }
    )

    document = document_from_rest(record)
    rendered = render_document(document)

    assert document.title == "Биоинформатика (BI23_1)"
    assert all(line == line.rstrip() for line in rendered.splitlines())


def test_document_from_rest_uses_slug_for_blank_decoded_title() -> None:
    record = RestRecord.model_validate(
        {
            "id": 8,
            "link": "https://finki.ukim.mk/msmljk/",
            "slug": "msmljk",
            "title": {"rendered": "&nbsp;"},
            "content": {"rendered": "<p>Programme details.</p>"},
            "type": "page",
        }
    )

    document = document_from_rest(record)

    assert document.title == "msmljk"
    assert "# msmljk\n" in render_document(document)


def test_render_document_neutralizes_markdown_syntax_from_untrusted_text() -> None:
    document = WebsiteDocument(
        aliases=(),
        language="mk",
        markdown="[click](javascript:alert(1))",
        modified=None,
        source_kind=SourceKind.RENDERED,
        title="![track](https://example.invalid/pixel)",
        url="https://finki.ukim.mk/notice/",
        wordpress_id=None,
        wordpress_type=None,
    )

    rendered = render_document(document)

    assert "[click](javascript:" not in rendered
    assert "![track](" not in rendered
    assert "click" in rendered
    assert "track" in rendered


def test_document_from_page_neutralizes_reference_link_definitions() -> None:
    document = document_from_page(
        (
            "<main><h1>Notice</h1><p>[click][target]</p>"
            "<p>[target]: javascript:alert(1)</p></main>"
        ),
        "https://finki.ukim.mk/notice/",
    )

    rendered = render_document(document)

    assert "\n[target]: javascript:" not in rendered
    assert "\n\\[target]: javascript:" in rendered
    assert "click" in rendered


def test_document_from_page_neutralizes_escaped_reference_labels() -> None:
    document = document_from_page(
        (
            "<main><h1>Notice</h1><p>[click][a\\]b]</p>"
            "<p>[a\\]b]: javascript:alert(1)</p></main>"
        ),
        "https://finki.ukim.mk/notice/",
    )

    rendered = render_document(document)

    assert "\n[a\\]b]: javascript:" not in rendered
    assert "\n\\[a\\]b]: javascript:" in rendered


def test_render_document_neutralizes_escaped_inline_link_labels() -> None:
    document = WebsiteDocument(
        aliases=(),
        language="mk",
        markdown="[a\\]b](javascript:alert(1))",
        modified=None,
        source_kind=SourceKind.RENDERED,
        title="Notice",
        url="https://finki.ukim.mk/notice/",
        wordpress_id=None,
        wordpress_type=None,
    )

    rendered = render_document(document)

    assert "javascript:" not in rendered
    assert "a\\]b" in rendered


def test_render_document_normalizes_controls_before_scheme_check() -> None:
    document = WebsiteDocument(
        aliases=(),
        language="mk",
        markdown="[click](jav&#x09;ascript:alert(1))",
        modified=None,
        source_kind=SourceKind.RENDERED,
        title="Notice",
        url="https://finki.ukim.mk/notice/",
        wordpress_id=None,
        wordpress_type=None,
    )

    rendered = render_document(document)

    assert "javascript:" not in rendered.replace("&#x09;", "")


def test_render_document_normalizes_commonmark_escapes_before_scheme_check() -> None:
    document = WebsiteDocument(
        aliases=(),
        language="mk",
        markdown="[click](javascript\\:alert(1)) ![image](data\\:image/png;base64,x)",
        modified=None,
        source_kind=SourceKind.RENDERED,
        title="Notice",
        url="https://finki.ukim.mk/notice/",
        wordpress_id=None,
        wordpress_type=None,
    )

    rendered = render_document(document)

    assert "javascript\\:" not in rendered
    assert "data\\:" not in rendered


def test_render_document_neutralizes_malformed_link_destination() -> None:
    document = WebsiteDocument(
        aliases=(),
        language="mk",
        markdown="[click](http://[)",
        modified=None,
        source_kind=SourceKind.RENDERED,
        title="Notice",
        url="https://finki.ukim.mk/notice/",
        wordpress_id=None,
        wordpress_type=None,
    )

    assert "http://[" not in render_document(document)


def test_render_document_sanitizes_many_unsafe_links_within_resource_budget() -> None:
    document = WebsiteDocument(
        aliases=(),
        language="mk",
        markdown="[click](javascript:run) " * 80_000,
        modified=None,
        source_kind=SourceKind.RENDERED,
        title="Notice",
        url="https://finki.ukim.mk/notice/",
        wordpress_id=None,
        wordpress_type=None,
    )

    started = perf_counter()
    rendered = render_document(document)

    assert perf_counter() - started < 5
    assert "javascript:" not in rendered


def test_render_document_bounds_nested_destination_inspection() -> None:
    nested = "[x](" * 8_000 + "javascript:run" + ")" * 8_000
    document = WebsiteDocument(
        aliases=(),
        language="mk",
        markdown=nested,
        modified=None,
        source_kind=SourceKind.RENDERED,
        title="Notice",
        url="https://finki.ukim.mk/notice/",
        wordpress_id=None,
        wordpress_type=None,
    )

    started = perf_counter()
    rendered = render_document(document)

    assert perf_counter() - started < 5
    assert "javascript:" not in rendered


def test_render_document_handles_many_unmatched_brackets() -> None:
    document = WebsiteDocument(
        aliases=(),
        language="mk",
        markdown="[" * 20_000,
        modified=None,
        source_kind=SourceKind.RENDERED,
        title="Notice",
        url="https://finki.ukim.mk/notice/",
        wordpress_id=None,
        wordpress_type=None,
    )

    assert render_document(document).endswith(f"{'[' * 20_000}\n")


def test_render_document_neutralizes_multiline_reference_labels() -> None:
    document = WebsiteDocument(
        aliases=(),
        language="mk",
        markdown="[click][a\nb]\n\n[a\nb]: javascript:alert(1)",
        modified=None,
        source_kind=SourceKind.RENDERED,
        title="Notice",
        url="https://finki.ukim.mk/notice/",
        wordpress_id=None,
        wordpress_type=None,
    )

    rendered = render_document(document)

    assert "\n[a\nb]: javascript:" not in rendered
    assert "\n\\[a\nb]: javascript:" in rendered


def test_document_from_page_neutralizes_markdown_fences() -> None:
    document = document_from_page(
        "<main><h1>Notice</h1><p>```</p><p>following text</p></main>",
        "https://finki.ukim.mk/notice/",
    )

    rendered = render_document(document)

    assert not any(line.startswith("```") for line in rendered.splitlines())
    assert "following text" in rendered
