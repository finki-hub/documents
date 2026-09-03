from __future__ import annotations

import json
import os
import stat
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread

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
from tools.website_output_lock import publication_lock
from tools.website_output_paths import hold_directory, make_temporary_directory


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


def _path_at(path: str | Path, directory_descriptor: int | None) -> Path:
    candidate = Path(path)
    if directory_descriptor is None or candidate.is_absolute():
        return candidate
    return Path(os.readlink(f"/proc/self/fd/{directory_descriptor}")) / candidate


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

    def fail_install_and_rollback(
        source: str | Path,
        destination: str | Path,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        if _path_at(destination, dst_dir_fd) == output_dir:
            raise OSError("injected rename failure")
        original_rename(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

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
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        source_path = _path_at(source, src_dir_fd)
        destination_path = _path_at(destination, dst_dir_fd)
        original_rename(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )
        if destination_path == output_dir and "-recovery-" not in source_path.name:
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

    def fail_mismatch_rollback(
        source: str | Path,
        destination: str | Path,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        source_path = _path_at(source, src_dir_fd)
        destination_path = _path_at(destination, dst_dir_fd)
        if source_path == output_dir and destination_path.name == "previous":
            original_rename(output_dir, owner_backup)
            output_dir.mkdir()
            _ = (output_dir / "foreign.txt").write_text("foreign", encoding="utf-8")
            original_rename(output_dir, destination_path)
            return
        if source_path.name == "previous" and destination_path == output_dir:
            raise OSError("injected mismatch rollback failure")
        original_rename(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

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

    with pytest.raises(OutputSafetyError, match="staging"):
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
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal substituted
        source_path = _path_at(source, src_dir_fd)
        destination_path = _path_at(destination, dst_dir_fd)
        if not substituted and destination_path == output_dir:
            substituted = True
            original_rename(source_path, displaced)
            source_path.mkdir()
            _ = (source_path / "foreign.txt").write_text("foreign", encoding="utf-8")
        original_rename(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(os, "rename", substitute_during_install)

    with pytest.raises(OutputSafetyError, match="staging"):
        write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))

    assert not output_dir.exists()
    assert (displaced / "manifest.json").is_file()
    recovery = next(tmp_path.glob(".website-recovery-*"))
    assert (recovery / "rejected" / "foreign.txt").read_text(encoding="utf-8") == (
        "foreign"
    )


@pytest.mark.parametrize("existing_output", [False, True])
def test_write_output_does_not_quarantine_concurrent_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    existing_output: bool,
) -> None:
    output_dir = tmp_path / "website"
    winner_dir = tmp_path / "winner"
    if existing_output:
        write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))
    winner = replace(_document(), markdown="Winner.", title="Winner")
    write_output(winner_dir, [winner], GenerationMetadata(rest_totals={}))
    original_rename = os.rename
    published = False

    def publish_winner_first(
        source: str | Path,
        destination: str | Path,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal published
        if not published and _path_at(destination, dst_dir_fd) == output_dir:
            published = True
            original_rename(winner_dir, output_dir)
            raise FileExistsError("concurrent winner published")
        original_rename(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(os, "rename", publish_winner_first)

    with pytest.raises(FileExistsError, match="concurrent winner published"):
        write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))

    assert (output_dir / "manifest.json").is_file()
    assert "# Winner" in (output_dir / "finki-website.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("existing_output", [False, True])
def test_write_output_preserves_winner_published_after_staging_move(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    existing_output: bool,
) -> None:
    output_dir = tmp_path / "website"
    winner_dir = tmp_path / "winner"
    displaced = tmp_path / "displaced-install"
    if existing_output:
        write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))
    winner = replace(_document(), markdown="Winner.", title="Winner")
    write_output(winner_dir, [winner], GenerationMetadata(rest_totals={}))
    original_rename = os.rename
    published = False

    def replace_installed_snapshot(
        source: str | Path,
        destination: str | Path,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal published
        destination_path = _path_at(destination, dst_dir_fd)
        original_rename(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )
        if not published and destination_path == output_dir:
            published = True
            original_rename(output_dir, displaced)
            original_rename(winner_dir, output_dir)

    monkeypatch.setattr(os, "rename", replace_installed_snapshot)

    with pytest.raises(OutputSafetyError, match="staging"):
        write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))

    assert (output_dir / "manifest.json").is_file()
    assert "# Winner" in (output_dir / "finki-website.md").read_text(encoding="utf-8")
    assert (displaced / "manifest.json").is_file()


def test_write_output_rejects_parent_link_substitution_during_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_parent = tmp_path / "missing-parent"
    output_dir = output_parent / "website"
    victim = tmp_path / "victim"
    victim.mkdir()
    displaced = tmp_path / "displaced-parent"
    original_mkdir = Path.mkdir

    def substitute_created_parent(
        path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        original_mkdir(path, mode, parents, exist_ok)
        if path == output_parent:
            _ = path.rename(displaced)
            try:
                path.symlink_to(victim, target_is_directory=True)
            except OSError:
                pytest.skip("directory symlinks are unavailable on this runner")

    monkeypatch.setattr(Path, "mkdir", substitute_created_parent)

    with pytest.raises(OutputSafetyError, match="link or junction"):
        write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))

    assert not (victim / "website").exists()


