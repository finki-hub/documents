import json
from collections.abc import Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType
from typing import Self
from urllib.request import Request

import pytest

from tools import document_api, preprocess


class _Response(AbstractContextManager["_Response"]):
    def __init__(self, payload: bytes = b'{"chunk_count": 1}') -> None:
        self.payload = payload

    def __iter__(self) -> Iterator[bytes]:
        return iter([b'data: {"status": "ok"}\n'])

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
        return self.payload


@pytest.fixture(autouse=True)
def isolated_document_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCUMENT_API_ALLOWED_ORIGINS", "https://example.test")

    def reject_network(_request: Request) -> _Response:
        pytest.fail("Unexpected document API network access")

    monkeypatch.setattr(document_api, "_open_api_request", reject_network)


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
    monkeypatch.setattr(document_api, "_open_api_request", urlopen)

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
    monkeypatch.setattr(document_api, "_open_api_request", urlopen)

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
    monkeypatch.setattr(document_api, "_open_api_request", urlopen)

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
    monkeypatch.setattr(document_api, "_open_api_request", urlopen)

    preprocess.ingest("https://example.test")

    assert captured[0]["content"] == valid_content


@pytest.fixture
def api_corpus(tmp_path: Path) -> Path:
    (tmp_path / "document.md").write_text(
        "<!-- title: Document | source: document.pdf | "
        "authority_url: https://finki.ukim.mk/document.pdf | "
        "document_date: 2024-05-16 | date_kind: adopted | date_precision: day | "
        "date_source: document_text | date_confidence: high | current_status: current | "
        "last_verified: 2026-09-01 -->\n\nOriginal",
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.parametrize("command", ["ingest", "fill", "sync"])
def test_commands_reject_unconfigured_origin_before_transport(
    command: str,
    api_corpus: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(preprocess, "OUT_DIR", api_corpus)
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.delenv("DOCUMENT_API_ALLOWED_ORIGINS", raising=False)
    operation = getattr(preprocess, command)

    with pytest.raises(ValueError, match="DOCUMENT_API_ALLOWED_ORIGINS"):
        operation("https://example.test")


def test_fill_uses_configured_origin_and_authenticated_transport(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    requests: list[Request] = []

    def open_request(request: Request) -> _Response:
        requests.append(request)
        return _Response()

    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setattr(document_api, "_open_api_request", open_request)

    preprocess.fill("https://example.test")

    assert len(requests) == 1
    assert requests[0].full_url == "https://example.test/documents/fill"
    assert requests[0].get_method() == "POST"
    assert requests[0].get_header("X-api-key") == "test-key"
    assert requests[0].data is not None
    assert json.loads(requests[0].data) == {"all_models": True, "all_chunks": False}
    assert "Fill complete: 1 ok, 0 errors." in capsys.readouterr().out


def test_sync_uses_configured_origin_for_listing_and_pruning(
    api_corpus: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    requests: list[Request] = []

    def open_request(request: Request) -> _Response:
        requests.append(request)
        if request.get_method() == "GET":
            return _Response(b'[{"name": "old name"}]')
        return _Response(b'{"metadata": {"r2_key": "documents/old.pdf"}}')

    monkeypatch.setattr(preprocess, "OUT_DIR", api_corpus)
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setattr(document_api, "_open_api_request", open_request)

    preprocess.sync("https://example.test")

    assert [(request.get_method(), request.full_url) for request in requests] == [
        ("POST", "https://example.test/documents/"),
        ("GET", "https://example.test/documents/list"),
        ("DELETE", "https://example.test/documents/old%20name"),
    ]
    assert all(request.get_header("X-api-key") == "test-key" for request in requests)
    assert "R2 original kept as archive: documents/old.pdf" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["ingest", "fill", "sync"])
def test_commands_stop_after_transport_rejects_redirect(
    command: str,
    api_corpus: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    requests: list[Request] = []

    def reject_redirect(request: Request) -> _Response:
        requests.append(request)
        if command == "sync" and request.get_method() == "POST":
            return _Response()
        raise ValueError("API redirects are not permitted")

    monkeypatch.setattr(preprocess, "OUT_DIR", api_corpus)
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setattr(document_api, "_open_api_request", reject_redirect)
    operation = getattr(preprocess, command)

    if command == "ingest":
        operation("https://example.test")
        assert (
            "FAIL  document.md: API redirects are not permitted"
            in capsys.readouterr().out
        )
    else:
        with pytest.raises(SystemExit, match="API redirects are not permitted"):
            operation("https://example.test")

    assert len(requests) == (2 if command == "sync" else 1)
    assert all(
        request.full_url.startswith("https://example.test/documents/")
        for request in requests
    )
