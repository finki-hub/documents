from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

import anyio
import httpx2
import pytest

from tools import website_content
from tools.website_models import (
    CrawlPlan,
    CrawlResult,
    GenerationMetadata,
    PageSnapshot,
    RestInventory,
    RestRecord,
    SourceKind,
    WebsiteDocument,
    WebsiteManifest,
)
from tools.website_output import write_output


def _path_at(path: str | Path, directory_descriptor: int | None) -> Path:
    candidate = Path(path)
    if directory_descriptor is None or candidate.is_absolute():
        return candidate
    return Path(os.readlink(f"/proc/self/fd/{directory_descriptor}")) / candidate


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
    original_rename = os.rename
    failed = False

    def fail_snapshot_swap_once(
        source: str | Path,
        destination: str | Path,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal failed
        if not failed and _path_at(destination, dst_dir_fd) == output_dir:
            failed = True
            raise OSError("injected install failure")
        original_rename(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(os, "rename", fail_snapshot_swap_once)

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


def test_update_website_prefers_rendered_page_over_empty_rest_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://finki.ukim.mk/notice/"
    record = RestRecord.model_validate(
        {
            "id": 42,
            "link": url,
            "slug": "notice",
            "title": {"rendered": "REST title"},
            "content": {"rendered": ""},
            "excerpt": {"rendered": "<p>REST fallback.</p>"},
            "type": "page",
        }
    )
    captured: list[WebsiteDocument] = []

    async def fake_inventory(_client: httpx2.AsyncClient) -> RestInventory:
        return RestInventory(records_by_url={url: record}, totals={"pages": 1})

    async def fake_crawl(
        _client: httpx2.AsyncClient,
        plan: CrawlPlan,
    ) -> CrawlResult:
        assert url in plan.seed_urls
        return CrawlResult(
            pages=(
                PageSnapshot(
                    final_url=url,
                    html="<main><h1>Rendered title</h1><p>Rendered body.</p></main>",
                    links=(),
                    requested_url=url,
                    status=200,
                ),
            ),
            requested_count=1,
            truncated=False,
        )

    def capture_output(
        _output_dir: Path,
        documents: Iterable[WebsiteDocument],
        _metadata: GenerationMetadata,
    ) -> None:
        captured.extend(documents)

    monkeypatch.setattr(website_content, "fetch_rest_inventory", fake_inventory)
    monkeypatch.setattr(website_content, "crawl_pages", fake_crawl)
    monkeypatch.setattr(website_content, "write_output", capture_output)

    result = anyio.run(website_content.update_website, tmp_path / "website", 10)

    assert result.document_count == 1
    assert len(captured) == 1
    assert captured[0].source_kind is SourceKind.RENDERED
    assert captured[0].markdown == "Rendered body."