def test_write_output_does_not_follow_substituted_staging_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "website"
    victim = tmp_path / "victim"
    victim.mkdir()
    displaced = tmp_path / "displaced-language"
    original_mkdir = Path.mkdir
    original_os_mkdir = os.mkdir
    substituted = False

    def substitute_language_directory(
        path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        nonlocal substituted
        original_mkdir(path, mode, parents, exist_ok)
        if not substituted and path.name == "mk" and path.parent.name == "documents":
            substituted = True
            _ = path.rename(displaced)
            try:
                path.symlink_to(victim, target_is_directory=True)
            except OSError:
                pytest.skip("directory symlinks are unavailable on this runner")

    def substitute_posix_language_directory(
        path: str,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        nonlocal substituted
        original_os_mkdir(path, mode, dir_fd=dir_fd)
        if not substituted and path == "mk" and dir_fd is not None:
            substituted = True
            original_rename = os.rename
            original_rename(path, displaced, src_dir_fd=dir_fd)
            os.symlink(
                victim,
                path,
                target_is_directory=True,
                dir_fd=dir_fd,
            )

    if os.name == "nt":
        monkeypatch.setattr(Path, "mkdir", substitute_language_directory)
    else:
        monkeypatch.setattr(os, "mkdir", substitute_posix_language_directory)

    with pytest.raises(OutputSafetyError, match="staging"):
        write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))

    assert not tuple(victim.iterdir())


def test_publication_lock_serializes_publishers(tmp_path: Path) -> None:
    output_dir = tmp_path / "website"
    first_entered = Event()
    release_first = Event()
    second_entered = Event()

    def hold_first_lock() -> None:
        with publication_lock(output_dir):
            first_entered.set()
            _ = release_first.wait(timeout=5)

    def enter_second_lock() -> None:
        with publication_lock(output_dir):
            second_entered.set()

    first = Thread(target=hold_first_lock)
    second = Thread(target=enter_second_lock)
    first.start()
    assert first_entered.wait(timeout=2)
    second.start()

    assert not second_entered.wait(timeout=0.1)
    release_first.set()
    assert second_entered.wait(timeout=2)
    first.join(timeout=2)
    second.join(timeout=2)
    assert not first.is_alive()
    assert not second.is_alive()


def test_write_output_rejects_parent_swap_during_lock_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_parent = tmp_path / "output-parent"
    output_parent.mkdir()
    output_dir = output_parent / "website"
    displaced = tmp_path / "displaced-parent"
    original_lock = publication_lock

    @contextmanager
    def unlocked_parent(_path: Path) -> Generator[None]:
        yield

    @contextmanager
    def swap_parent_before_lock(
        path: Path,
        _parent_descriptor: int | None,
    ) -> Generator[None]:
        _ = output_parent.rename(displaced)
        output_parent.mkdir()
        with original_lock(path):
            yield

    monkeypatch.setattr(website_output, "hold_directory", unlocked_parent)
    monkeypatch.setattr(website_output, "publication_lock", swap_parent_before_lock)

    with pytest.raises(OutputSafetyError, match="changed during generation"):
        write_output(output_dir, [_document()], GenerationMetadata(rest_totals={}))

    assert not output_dir.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory permissions")
def test_temporary_output_directories_are_private_with_permissive_umask(
    tmp_path: Path,
) -> None:
    with hold_directory(tmp_path) as parent_descriptor:
        previous_umask = os.umask(0)
        try:
            temporary = make_temporary_directory(
                tmp_path,
                ".website-",
                parent_descriptor,
            )
        finally:
            _ = os.umask(previous_umask)

    assert stat.S_IMODE(temporary.stat().st_mode) == 0o700


@pytest.mark.skipif(os.name != "nt", reason="Windows reparse-point handles")
def test_hold_directory_rejects_reparse_substitution_during_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import _winapi

    parent = tmp_path / "parent"
    parent.mkdir()
    displaced = tmp_path / "displaced-parent"
    victim = tmp_path / "victim"
    victim.mkdir()
    probe = tmp_path / "probe"
    try:
        probe.symlink_to(victim, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this runner")
    probe.unlink()
    original_create_file = _winapi.CreateFile
    substituted = False

    def substitute_during_open(
        path: str,
        desired_access: int,
        share_mode: int,
        security_attributes: int,
        creation_disposition: int,
        flags_and_attributes: int,
        template_file: int,
    ) -> int:
        nonlocal substituted
        if Path(path) != parent or substituted:
            return original_create_file(
                path,
                desired_access,
                share_mode,
                security_attributes,
                creation_disposition,
                flags_and_attributes,
                template_file,
            )
        substituted = True
        _ = parent.rename(displaced)
        parent.symlink_to(victim, target_is_directory=True)
        handle = original_create_file(
            path,
            desired_access,
            share_mode,
            security_attributes,
            creation_disposition,
            flags_and_attributes,
            template_file,
        )
        try:
            parent.unlink()
            _ = displaced.rename(parent)
        except OSError:
            _winapi.CloseHandle(handle)
            parent.unlink()
            _ = displaced.rename(parent)
            raise
        return handle

    monkeypatch.setattr(_winapi, "CreateFile", substitute_during_open)

    with (
        pytest.raises(OutputSafetyError, match="directory changed"),
        hold_directory(parent),
    ):
        pass
