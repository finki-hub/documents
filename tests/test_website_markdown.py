from tools.website_markdown import (
    document_from_page,
    document_from_rest,
    render_document,
)
from tools.website_models import RestRecord, SourceKind


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


def test_document_from_page_removes_unsafe_link_targets() -> None:
    document = document_from_page(
        '<main><h1>Notice</h1><a href="javascript:alert(1)">click</a></main>',
        "https://finki.ukim.mk/notice/",
    )

    assert "javascript:" not in document.markdown
    assert "click" in document.markdown


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
