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


def test_write_output_does_not_remove_recreated_staging_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "website"
    original_rename = os.rename
    recreated_staging: list[Path] = []

    def recreate_staging_after_install(
        source: str | Path,
        destination: str | Path,
    ) -> None:
        original_rename(source, destination)
        source_path = Path(source)
        if Path(destination) == output_dir and "-recovery-" not in source_path.name:
            source_path.mkdir()
            _ = (source_path / "keep.txt").write_text("foreign", encoding="utf-8")
            recreated_staging.append(source_path)

    monkeypatch.setattr(os, "rename", recreate_staging_after_install)

    write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))

    assert len(recreated_staging) == 1
    assert (recreated_staging[0] / "keep.txt").read_text(encoding="utf-8") == "foreign"


def test_write_output_rejects_same_directory_content_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "website"
    output_dir.mkdir()
    sentinel = output_dir / "keep.txt"

    def mutate_output_during_render(document: WebsiteDocument) -> str:
        _ = sentinel.write_text("foreign", encoding="utf-8")
        return render_document(document)

    monkeypatch.setattr(website_output, "render_document", mutate_output_during_render)

    with pytest.raises(OutputSafetyError, match="changed during generation"):
        write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))

    assert sentinel.read_text(encoding="utf-8") == "foreign"


def test_write_output_preserves_mismatched_tree_when_rollback_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "website"
    write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))
    original_rename = os.rename
    owner_backup = tmp_path / "owner-backup"

    def fail_mismatch_rollback(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        if source_path == output_dir and destination_path.name == "previous":
            original_rename(output_dir, owner_backup)
            output_dir.mkdir()
            _ = (output_dir / "foreign.txt").write_text("foreign", encoding="utf-8")
            original_rename(output_dir, destination_path)
            return
        if source_path.name == "previous" and destination_path == output_dir:
            raise OSError("injected mismatch rollback failure")
        original_rename(source, destination)

    monkeypatch.setattr(os, "rename", fail_mismatch_rollback)

    with pytest.raises(OSError, match="injected mismatch rollback failure"):
        write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))

    recovery_directories = tuple(tmp_path.glob(".website-recovery-*"))
    assert len(recovery_directories) == 1
    assert (recovery_directories[0] / "previous" / "foreign.txt").read_text(
        encoding="utf-8"
    ) == "foreign"


def test_write_output_rejects_substituted_staging_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "website"
    victim = tmp_path / "victim.txt"
    _ = victim.write_text("keep", encoding="utf-8")

    def substitute_staging(document: WebsiteDocument) -> str:
        staging = next(tmp_path.glob(".website-*"))
        _ = staging.rename(tmp_path / "displaced-staging")
        (staging / "documents" / "mk").mkdir(parents=True)
        try:
            (staging / "manifest.json").symlink_to(victim)
        except OSError:
            pytest.skip("symlinks are unavailable on this runner")
        return render_document(document)

    monkeypatch.setattr(website_output, "render_document", substitute_staging)

    with pytest.raises(OSError):
        write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))

    assert victim.read_text(encoding="utf-8") == "keep"


def test_write_output_rejects_staging_substitution_after_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "website"
    displaced = tmp_path / "displaced-staging"
    original_rename = os.rename
    substituted = False

    def substitute_during_install(
        source: str | Path,
        destination: str | Path,
    ) -> None:
        nonlocal substituted
        source_path = Path(source)
        if not substituted and Path(destination) == output_dir:
            substituted = True
            original_rename(source_path, displaced)
            source_path.mkdir()
            _ = (source_path / "foreign.txt").write_text("foreign", encoding="utf-8")
        original_rename(source_path, destination)

    monkeypatch.setattr(os, "rename", substitute_during_install)

    with pytest.raises(OutputSafetyError, match="staging"):
        write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))

    assert not output_dir.exists()
    assert (displaced / "manifest.json").is_file()
    recovery = next(tmp_path.glob(".website-recovery-*"))
    assert (recovery / "rejected" / "foreign.txt").read_text(encoding="utf-8") == (
        "foreign"
    )
