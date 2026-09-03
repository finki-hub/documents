from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools import website_output
from tools.website_markdown import render_document
from tools.website_models import (
    GenerationMetadata,
    SourceKind,
    WebsiteDocument,
    WebsiteManifest,
)
from tools.website_output import OutputSafetyError, write_output


def _document() -> WebsiteDocument:
    return WebsiteDocument(
        aliases=(),
        language="mk",
        markdown="Content.",
        modified=None,
        source_kind=SourceKind.RENDERED,
        title="Notice",
        url="https://finki.ukim.mk/notice/",
        wordpress_id=None,
        wordpress_type=None,
    )


def test_manifest_requires_explicit_ownership_fields() -> None:
    with pytest.raises(ValidationError):
        _ = WebsiteManifest.model_validate_json(
            '{"base_url":"https://finki.ukim.mk/","document_count":0,'
            + '"documents":[],"rest_totals":{}}'
        )


def test_write_output_rejects_manifest_without_ownership_fields(tmp_path: Path) -> None:
    output_dir = tmp_path / "foreign"
    output_dir.mkdir()
    sentinel = output_dir / "keep.txt"
    _ = sentinel.write_text("do not delete", encoding="utf-8")
    _ = (output_dir / "manifest.json").write_text(
        json.dumps(
            {
                "base_url": "https://finki.ukim.mk/",
                "document_count": 0,
                "documents": [],
                "rest_totals": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(OutputSafetyError):
        write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))

    assert sentinel.read_text(encoding="utf-8") == "do not delete"


def test_write_output_rejects_current_directory_spelled_with_dot_dot() -> None:
    disguised_current = Path.cwd() / "missing-child" / ".."

    with pytest.raises(OutputSafetyError, match="protected path"):
        write_output(
            disguised_current,
            [_document()],
            GenerationMetadata(rest_totals={}),
        )


def test_write_output_detects_output_replacement_after_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "website"
    sentinel = output_dir / "keep.txt"

    def replace_output_during_render(document: WebsiteDocument) -> str:
        output_dir.mkdir()
        _ = sentinel.write_text("do not delete", encoding="utf-8")
        return render_document(document)

    monkeypatch.setattr(
        website_output,
        "render_document",
        replace_output_during_render,
    )

    with pytest.raises(OutputSafetyError, match="changed during generation"):
        write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))

    assert sentinel.read_text(encoding="utf-8") == "do not delete"


def test_write_output_preserves_recovery_when_rollback_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "website"
    write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))
    original_rename = os.rename

    def fail_install_and_rollback(source: str | Path, destination: str | Path) -> None:
        if Path(destination) == output_dir:
            raise OSError("injected rename failure")
        original_rename(source, destination)

    monkeypatch.setattr(os, "rename", fail_install_and_rollback)

    with pytest.raises(OSError, match="injected rename failure"):
        write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))

    recovery_directories = tuple(tmp_path.glob(".website-recovery-*"))
    assert len(recovery_directories) == 1
    assert (recovery_directories[0] / "previous" / "manifest.json").is_file()
