from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tools.website_models import (
    GenerationMetadata,
    SourceKind,
    WebsiteDocument,
    WebsiteManifest,
)
from tools.website_output import OutputSafetyError, write_output


def _document(title: str = "Notice") -> WebsiteDocument:
    return WebsiteDocument(
        aliases=(),
        language="mk",
        markdown=f"Content for {title}.",
        modified=None,
        source_kind=SourceKind.RENDERED,
        title=title,
        url=f"https://finki.ukim.mk/{title.casefold()}/",
        wordpress_id=None,
        wordpress_type=None,
    )


def test_manifest_requires_explicit_ownership_fields() -> None:
    with pytest.raises(ValidationError):
        _ = WebsiteManifest.model_validate_json(
            '{"base_url":"https://finki.ukim.mk/","document_count":0,"documents":[],"rest_totals":{}}'
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

    with pytest.raises(OutputSafetyError, match="ownership manifest"):
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


@pytest.mark.parametrize(
    "output_dir",
    [
        Path("raw"),
        Path("raw/website-contract-probe"),
        Path("processed"),
        Path("processed/website-contract-probe"),
    ],
)
def test_write_output_rejects_corpus_directories(output_dir: Path) -> None:
    with pytest.raises(OutputSafetyError, match="protected path"):
        write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))


def test_successful_replacement_preserves_previous_snapshot(tmp_path: Path) -> None:
    output_dir = tmp_path / "website"
    write_output(
        output_dir, [_document("Original")], GenerationMetadata(rest_totals={})
    )

    write_output(
        output_dir,
        [_document("Replacement")],
        GenerationMetadata(rest_totals={}),
    )

    recovery = next(tmp_path.glob(".website-recovery-*"))
    previous = (recovery / "previous" / "finki-website.md").read_text(encoding="utf-8")
    assert "# Original" in previous
    assert "# Replacement" in (output_dir / "finki-website.md").read_text(
        encoding="utf-8"
    )


def test_failed_initial_install_preserves_staging_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "website"
    original_rename = Path.rename

    def fail_install(path: Path, target: str | Path) -> Path:
        if Path(target) == output_dir:
            raise OSError("injected install failure")
        return original_rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_install)

    with pytest.raises(OSError, match="injected install failure"):
        write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))

    staging = next(tmp_path.glob(".website-*"))
    assert (staging / "manifest.json").is_file()
