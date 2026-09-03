from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from tools import website_content


@dataclass(frozen=True, slots=True)
class FakeUpdateResult:
    document_count: int
    crawl_truncated: bool


def test_main_warns_when_page_limit_truncates_crawl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def update(_output_dir: Path, _max_pages: int) -> FakeUpdateResult:
        return FakeUpdateResult(document_count=3, crawl_truncated=True)

    monkeypatch.setattr(website_content, "update_website", update)

    exit_code = website_content.main(
        ["--output", str(tmp_path / "website"), "--max-pages", "1"]
    )

    assert exit_code == 0
    assert "WARNING" in capsys.readouterr().err
