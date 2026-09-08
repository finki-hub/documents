from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

from tools import rag_corpus_bundle as bundle_module
from tools.rag_corpus_bundle import (
    BundleValidationError,
    _main,
    _source_tree_sha256,
    build_bundle,
    bundle_sha256,
    serialize_bundle,
)

ROOT = Path(__file__).parents[1]


def _source_tree(tmp_path: Path) -> Path:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is unavailable")
    shutil.copytree(ROOT / "processed", tmp_path / "processed")
    shutil.copytree(ROOT / "raw", tmp_path / "raw")
    website = tmp_path / "website-reference"
    website.mkdir()
    shutil.copy2(
        ROOT / "website-reference" / "finki-static-pages.md",
        website / "finki-static-pages.md",
    )
    subprocess.run([git, "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(
        [git, "config", "user.email", "test@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run([git, "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(
        [git, "add", "processed", "raw", "website-reference"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        [git, "commit", "--quiet", "-m", "fixture"], cwd=tmp_path, check=True
    )
    return tmp_path


def test_fast_path_rejects_an_untracked_discovered_document(tmp_path: Path) -> None:
    root = _source_tree(tmp_path)
    original = (root / "processed" / "partnerstvo-industrija.md").read_text(
        encoding="utf-8"
    )
    (root / "processed" / "newly-reviewed-document.md").write_text(
        original, encoding="utf-8"
    )

    with pytest.raises(BundleValidationError, match="tracked|HEAD"):
        build_bundle(root)


def test_fast_path_rejects_a_modified_discovered_document(tmp_path: Path) -> None:
    root = _source_tree(tmp_path)
    document = root / "processed" / "partnerstvo-industrija.md"
    document.write_text(document.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(BundleValidationError, match="tracked at HEAD|match HEAD"):
        build_bundle(root)


def test_fast_path_rejects_an_ignored_discovered_document(tmp_path: Path) -> None:
    root = _source_tree(tmp_path)
    git = shutil.which("git")
    assert git is not None
    (root / ".gitignore").write_text("processed/ignored.md\n", encoding="utf-8")
    subprocess.run([git, "add", ".gitignore"], cwd=root, check=True)
    subprocess.run(
        [git, "commit", "--quiet", "-m", "ignore-rule"], cwd=root, check=True
    )
    shutil.copy2(
        root / "processed" / "partnerstvo-industrija.md",
        root / "processed" / "ignored.md",
    )

    with pytest.raises(BundleValidationError, match="tracked at HEAD|clean|HEAD"):
        build_bundle(root)


def test_fast_path_rejects_a_missing_head_corpus_file(tmp_path: Path) -> None:
    root = _source_tree(tmp_path)
    (root / "processed" / "partnerstvo-industrija.md").unlink()

    with pytest.raises(BundleValidationError, match="HEAD|inventory|incomplete"):
        build_bundle(root)


def test_fast_path_rejects_skip_worktree_content_that_differs_from_head(
    tmp_path: Path,
) -> None:
    root = _source_tree(tmp_path)
    git = shutil.which("git")
    assert git is not None
    relative = "processed/partnerstvo-industrija.md"
    subprocess.run(
        [git, "update-index", "--skip-worktree", relative], cwd=root, check=True
    )
    document = root / relative
    document.write_text(document.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(BundleValidationError, match="match HEAD|tracked"):
        build_bundle(root)


def test_fast_path_exports_pages_without_allowlist_or_wall_clock_filter(
    tmp_path: Path,
) -> None:
    root = _source_tree(tmp_path)
    bundle = build_bundle(root)

    assert any(entry.name.startswith("website/") for entry in bundle.entries)


def test_fast_path_requires_raw_directory_and_provenance_files(tmp_path: Path) -> None:
    root = _source_tree(tmp_path)
    shutil.rmtree(root / "raw")

    with pytest.raises(BundleValidationError, match="raw"):
        build_bundle(root)


def test_fast_path_rejects_traversal_raw_provenance(tmp_path: Path) -> None:
    root = _source_tree(tmp_path)
    (root / "outside.pdf").write_bytes(b"external")
    document = root / "processed" / "partnerstvo-industrija.md"
    content = document.read_text(encoding="utf-8")
    document.write_text(
        content.replace(
            "source: Partnerstvo-industrija.docx", "source: ../outside.pdf"
        ),
        encoding="utf-8",
    )

    with pytest.raises(BundleValidationError, match="raw|traversal|external"):
        build_bundle(root)


def test_fast_path_rejects_missing_raw_provenance(tmp_path: Path) -> None:
    root = _source_tree(tmp_path)
    document = root / "processed" / "partnerstvo-industrija.md"
    content = document.read_text(encoding="utf-8")
    document.write_text(
        content.replace("source: Partnerstvo-industrija.docx", "source: missing.pdf"),
        encoding="utf-8",
    )

    with pytest.raises(BundleValidationError, match="raw|tracked|HEAD"):
        build_bundle(root)


def test_fast_path_rejects_absolute_raw_provenance(tmp_path: Path) -> None:
    root = _source_tree(tmp_path)
    outside = tmp_path / "absolute.pdf"
    outside.write_bytes(b"external")
    document = root / "processed" / "partnerstvo-industrija.md"
    content = document.read_text(encoding="utf-8")
    document.write_text(
        content.replace("source: Partnerstvo-industrija.docx", f"source: {outside}"),
        encoding="utf-8",
    )

    with pytest.raises(BundleValidationError, match="raw|absolute|external"):
        build_bundle(root)


def test_fast_path_rejects_symlinked_raw_provenance(tmp_path: Path) -> None:
    root = _source_tree(tmp_path)
    raw_file = root / "raw" / "Partnerstvo-industrija.docx"
    target = tmp_path / "external.docx"
    target.write_bytes(raw_file.read_bytes())
    raw_file.unlink()
    try:
        raw_file.symlink_to(target)
    except OSError:
        pytest.skip("file symlinks are unavailable on this platform")

    with pytest.raises(BundleValidationError, match="raw|symlink|tracked"):
        build_bundle(root)


def test_fast_path_rejects_symlinked_corpus_input(tmp_path: Path) -> None:
    root = _source_tree(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text(
        (root / "processed" / "partnerstvo-industrija.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    linked = root / "processed" / "linked.md"
    try:
        linked.symlink_to(outside)
    except OSError:
        pytest.skip("file symlinks are unavailable on this platform")

    with pytest.raises(BundleValidationError, match="symlink|confine|tracked"):
        build_bundle(root)


def test_fast_path_rejects_symlinked_website_input(tmp_path: Path) -> None:
    root = _source_tree(tmp_path)
    website = root / "website-reference"
    real_website = root / "website-reference-real"
    website.rename(real_website)
    try:
        website.symlink_to(real_website, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this platform")

    with pytest.raises(BundleValidationError, match="symlink|confine"):
        build_bundle(root)


def test_raw_provenance_contributes_to_source_tree_digest(tmp_path: Path) -> None:
    root = _source_tree(tmp_path)
    before = _source_tree_sha256(root)
    raw_file = root / "raw" / "Partnerstvo-industrija.docx"
    raw_file.write_bytes(raw_file.read_bytes() + b"\n")

    assert _source_tree_sha256(root) != before


def test_release_export_requires_whole_repository_cleanliness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _source_tree(tmp_path)
    monkeypatch.setattr(
        bundle_module, "_git_worktree_status", lambda _: " M tools/not-corpus.py\n"
    )

    with pytest.raises(BundleValidationError, match="clean"):
        _main(["--release", "--repo-root", str(root)])


def test_bundle_checksum_is_the_hash_of_exact_canonical_json(tmp_path: Path) -> None:
    root = _source_tree(tmp_path)
    bundle = build_bundle(root)
    encoded = serialize_bundle(bundle)

    assert bundle_sha256(encoded) == hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    assert encoded == serialize_bundle(bundle)


def test_release_cli_emits_bundle_on_stdout_and_checksum_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _source_tree(tmp_path)

    assert _main(["--release", "--repo-root", str(root)]) == 0
    captured = capsys.readouterr()

    assert captured.out.endswith("\n")
    assert captured.out.startswith('{"entries":')
    assert "bundle_sha256=" not in captured.out
    assert f"bundle_sha256={bundle_sha256(captured.out)}" in captured.err
