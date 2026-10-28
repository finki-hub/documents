from __future__ import annotations

from datetime import date
from hashlib import sha256
from pathlib import Path

import pytest

from tools import website_reference
from tools.website_reference import (
    load_sources,
    main,
    parse_aggregate,
    validate_reference_body,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("option", ["--sources", "--aggregate"])
@pytest.mark.parametrize("path_kind", ["parent", "outside", "prefix-sibling"])
def test_reference_cli_rejects_paths_outside_project_before_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    option: str,
    path_kind: str,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(website_reference, "_PROJECT_ROOT", project)
    monkeypatch.chdir(project)
    paths = {
        "parent": Path("..") / "secret.toml",
        "outside": tmp_path / "secret.toml",
        "prefix-sibling": tmp_path / "project-other" / "secret.toml",
    }

    def unexpected_read(_path: Path, *, today: date) -> tuple[()]:
        pytest.fail(f"unexpected read on {today}")

    monkeypatch.setattr(website_reference, "load_sources", unexpected_read)
    argv = ["--check", option, str(paths[path_kind])]
    with pytest.raises(ValueError, match="parent traversal|within the project"):
        main(argv)


def _copy_reference(project: Path) -> None:
    reference = project / "website-reference"
    reference.mkdir()
    for filename in ("sources.toml", "finki-static-pages.md"):
        (reference / filename).write_bytes(
            (ROOT / "website-reference" / filename).read_bytes()
        )


def test_reference_cli_accepts_offline_files_in_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_reference(tmp_path)
    monkeypatch.setattr(website_reference, "_PROJECT_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(["--check"]) == 0


def test_reference_cli_preserves_lf_only_validation_with_safe_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_reference(tmp_path)
    aggregate = tmp_path / "website-reference" / "finki-static-pages.md"
    aggregate.write_bytes(aggregate.read_bytes().replace(b"\n", b"\r\n"))
    monkeypatch.setattr(website_reference, "_PROJECT_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="LF-only"):
        main(["--check"])


def test_reference_cli_preserves_quality_validation_with_safe_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy_reference(tmp_path)
    aggregate = tmp_path / "website-reference" / "finki-static-pages.md"
    text = aggregate.read_text(encoding="utf-8")
    first_page = parse_aggregate(text)[0]
    body = "Home\nHome\nHome"
    digest = sha256(f"{first_page.title}\n\n{body}".encode()).hexdigest()
    text = text.replace(first_page.body, body, 1).replace(
        first_page.content_sha256, digest, 1
    )
    aggregate.write_text(text, encoding="utf-8", newline="\n")
    monkeypatch.setattr(website_reference, "_PROJECT_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="navigation|empty"):
        main(["--check"])


def test_reference_source_loader_rejects_parent_traversal(tmp_path: Path) -> None:
    path = tmp_path / ".." / "secret.toml"
    today = date(2026, 10, 28)
    with pytest.raises(ValueError, match="parent traversal"):
        load_sources(path, today=today)


def test_reference_source_loader_rejects_non_regular_input(tmp_path: Path) -> None:
    today = date(2026, 10, 28)
    with pytest.raises(ValueError, match="regular file"):
        load_sources(tmp_path, today=today)


@pytest.mark.parametrize("directory_link", [False, True])
def test_reference_source_loader_rejects_symlink_paths(
    tmp_path: Path, directory_link: bool
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    source = target / "sources.toml"
    source.write_text("version = 2", encoding="utf-8")
    link = tmp_path / "linked"
    try:
        link.symlink_to(
            target if directory_link else source, target_is_directory=directory_link
        )
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")
    path = link / "sources.toml" if directory_link else link
    today = date(2026, 10, 28)
    with pytest.raises(ValueError, match="symlinks or junctions"):
        load_sources(path, today=today)


def test_reference_heading_validation_handles_long_whitespace_without_backtracking() -> (
    None
):
    heading = "#" + "\t" * 200_000 + "A" * 200
    with pytest.raises(ValueError, match="markup-only"):
        validate_reference_body(heading, "heading-only", content_kind="prose")


def test_reference_cli_rejects_symlink_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = project / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")
    monkeypatch.setattr(website_reference, "_PROJECT_ROOT", project)
    monkeypatch.chdir(project)
    argv = ["--check", "--sources", str(link / "sources.toml")]
    with pytest.raises(ValueError, match="within the project|symlinks or junctions"):
        main(argv)
