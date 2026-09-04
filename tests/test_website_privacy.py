from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import anyio
import httpx2
import pytest

from tools import website_content
from tools.website_models import (
    CrawlPlan,
    CrawlResult,
    GenerationMetadata,
    PageSnapshot,
    RestInventory,
    RestRecord,
    WebsiteDocument,
)


def _record(identifier: int, url: str, content: str) -> RestRecord:
    return RestRecord.model_validate(
        {
            "id": identifier,
            "link": url,
            "slug": url.rstrip("/").rsplit("/", maxsplit=1)[-1],
            "title": {"rendered": "Candidate list"},
            "content": {"rendered": content},
            "type": "announcement",
        }
    )


def _page(url: str, body: str, *, title: str = "Candidate list") -> PageSnapshot:
    return PageSnapshot(
        final_url=url,
        html=f"<main><h1>{title}</h1>{body}</main>",
        links=(),
        requested_url=url,
        status=200,
    )


def _build(
    records: dict[str, RestRecord],
    pages: tuple[PageSnapshot, ...],
) -> tuple[WebsiteDocument, ...]:
    return website_content.build_documents(
        RestInventory(records_by_url=records, totals={"announcements": len(records)}),
        CrawlResult(pages=pages, requested_count=len(pages), truncated=False),
    )


def test_build_documents_excludes_formatted_identifier_phrases() -> None:
    rest_url = "https://finki.ukim.mk/announcements/candidate-list/"
    rendered_url = "https://finki.ukim.mk/en/announcements/candidate-list/"
    records = {
        rest_url: _record(
            42,
            rest_url,
            (
                "<p>Код (првите <strong>седум</strong> бројки од единствениот "
                "матичен број на кандидатот): 0000000</p>"
            ),
        )
    }
    pages = (
        _page(
            rendered_url,
            (
                "<p>Code (the first seven <br>digits of the candidate's unique "
                "identification number): 0000000</p>"
            ),
        ),
    )

    assert _build(records, pages) == ()


def test_build_documents_excludes_short_candidate_code_tables() -> None:
    rest_url = "https://finki.ukim.mk/announcements/candidate-code/"
    rendered_url = "https://finki.ukim.mk/en/announcements/candidate-code/"
    records = {
        rest_url: _record(
            43,
            rest_url,
            "<table><tr><th>Код на кандидатот</th></tr><tr><td>FIN0000000</td></tr></table>",
        )
    }
    pages = (
        _page(
            rendered_url,
            "<table><tr><th>Candidate code</th></tr><tr><td>0000000</td></tr></table>",
        ),
    )

    assert _build(records, pages) == ()


@pytest.mark.parametrize(
    "code",
    ["FIN0000000", "F.I.N.0000000", "FIN 00-00-000", "ＦＩＮ０００００００"],
)
def test_build_documents_excludes_fin_code_without_candidate_wording(code: str) -> None:
    url = "https://finki.ukim.mk/announcements/admitted-students/"
    pages = (
        _page(
            url,
            f"<table><tr><th>Код</th></tr><tr><td>{code}</td></tr></table>",
            title="Прелиминарна листа на примени студенти",
        ),
    )

    assert _build({}, pages) == ()


def test_build_documents_blocks_sensitive_url_across_representations() -> None:
    clean_rest_sensitive_page = "https://finki.ukim.mk/announcements/rest-clean/"
    sensitive_rest_clean_page = "https://finki.ukim.mk/announcements/rest-sensitive/"
    records = {
        clean_rest_sensitive_page: _record(
            1,
            clean_rest_sensitive_page,
            "<p>Public summary.</p>",
        ),
        sensitive_rest_clean_page: _record(
            2,
            sensitive_rest_clean_page,
            "<p>Code (the first seven digits): 0000000</p>",
        ),
    }
    pages = (
        _page(
            clean_rest_sensitive_page,
            "<p>Code (the first seven digits): 0000000</p>",
        ),
        _page(sensitive_rest_clean_page, "<p>Public summary.</p>"),
    )

    assert _build(records, pages) == ()


@pytest.mark.parametrize(
    "body",
    [
        "<p>Registration number 1234567.</p>",
        "<p>Account reference 7654321.</p>",
        "<p>ISBN 1234567.</p>",
        '<p>See <a href="https://example.com/1234567">the archive</a>.</p>',
    ],
)
def test_build_documents_keeps_benign_seven_digit_values(body: str) -> None:
    url = "https://finki.ukim.mk/notice/"

    documents = _build({}, (_page(url, body, title="Notice"),))

    assert len(documents) == 1


def test_update_website_checks_rendered_version_of_complete_rest_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://finki.ukim.mk/announcements/candidate-list/"
    record = _record(44, url, "<p>Public summary.</p>")
    captured: list[WebsiteDocument] = []

    async def fake_inventory(_client: httpx2.AsyncClient) -> RestInventory:
        return RestInventory(records_by_url={url: record}, totals={"announcements": 1})

    async def fake_crawl(
        _client: httpx2.AsyncClient,
        plan: CrawlPlan,
    ) -> CrawlResult:
        assert url not in plan.discovery_only_urls
        return CrawlResult(
            pages=(
                _page(
                    url,
                    "<p>Code (the first seven digits): 0000000</p>",
                ),
            ),
            requested_count=1,
            truncated=False,
        )

    def capture_output(
        _output_dir: Path,
        documents: Iterable[WebsiteDocument],
        _metadata: GenerationMetadata,
    ) -> None:
        captured.extend(documents)

    monkeypatch.setattr(website_content, "fetch_rest_inventory", fake_inventory)
    monkeypatch.setattr(website_content, "crawl_pages", fake_crawl)
    monkeypatch.setattr(website_content, "write_output", capture_output)

    result = anyio.run(website_content.update_website, tmp_path / "website", 10)

    assert result.document_count == 0
    assert captured == []
