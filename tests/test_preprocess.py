import json
import subprocess
import sys
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


@pytest.mark.parametrize(
    "filename",
    [
        "vodich-za-studenti.pdf",
        "pravilnik-za-prijavi-za-korupcija-glasnik-485-2020.pdf",
    ],
)
def test_explicitly_rejected_source_remains_excluded(filename: str) -> None:
    assert preprocess.is_excluded(filename)


def test_approved_administrative_source_is_included() -> None:
    assert not preprocess.is_excluded("odluka-plati-nadomestoci-finki-2026-02-19.pdf")


def test_extract_preserves_reviewed_consolidated_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_dir = tmp_path / "raw"
    out_dir = tmp_path / "processed"
    raw_dir.mkdir()
    out_dir.mkdir()
    reviewed = out_dir / "zakon-zashtita-lichni-podatoci-42-2020.md"
    reviewed.write_text("reviewed consolidated law", encoding="utf-8")
    for filename in (
        "zakon-zashtita-lichni-podatoci-42-2020.pdf",
        "izmeni-zakon-zashtita-lichni-podatoci-294-2021.pdf",
        "dopolnuvanje-zakon-zashtita-lichni-podatoci-101-2025.pdf",
    ):
        (raw_dir / filename).write_bytes(b"not read")
    monkeypatch.setattr(preprocess, "OUT_DIR", out_dir)

    preprocess.extract_tier_a(raw_dir)

    assert reviewed.read_text(encoding="utf-8") == "reviewed consolidated law"
    assert [path.name for path in out_dir.iterdir()] == [reviewed.name]


def test_direct_extract_cli_reaches_curated_source_guard(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "zakon-zashtita-lichni-podatoci-42-2020.pdf").write_bytes(b"not read")

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "tools" / "preprocess.py"),
            "extract",
            str(raw_dir),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "SKIP  (curated set)" in result.stdout


def test_ingest_preserves_all_sources_and_currentness_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "processed"
    out_dir.mkdir()
    (out_dir / "document.md").write_text(
        "<!-- title: Document | source: base.pdf | amendments: first.pdf, second.pdf | "
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
