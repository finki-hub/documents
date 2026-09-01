import json
from collections.abc import Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType
from typing import Self
from urllib.request import Request

import pytest

from tools import preprocess


class _Response(AbstractContextManager["_Response"]):
    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def read(self) -> bytes:
        return b'{"chunk_count": 1}'


def test_ingest_preserves_all_sources_and_currentness_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "processed"
    out_dir.mkdir()
    (out_dir / "document.md").write_text(
        "<!-- title: Document | source: base.pdf | amendments: first.pdf, second.pdf | "
        "authority_url: https://finki.ukim.mk/official/base.pdf | "
        "document_date: 2013-07-04 | date_kind: adopted | date_precision: day | "
        "date_source: document_text | date_confidence: high | current_status: currentness_unresolved | "
        "last_verified: 2026-09-01 | issued: 2013-07-04 | amended_through: 2025-05-01 | "
        "source_pages: 3-21 | TIER A extraction -->\n\n# Член 1\n\nText",
        encoding="utf-8",
    )
    captured: list[dict[str, str | dict[str, str | list[str]]]] = []

    def urlopen(request: Request) -> _Response:
        assert request.data is not None
        captured.append(json.loads(request.data))
        return _Response()

    monkeypatch.setattr(preprocess, "OUT_DIR", out_dir)
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    preprocess.ingest("https://example.test")

    assert captured[0]["metadata"] == {
        "amended_through": "2025-05-01",
        "authority_url": "https://finki.ukim.mk/official/base.pdf",
        "current_status": "currentness_unresolved",
        "date_confidence": "high",
        "date_kind": "adopted",
        "date_precision": "day",
        "date_source": "document_text",
        "document_date": "2013-07-04",
        "issued": "2013-07-04",
        "last_verified": "2026-09-01",
        "r2_key": "documents/base.pdf",
        "r2_keys": [
            "documents/base.pdf",
            "documents/first.pdf",
            "documents/second.pdf",
        ],
        "source_pages": "3-21",
        "source_file": "base.pdf",
        "source_files": ["base.pdf", "first.pdf", "second.pdf"],
    }


def test_ingest_rejects_invalid_corpus_before_network_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "processed"
    out_dir.mkdir()
    (out_dir / "document.md").write_text(
        "<!-- title: Document | source: document.pdf | "
        "document_date: 2024-05-16 | date_kind: adopted | date_precision: day | "
        "date_source: document_text | date_confidence: high | current_status: current | "
        "last_verified: 2026-09-01 | TIER A extraction -->\n\nText",
        encoding="utf-8",
    )
    requests: list[Request] = []

    def urlopen(request: Request) -> _Response:
        requests.append(request)
        return _Response()

    monkeypatch.setattr(preprocess, "OUT_DIR", out_dir)
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    with pytest.raises(preprocess.MetadataError, match="missing authority_url"):
        preprocess.ingest("https://example.test")

    assert requests == []


def test_ingest_ignores_document_added_after_snapshot_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "processed"
    out_dir.mkdir()
    (out_dir / "document.md").write_text(
        "<!-- title: Document | source: document.pdf | "
        "authority_url: https://finki.ukim.mk/document.pdf | "
        "document_date: 2024-05-16 | date_kind: adopted | date_precision: day | "
        "date_source: document_text | date_confidence: high | current_status: current | "
        "last_verified: 2026-09-01 -->\n\nOriginal",
        encoding="utf-8",
    )
    late = out_dir / "late.md"
    path_glob = Path.glob
    glob_calls = 0

    def glob(path: Path, pattern: str) -> Iterator[Path]:
        nonlocal glob_calls
        paths = tuple(path_glob(path, pattern))
        glob_calls += 1
        if glob_calls == 1:
            late.write_text(
                "<!-- title: Late | authority_url: https://evil.example/document.pdf -->\n\nLate",
                encoding="utf-8",
            )
        return iter(paths)

    captured: list[dict[str, str | dict[str, str | list[str]]]] = []

    def urlopen(request: Request) -> _Response:
        assert request.data is not None
        captured.append(json.loads(request.data))
        return _Response()

    monkeypatch.setattr(Path, "glob", glob)
    monkeypatch.setattr(preprocess, "OUT_DIR", out_dir)
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    preprocess.ingest("https://example.test")

    assert [body["name"] for body in captured] == ["document"]


def test_ingest_sends_the_exact_content_that_was_validated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "processed"
    out_dir.mkdir()
    document = out_dir / "document.md"
    valid_content = (
        "<!-- title: Document | source: document.pdf | "
        "authority_url: https://finki.ukim.mk/document.pdf | "
        "document_date: 2024-05-16 | date_kind: adopted | date_precision: day | "
        "date_source: document_text | date_confidence: high | current_status: current | "
        "last_verified: 2026-09-01 -->\n\nOriginal"
    )
    document.write_text(valid_content, encoding="utf-8")
    path_read_text = Path.read_text
    document_reads = 0

    def read_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        nonlocal document_reads
        content = path_read_text(path, encoding=encoding, errors=errors)
        if path == document and document_reads == 0:
            document_reads += 1
            document.write_text(
                "<!-- title: Replaced | authority_url: https://evil.example/document.pdf -->\n\nReplaced",
                encoding="utf-8",
            )
        return content

    captured: list[dict[str, str | dict[str, str | list[str]]]] = []

    def urlopen(request: Request) -> _Response:
        assert request.data is not None
        captured.append(json.loads(request.data))
        return _Response()

    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(preprocess, "OUT_DIR", out_dir)
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    preprocess.ingest("https://example.test")

    assert captured[0]["content"] == valid_content
