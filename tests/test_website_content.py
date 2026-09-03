from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools.website_models import (
    GenerationMetadata,
    SourceKind,
    WebsiteDocument,
    WebsiteManifest,
)
from tools.website_output import write_output


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

    metadata = GenerationMetadata(rest_totals={"pages": 2})
    write_output(output_dir, documents, metadata)
    first_manifest = (output_dir / "manifest.json").read_bytes()
    _ = (output_dir / "documents" / "stale.md").write_text("stale", encoding="utf-8")
    write_output(output_dir, reversed(documents), metadata)

    manifest = WebsiteManifest.model_validate_json(
        (output_dir / "manifest.json").read_bytes()
    )
    assert (output_dir / "manifest.json").read_bytes() == first_manifest
    assert manifest.document_count == 2
    assert manifest.generator == "finki-website-content"
    assert manifest.crawled_pages == 0
    assert manifest.crawl_truncated is False
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

    write_output(output_dir, [document], GenerationMetadata(rest_totals={}))

    generated = next((output_dir / "documents" / "mk").iterdir())
    assert len(generated.name) <= 100


def test_write_output_rejects_nonempty_foreign_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "foreign"
    output_dir.mkdir()
    sentinel = output_dir / "keep.txt"
    _ = sentinel.write_text("do not delete", encoding="utf-8")

    with pytest.raises(RuntimeError):
        write_output(
            output_dir,
            [_document("https://finki.ukim.mk/notice/", "Notice", "mk")],
            GenerationMetadata(rest_totals={}),
        )

    assert sentinel.read_text(encoding="utf-8") == "do not delete"


def test_write_output_restores_owned_snapshot_when_install_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "website"
    original_document = _document("https://finki.ukim.mk/original/", "Original", "mk")
    write_output(
        output_dir,
        [original_document],
        GenerationMetadata(rest_totals={}),
    )
    original_files = {
        path.relative_to(output_dir): path.read_bytes()
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    original_replace = os.replace
    failed = False

    def fail_manifest_once(source: str | Path, destination: str | Path) -> None:
        nonlocal failed
        if not failed and Path(destination).name == "manifest.json":
            failed = True
            raise OSError("injected install failure")
        original_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_manifest_once)

    with pytest.raises(OSError, match="injected install failure"):
        write_output(
            output_dir,
            [_document("https://finki.ukim.mk/replacement/", "Replacement", "en")],
            GenerationMetadata(rest_totals={}),
        )

    restored_files = {
        path.relative_to(output_dir): path.read_bytes()
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    assert restored_files == original_files


def test_write_output_rejects_symlink_inside_owned_snapshot(tmp_path: Path) -> None:
    output_dir = tmp_path / "website"
    write_output(
        output_dir,
        [_document("https://finki.ukim.mk/original/", "Original", "mk")],
        GenerationMetadata(rest_totals={}),
    )
    outside = tmp_path / "outside.txt"
    _ = outside.write_text("outside", encoding="utf-8")
    link = output_dir / "documents" / "outside-link.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are unavailable on this runner")

    with pytest.raises(RuntimeError):
        write_output(
            output_dir,
            [_document("https://finki.ukim.mk/replacement/", "Replacement", "en")],
            GenerationMetadata(rest_totals={}),
        )

    assert outside.read_text(encoding="utf-8") == "outside"


def test_write_output_records_truncated_crawl_status(tmp_path: Path) -> None:
    output_dir = tmp_path / "website"
    metadata = GenerationMetadata(
        crawled_pages=20,
        crawl_truncated=True,
        rest_totals={"pages": 3},
    )

    write_output(
        output_dir,
        [_document("https://finki.ukim.mk/notice/", "Notice", "mk")],
        metadata,
    )

    manifest = WebsiteManifest.model_validate_json(
        (output_dir / "manifest.json").read_bytes()
    )
    assert manifest.crawled_pages == 20
    assert manifest.crawl_truncated is True
