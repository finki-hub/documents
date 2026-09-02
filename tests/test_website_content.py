from __future__ import annotations

from pathlib import Path

from tools.website_content import write_output
from tools.website_models import SourceKind, WebsiteDocument, WebsiteManifest


def _document(url: str, title: str, language: str) -> WebsiteDocument:
    return WebsiteDocument(
        aliases=(),
        language=language,
        markdown=f"Content for {title}.",
        modified=None,
        source_kind=SourceKind.RENDERED,
        title=title,
        url=url,
        wordpress_id=None,
        wordpress_type=None,
    )


def test_write_output_replaces_stale_files_and_is_deterministic(tmp_path: Path) -> None:
    output_dir = tmp_path / "website"
    documents = (
        _document("https://finki.ukim.mk/en/about/", "About", "en"),
        _document("https://finki.ukim.mk/kadar/", "Кадар", "mk"),
    )

    write_output(output_dir, documents, {"pages": 2})
    first_manifest = (output_dir / "manifest.json").read_bytes()
    _ = (output_dir / "documents" / "stale.md").write_text(
        "stale", encoding="utf-8"
    )
    write_output(output_dir, reversed(documents), {"pages": 2})

    manifest = WebsiteManifest.model_validate_json(
        (output_dir / "manifest.json").read_bytes()
    )
    assert (output_dir / "manifest.json").read_bytes() == first_manifest
    assert manifest.document_count == 2
    assert [entry.language for entry in manifest.documents] == ["en", "mk"]
    assert not (output_dir / "documents" / "stale.md").exists()
    combined = (output_dir / "finki-website.md").read_text(encoding="utf-8")
    assert "# About" in combined
    assert "# Кадар" in combined


def test_write_output_bounds_filenames_for_long_canonical_urls(tmp_path: Path) -> None:
    output_dir = tmp_path / "website"
    document = _document(
        f"https://finki.ukim.mk/announcements/{'long-announcement-' * 20}/",
        "Long announcement",
        "mk",
    )

    write_output(output_dir, [document], {})

    generated = next((output_dir / "documents" / "mk").iterdir())
    assert len(generated.name) <= 100
