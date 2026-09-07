from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path

import httpx2
import pytest

from tools import website_reference as website_reference_module
from tools.website_reference import (
    MAX_REVIEW_AGE,
    ReferencePage,
    ReferenceSource,
    has_substantive_prose,
    is_navigation_shaped,
    load_sources,
    parse_aggregate,
    refresh_reference,
    render_aggregate,
    validate_aggregate,
    verify_live,
)

ROOT = Path(__file__).parents[1]
SOURCES = ROOT / "website-reference" / "sources.toml"


def _source(source_id: str, path: str) -> ReferenceSource:
    return ReferenceSource(
        id=source_id,
        source_url=f"https://finki.ukim.mk{path}",
        canonical_url=f"https://finki.ukim.mk{path}",
        language="en",
        category="studies",
        content_kind="prose",
        last_verified=date(2026, 9, 1),
        content_selectors=("main",),
    )


def _legacy_source(source_id: str, path: str) -> ReferenceSource:
    return ReferenceSource(
        id=source_id,
        source_url=f"https://oldsite.finki.ukim.mk{path}",
        canonical_url=f"https://oldsite.finki.ukim.mk{path}",
        language="mk",
        category="studies",
        content_kind="prose",
        last_verified=date(2026, 9, 1),
        content_selectors=("main",),
    )


def _html(title: str, body: str) -> str:
    return f"<html><body><main><h1>{title}</h1>{body}</main></body></html>"


def _prose(label: str) -> str:
    return (
        f"{label} provides detailed information for students about procedures, "
        "deadlines, documents, contacts, and academic support. The instructions "
        "describe each required step clearly so visitors can complete their requests."
    )


def _refresh_with_responses(
    sources: tuple[ReferenceSource, ...],
    output: Path,
    responses: dict[str, httpx2.Response],
) -> list[str]:
    requested: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        url = str(request.url)
        requested.append(url)
        return responses[url]

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    try:
        refresh_reference(sources, output, client=client)
    finally:
        import anyio

        anyio.run(client.aclose)
    return requested


def test_task3_source_config_contains_exact_approved_25_pages() -> None:
    expected = {
        "finki-about": (
            "https://finki.ukim.mk/za-nas/nastavno-nauchna-dejnost/za-fakultetot/",
            "mk",
            "institutional",
            ".page-content__body",
        ),
        "finki-vision": (
            "https://finki.ukim.mk/za-nas/nastavno-nauchna-dejnost/za-fakultetot/vizija/",
            "mk",
            "institutional",
            "#tabs-14368-panel-vizija",
        ),
        "finki-strategic-goals": (
            "https://finki.ukim.mk/za-nas/nastavno-nauchna-dejnost/za-fakultetot/strateshki-celi/",
            "mk",
            "institutional",
            "#tabs-14368-panel-strateshki-celi",
        ),
        "finki-history": (
            "https://finki.ukim.mk/za-nas/nastavno-nauchna-dejnost/za-fakultetot/istorijat/",
            "mk",
            "institutional",
            "#tabs-14368-panel-istorijat",
        ),
        "finki-logo": (
            "https://finki.ukim.mk/za-nas/nastavno-nauchna-dejnost/za-fakultetot/logo/",
            "mk",
            "institutional",
            "#tabs-14368-panel-logo",
        ),
        "finki-centers": (
            "https://finki.ukim.mk/za-nas/rakovodstvo-i-organizacija/instituti-i-centri/centri/",
            "mk",
            "organizations",
            ".page-content__body",
        ),
        "finki-laboratories": (
            "https://finki.ukim.mk/za-nas/rakovodstvo-i-organizacija/laboratorii/",
            "mk",
            "institutional",
            "#tabs-14349-panel-laboratorii",
        ),
        "privacy-personal-data": (
            "https://finki.ukim.mk/za-nas/administracija-i-dokumenti/zashtita-na-lichni-podatoci/",
            "mk",
            "privacy",
            "main.site-main .page-content__body",
        ),
        "public-information-access": (
            "https://finki.ukim.mk/za-nas/administracija-i-dokumenti/sloboden-pristap-do-informacii-od-javen-karakter/",
            "mk",
            "public-information",
            "main.site-main .page-content__body",
        ),
        "electronic-documents": (
            "https://finki.ukim.mk/elektronski-dokumenti/",
            "mk",
            "forms",
            "main.site-main .page-content__body",
        ),
        "grade-annulment": (
            "https://finki.ukim.mk/procedura-za-ponishtuvanje-na-ocena/",
            "mk",
            "procedures",
            "main.site-main .page-content__body",
        ),
        "transfer-from-another-faculty": (
            "https://finki.ukim.mk/announcements/soopshtenie-za-prefrluvanje-od-drug-fakultet-10/",
            "mk",
            "procedures",
            "main.site-main .page-content__body",
        ),
        "course-enrollment-rules": (
            "https://finki.ukim.mk/pravila-za-zapishuvanje-na-predmeti/",
            "mk",
            "procedures",
            "main.site-main .page-content__body",
        ),
        "student-forms": (
            "https://finki.ukim.mk/studii-2/poddrshka/obrasci/",
            "mk",
            "forms",
            "main.site-main .page-content__body",
        ),
        "erasmus": (
            "https://finki.ukim.mk/studii-2/poddrshka/erazmus/",
            "mk",
            "erasmus",
            "main.site-main .page-content__body",
        ),
        "ug-study-program-choice": (
            "https://finki.ukim.mk/upisi/dodiplomski-studii/izbor-na-studiska-programa/",
            "mk",
            "programmes",
            ".page-content__body",
        ),
        "ug-required-subjects": (
            "https://finki.ukim.mk/upisi/dodiplomski-studii/potrebni-predmeti/",
            "mk",
            "studies",
            ".page-content__body",
        ),
        "ug-required-documents": (
            "https://finki.ukim.mk/upisi/dodiplomski-studii/potrebni-dokumenti/",
            "mk",
            "forms",
            ".page-content__body",
        ),
        "ug-scholarships": (
            "https://finki.ukim.mk/upisi/dodiplomski-studii/stipendii/",
            "mk",
            "student-support",
            ".page-content__body",
        ),
        "masters-required-documents": (
            "https://finki.ukim.mk/upisi/magisterski-studii/potrebni-dokumenti/",
            "mk",
            "forms",
            ".page-content__body",
        ),
        "masters-admission-conditions": (
            "https://finki.ukim.mk/upisi/magisterski-studii/uslovi/",
            "mk",
            "studies",
            ".page-content__body",
        ),
        "doctoral-required-documents": (
            "https://finki.ukim.mk/upisi/doktorski-studii/potrebni-dokumenti/",
            "mk",
            "forms",
            ".page-content__body",
        ),
        "doctoral-admission-conditions": (
            "https://finki.ukim.mk/upisi/doktorski-studii/uslovi/",
            "mk",
            "studies",
            ".page-content__body",
        ),
        "international-undergraduate-admissions": (
            "https://finki.ukim.mk/internacionalni-studenti/admissions/undergraduate-studies-for-international-students/",
            "en",
            "international-study",
            ".page-content__body",
        ),
        "international-masters-admissions": (
            "https://finki.ukim.mk/internacionalni-studenti/admissions/masters-studies-for-international-students/",
            "en",
            "international-study",
            ".page-content__body",
        ),
    }
    structured_ids = {"finki-centers", "ug-required-subjects"}
    link_catalog_ids = {"student-forms"}
    sources = load_sources(SOURCES, today=date(2026, 9, 7))
    records = {
        source.id: (
            source.source_url,
            source.canonical_url,
            source.language,
            source.category,
            source.content_selectors[0],
            source.content_kind,
        )
        for source in sources
    }

    assert records == {
        source_id: (
            url,
            url,
            language,
            category,
            selector,
            (
                "structured"
                if source_id in structured_ids
                else "link-catalog"
                if source_id in link_catalog_ids
                else "prose"
            ),
        )
        for source_id, (url, language, category, selector) in expected.items()
    }
    assert sum(source.content_kind == "prose" for source in sources) == 22
    assert {
        source.id for source in sources if source.content_kind == "structured"
    } == structured_ids
    assert {
        source.id for source in sources if source.content_kind == "link-catalog"
    } == link_catalog_ids
    assert {source.last_verified for source in sources} == {date(2026, 9, 7)}
    assert not {
        "study-guide",
        "student-practice",
        "about-faculty",
        "strategic-goals",
    }.intersection(records)


def test_allowlist_accepts_amended_two_source_floor(tmp_path: Path) -> None:
    original = SOURCES.read_text(encoding="utf-8")
    source_blocks = original.split("[[sources]]")
    path = tmp_path / "sources.toml"
    path.write_text(
        source_blocks[0] + "[[sources]]" + "[[sources]]".join(source_blocks[1:3]),
        encoding="utf-8",
    )

    sources = load_sources(path, today=date(2026, 9, 7))

    assert len(sources) == 2


def _kind_contract_toml(*, version: int, content_kind: str | None) -> str:
    kind_line = f'content_kind = "{content_kind}"\n' if content_kind is not None else ""
    return (
        f"version = {version}\n\n"
        "[[sources]]\n"
        'id = "kind-page"\n'
        'source_url = "https://finki.ukim.mk/za-nas/about/"\n'
        'canonical_url = "https://finki.ukim.mk/za-nas/about/"\n'
        'language = "mk"\n'
        'category = "studies"\n'
        f"{kind_line}"
        'last_verified = "2026-09-07"\n'
        'content_selectors = ["main"]\n'
    )


def test_source_contract_requires_v2_and_explicit_known_content_kind(
    tmp_path: Path,
) -> None:
    version_one = tmp_path / "version-one.toml"
    version_one.write_text(
        _kind_contract_toml(version=1, content_kind="prose"), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="version"):
        load_sources(version_one, today=date(2026, 9, 7))

    missing_kind = tmp_path / "missing-kind.toml"
    missing_kind.write_text(
        _kind_contract_toml(version=2, content_kind=None), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="content_kind"):
        load_sources(missing_kind, today=date(2026, 9, 7))

    unknown_kind = tmp_path / "unknown-kind.toml"
    unknown_kind.write_text(
        _kind_contract_toml(version=2, content_kind="catalog"), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="content_kind"):
        load_sources(unknown_kind, today=date(2026, 9, 7))


def test_structured_content_kind_accepts_repeated_headings_and_rejects_bad_shell() -> (
    None
):
    structured = "\n".join(
        [
            "## Институти",
            _prose("Центр за истражување"),
            "## Институти",
            _prose("Центар за поддршка"),
            "## Институти",
            _prose("Центар за развој"),
        ]
    )
    assert (
        website_reference_module.validate_reference_body(
            structured, "finki-centers", content_kind="structured"
        )
        == structured
    )

    link_dominated_shell = "\n".join(
        [_prose("Структурирана содржина")]
        + ["- [Home](https://example.com/home)"] * 300
    )
    with pytest.raises(ValueError, match="navigation|quality"):
        website_reference_module.validate_reference_body(
            link_dominated_shell, "finki-centers", content_kind="structured"
        )


def test_link_catalog_requires_distinct_labeled_http_links() -> None:
    body = (
        "- [Detailed undergraduate application instructions and required supporting documents](https://finki.ukim.mk/forms/undergraduate)\n"
        "- [Detailed graduate application instructions and required supporting documents](https://finki.ukim.mk/forms/graduate)\n"
        "- [Detailed doctoral application instructions and required supporting documents](https://finki.ukim.mk/forms/doctoral)"
    )
    assert (
        website_reference_module.validate_reference_body(
            body, "student-forms", content_kind="link-catalog"
        )
        == body
    )

    invalid_bodies = (
        _prose("Plain prose only"),
        "\n".join(["- [Same form](https://example.com/form)"] * 3),
        "- [](https://example.com/blank)",
        "\n".join(["- [Home](https://example.com/home)"] * 3),
        "- [Unsafe](javascript:alert(1))",
        "- [Placeholder](#)",
    )
    for invalid_body in invalid_bodies:
        with pytest.raises(ValueError, match="link|catalog|navigation|quality"):
            website_reference_module.validate_reference_body(
                invalid_body, "student-forms", content_kind="link-catalog"
            )


def test_link_catalog_refresh_preserves_links_without_fetching_targets(
    tmp_path: Path,
) -> None:
    source = replace(
        _source("student-forms", "/en/forms/"), content_kind="link-catalog"
    )
    body = (
        '<a href="https://example.com/form-one">Detailed form instructions for undergraduate students and required supporting documents</a>'
        '<a href="https://example.com/form-two">Detailed form instructions for graduate students and required supporting documents</a>'
        '<a href="https://example.com/form-three">Detailed form instructions for doctoral students and required supporting documents</a>'
    )
    requested = _refresh_with_responses(
        (source,),
        tmp_path / "aggregate.md",
        {
            source.source_url: httpx2.Response(
                200,
                headers={"content-type": "text/html"},
                text=_html("Forms", body),
            )
        },
    )
    aggregate = (tmp_path / "aggregate.md").read_text(encoding="utf-8")
    assert requested == [source.source_url]
    assert "https://example.com/form-one" in aggregate
    assert "https://example.com/form-two" in aggregate
    assert "https://example.com/form-three" in aggregate


def test_aggregate_round_trip_preserves_and_validates_content_kind() -> None:
    body = _prose("Structured information")
    page = ReferencePage(
        source_id="structured-page",
        source_url="https://finki.ukim.mk/en/structured/",
        canonical_url="https://finki.ukim.mk/en/structured/",
        language="en",
        category="studies",
        content_kind="structured",
        last_verified=date(2026, 9, 1),
        title="Structured",
        body=body,
        content_sha256=sha256(f"Structured\n\n{body}".encode()).hexdigest(),
    )
    rendered = render_aggregate((page,))
    assert "content_kind: structured\n" in rendered
    assert parse_aggregate(rendered)[0].content_kind == "structured"
    tampered = rendered.replace("content_kind: structured", "content_kind: prose")
    source = ReferenceSource(
        id=page.source_id,
        source_url=page.source_url,
        canonical_url=page.canonical_url,
        language=page.language,
        category=page.category,
        content_kind=page.content_kind,
        last_verified=page.last_verified,
        content_selectors=("main",),
    )
    with pytest.raises(ValueError, match="content_kind|metadata"):
        validate_aggregate(tampered, (source,))

    missing_kind = rendered.replace("content_kind: structured\n", "")
    with pytest.raises(ValueError, match="metadata|content_kind"):
        parse_aggregate(missing_kind)
    unknown_kind = rendered.replace("content_kind: structured", "content_kind: catalog")
    with pytest.raises(ValueError, match="content_kind"):
        parse_aggregate(unknown_kind)


def test_structured_body_can_pass_structured_quality_without_prose_quality() -> None:
    long_link_label = " ".join(["Detailed linked information"] * 30)
    body = f"{_prose('Structured information')}\n[{long_link_label}](https://example.com/details)"

    assert not has_substantive_prose(body)
    assert (
        website_reference_module.validate_reference_body(
            body, "finki-centers", content_kind="structured"
        )
        == body
    )


@pytest.mark.parametrize("content_kind", ["structured", "link-catalog"])
def test_sensitive_identifiers_rejected_for_non_prose_shapes(
    tmp_path: Path, content_kind: str
) -> None:
    if content_kind == "structured":
        body = _prose("Structured content") + "\nCandidate identifier: 1234567"
    else:
        body = (
            "- [Detailed form instructions for undergraduate student applications and supporting documents](https://example.com/one)\n"
            "- [Detailed form instructions for graduate student applications and supporting documents](https://example.com/two)\n"
            "- [Detailed form instructions for doctoral student applications and supporting documents](https://example.com/three)\n"
            "Candidate identifier: 1234567"
        )
    source = replace(
        _source(f"{content_kind}-sensitive", "/en/sensitive/"),
        content_kind=content_kind,
    )
    with pytest.raises(ValueError, match="identifier"):
        _refresh_with_responses(
            (source,),
            tmp_path / f"{content_kind}.md",
            {
                source.source_url: httpx2.Response(
                    200,
                    headers={"content-type": "text/html"},
                    text=_html("Sensitive", body),
                )
            },
        )


def test_invalid_programmatic_content_kind_is_rejected_before_fetch(
    tmp_path: Path,
) -> None:
    source = replace(
        _source("invalid-kind", "/en/invalid-kind/"), content_kind="invalid"
    )
    requested: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested.append(str(request.url))
        return httpx2.Response(
            200,
            headers={"content-type": "text/html"},
            text=_html("Invalid", f"<p>{_prose('Invalid kind')}</p>"),
        )

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    try:
        with pytest.raises(ValueError, match="content_kind"):
            refresh_reference((source,), tmp_path / "aggregate.md", client=client)
    finally:
        import anyio

        anyio.run(client.aclose)

    assert requested == []


def _selector_allowlist(
    *,
    first_selector: str | None = '["#article-body"]',
    second_selector: str | None = '["main"]',
) -> str:
    first = (
        f"content_selectors = {first_selector}\n" if first_selector is not None else ""
    )
    second = (
        f"content_selectors = {second_selector}\n"
        if second_selector is not None
        else ""
    )
    return (
        "version = 2\n\n"
        "[[sources]]\n"
        'id = "finki-legal-acts"\n'
        'source_url = "https://oldsite.finki.ukim.mk/mk/zafakultetot/pravni_akti"\n'
        'canonical_url = "https://oldsite.finki.ukim.mk/mk/zafakultetot/pravni_akti"\n'
        'language = "mk"\ncategory = "legal"\ncontent_kind = "prose"\nlast_verified = "2026-09-07"\n'
        f"{first}\n"
        "[[sources]]\n"
        'id = "student-service"\n'
        'source_url = "https://oldsite.finki.ukim.mk/mk/studies/studentska-sluzba"\n'
        'canonical_url = "https://oldsite.finki.ukim.mk/mk/studies/studentska-sluzba"\n'
        'language = "mk"\ncategory = "procedures"\ncontent_kind = "prose"\nlast_verified = "2026-09-07"\n'
        f"{second}"
    )


def _route_allowlist(url: str, *, language: str = "mk") -> str:
    text = _selector_allowlist()
    old_url = "https://oldsite.finki.ukim.mk/mk/zafakultetot/pravni_akti"
    text = text.replace(old_url, url)
    return text.replace('language = "mk"', f'language = "{language}"', 1)


@pytest.mark.parametrize(
    ("url", "language"),
    [
        ("https://finki.ukim.mk/za-nas/about/", "mk"),
        ("https://finki.ukim.mk/upisi/programmes/", "mk"),
        ("https://finki.ukim.mk/studii-2/support/", "mk"),
        ("https://finki.ukim.mk/elektronski-dokumenti/", "mk"),
        ("https://finki.ukim.mk/procedura-za-ponishtuvanje-na-ocena/", "mk"),
        ("https://finki.ukim.mk/pravila-za-zapishuvanje-na-predmeti/", "mk"),
        (
            "https://finki.ukim.mk/announcements/soopshtenie-za-prefrluvanje-od-drug-fakultet-10/",
            "mk",
        ),
        (
            "https://finki.ukim.mk/internacionalni-studenti/admissions/undergraduate-studies-for-international-students/",
            "en",
        ),
        (
            "https://finki.ukim.mk/internacionalni-studenti/admissions/masters-studies-for-international-students/",
            "en",
        ),
    ],
)
def test_allowlist_accepts_bounded_unprefixed_routes(
    tmp_path: Path, url: str, language: str
) -> None:
    path = tmp_path / "sources.toml"
    path.write_text(_route_allowlist(url, language=language), encoding="utf-8")

    sources = load_sources(path, today=date(2026, 9, 7))

    assert sources[0].source_url == url
    assert sources[0].language == language


@pytest.mark.parametrize(
    ("url", "language"),
    [
        ("https://finki.ukim.mk/unknown/root/", "mk"),
        ("https://finki.ukim.mk/documents/guide/", "mk"),
        ("https://finki.ukim.mk/announcements/other/", "mk"),
        (
            "https://finki.ukim.mk/internacionalni-studenti/admissions/other/",
            "en",
        ),
        ("https://finki.ukim.mk/za-nas/about/", "en"),
        (
            "https://finki.ukim.mk/internacionalni-studenti/admissions/undergraduate-studies-for-international-students/",
            "mk",
        ),
        ("https://finki.ukim.mk/za-nas/%6eews/", "mk"),
        ("https://finki.ukim.mk/za-nas/assets/file.pdf", "mk"),
        ("https://finki.ukim.mk/za-nas/wp-admin/", "mk"),
        ("https://finki.ukim.mk/za-nas/feed/", "mk"),
        ("https://finki.ukim.mk/za-nas/2026/09/", "mk"),
        ("https://finki.ukim.mk/za-nas/about/?candidate=1234567", "mk"),
    ],
)
def test_allowlist_rejects_unbounded_unprefixed_routes(
    tmp_path: Path, url: str, language: str
) -> None:
    path = tmp_path / "sources.toml"
    path.write_text(_route_allowlist(url, language=language), encoding="utf-8")

    with pytest.raises(
        ValueError, match="(route|language|forbidden|asset|candidate|query)"
    ):
        load_sources(path, today=date(2026, 9, 7))


def test_allowed_transfer_exception_still_rejects_sensitive_body(
    tmp_path: Path,
) -> None:
    url = "https://finki.ukim.mk/announcements/soopshtenie-za-prefrluvanje-od-drug-fakultet-10/"
    source = ReferenceSource(
        id="transfer-from-another-faculty",
        source_url=url,
        canonical_url=url,
        language="mk",
        category="procedures",
        content_kind="prose",
        last_verified=date(2026, 9, 7),
        content_selectors=("main",),
    )

    with pytest.raises(ValueError, match="identifier"):
        _refresh_with_responses(
            (source,),
            tmp_path / "aggregate.md",
            {
                url: httpx2.Response(
                    200,
                    headers={"content-type": "text/html"},
                    text=_html(
                        "Transfer",
                        f"<p>{_prose('Candidate identifier 1234567')}</p>",
                    ),
                )
            },
        )


@pytest.mark.parametrize(
    "value",
    [
        '"#article-body"',
        "[]",
        '[""]',
        '["   "]',
        '["#article\\rbody"]',
        '["[broken"]',
        '["> main"]',
        '["main >> div"]',
        '["main\\tdiv"]',
        '["main:"]',
        '["main::"]',
        '["main[attr=value]"]',
        '["main + div"]',
        '["<!-- finki-static-page:start -->"]',
    ],
)
def test_allowlist_rejects_invalid_content_selector_values(
    tmp_path: Path, value: str
) -> None:
    path = tmp_path / "sources.toml"
    path.write_text(_selector_allowlist(first_selector=value), encoding="utf-8")

    with pytest.raises(ValueError, match="content_selectors"):
        load_sources(path, today=date(2026, 9, 7))


def test_allowlist_rejects_missing_content_selectors(tmp_path: Path) -> None:
    path = tmp_path / "sources.toml"
    path.write_text(_selector_allowlist(first_selector=None), encoding="utf-8")

    with pytest.raises(ValueError, match="content_selectors"):
        load_sources(path, today=date(2026, 9, 7))


def test_allowlist_does_not_grandfather_changed_seed_metadata(tmp_path: Path) -> None:
    path = tmp_path / "sources.toml"
    path.write_text(
        _selector_allowlist(first_selector=None, second_selector=None).replace(
            'category = "legal"', 'category = "studies"', 1
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="content_selectors"):
        load_sources(path, today=date(2026, 9, 7))


@pytest.mark.parametrize("control", [*range(0x20), 0x7F])
@pytest.mark.parametrize("position", ["prefix", "suffix"])
def test_allowlist_rejects_every_selector_boundary_control(
    tmp_path: Path, control: int, position: str
) -> None:
    escaped = f"\\u{control:04x}"
    value = (
        f'["{escaped}#article-body"]'
        if position == "prefix"
        else f'["#article-body{escaped}"]'
    )
    path = tmp_path / "sources.toml"
    path.write_text(_selector_allowlist(first_selector=value), encoding="utf-8")

    with pytest.raises(ValueError, match="content_selectors"):
        load_sources(path, today=date(2026, 9, 7))


def test_allowlist_accepts_a_valid_selector_after_boundary_control_checks(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sources.toml"
    path.write_text(
        _selector_allowlist(first_selector='["#article-body"]'), encoding="utf-8"
    )

    sources = load_sources(path, today=date(2026, 9, 7))

    assert sources[0].content_selectors == ("#article-body",)


@pytest.mark.parametrize(
    "url",
    [
        "https://finki.ukim.mk/mk/studies/",
        "https://www.finki.ukim.mk/mk/studies/",
        "https://oldsite.finki.ukim.mk/mk/studies/",
    ],
)
def test_allowlist_accepts_direct_macedonian_routes_on_all_finki_hosts(
    tmp_path: Path,
    url: str,
) -> None:
    text = _selector_allowlist().replace(
        "https://oldsite.finki.ukim.mk/mk/zafakultetot/pravni_akti", url
    )
    path = tmp_path / "sources.toml"
    path.write_text(text, encoding="utf-8")
    assert load_sources(path, today=date(2026, 9, 7))[0].language == "mk"


@pytest.mark.parametrize(
    "url",
    [
        "https://oldsite.finki.ukim.mk/en/studies/",
        "https://finki.ukim.mk/de/studies/",
        "https://www.finki.ukim.mk.evil/mk/studies/",
        "https://finki.ukim.mk/mk/assets/file.pdf",
        "https://finki.ukim.mk/mk/studies/?page=2",
    ],
)
def test_allowlist_rejects_non_canonical_curated_routes(
    tmp_path: Path, url: str
) -> None:
    text = _selector_allowlist().replace(
        "https://oldsite.finki.ukim.mk/mk/zafakultetot/pravni_akti", url
    )
    path = tmp_path / "sources.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="(URL|route|host|query|asset|language)"):
        load_sources(path, today=date(2026, 9, 7))


def test_curated_adapter_uses_selector_and_never_follows_page_links(
    tmp_path: Path,
) -> None:
    source = replace(
        _legacy_source("selector-page", "/mk/selector/"),
        content_selectors=("#article-body",),
    )
    article = (
        "This article contains the substantive institutional information needed by students. "
        "It explains procedures, contacts, deadlines, and supporting documents in detail. "
        "Students should review the instructions carefully before submitting requests, "
        "because each academic service follows a documented and transparent process."
    )
    html = (
        "<html><body><main><nav>Home Studies Contact</nav>"
        '<a href="https://oldsite.finki.ukim.mk/mk/linked/">Linked label</a>'
        f'<section id="article-body"><h1>Selector page</h1><p>{article}</p></section>'
        "</main></body></html>"
    )
    output = tmp_path / "aggregate.md"
    requested = _refresh_with_responses(
        (source,),
        output,
        {
            source.source_url: httpx2.Response(
                200, headers={"content-type": "text/html"}, text=html
            )
        },
    )

    body = parse_aggregate(output.read_text(encoding="utf-8"))[0].body
    assert requested == [source.source_url]
    assert "substantive institutional information" in body
    assert "Home Studies Contact" not in body
    assert "Linked label" not in body


def test_current_source_redirects_only_to_its_legacy_canonical(
    tmp_path: Path,
) -> None:
    source = ReferenceSource(
        id="study-guide",
        source_url="https://finki.ukim.mk/mk/studies/study-guide",
        canonical_url="https://oldsite.finki.ukim.mk/mk/studies/study-guide",
        language="mk",
        category="studies",
        content_kind="prose",
        last_verified=date(2026, 9, 7),
        content_selectors=("#node-24594 .field-item > div:nth-child(1)",),
    )
    response = _prose("Студискиот водич")
    responses = {
        source.source_url: httpx2.Response(
            307,
            headers={"location": source.canonical_url},
        ),
        source.canonical_url: httpx2.Response(
            200,
            headers={"content-type": "text/html"},
            text=_html(
                "Водич за студирање",
                f'<div id="node-24594"><div class="field-item"><div>{response}</div></div></div>',
            ),
        ),
    }

    requested = _refresh_with_responses((source,), tmp_path / "aggregate.md", responses)

    assert requested == [source.source_url, source.canonical_url]


def test_quality_gates_distinguish_prose_from_navigation() -> None:
    link_list = "\n".join(
        f"- [Section {index}](https://example.com/{index})" for index in range(20)
    )
    repeated = "\n".join(["Home", "Studies", "Contact"] * 3)
    repeated_links = "\n".join(["- [Home](https://example.com/home)"] * 3)
    prose = (
        "Students can find detailed information about enrolment, examinations, "
        "study procedures, required forms, deadlines, contacts, and academic support. "
        "The faculty publishes the current instructions and explains each step clearly."
    )

    assert not has_substantive_prose(link_list)
    assert is_navigation_shaped(repeated)
    assert is_navigation_shaped(repeated_links)
    assert has_substantive_prose(prose)
    assert not is_navigation_shaped(prose)


def test_navigation_shape_ignores_repeated_long_instructional_prose() -> None:
    repeated_prose = "Поднесете го барањето преку системот денес."
    repeated_short_label = "Студии"
    repeated_thirty_nine = "Choose a study programme from this menu"
    repeated_forty = "Choose a study programme from this menu."

    assert len(repeated_prose) == 43
    assert len(repeated_thirty_nine) == 39
    assert len(repeated_forty) == 40
    assert not is_navigation_shaped("\n".join([repeated_prose] * 3))
    assert is_navigation_shaped("\n".join([repeated_short_label] * 3))
    assert is_navigation_shaped("\n".join([repeated_thirty_nine] * 3))
    assert not is_navigation_shaped("\n".join([repeated_forty] * 3))


@pytest.mark.parametrize(
    "body",
    [
        "\n".join(
            f"- [Section {index}](https://example.com/{index})" for index in range(30)
        ),
        "\n".join(
            ["Student services and procedures"] * 3
            + ["Academic support and deadlines"] * 3
            + ["Faculty contacts and forms"] * 3
        ),
    ],
)
def test_refresh_quality_gates_leave_prior_aggregate_untouched(
    tmp_path: Path, body: str
) -> None:
    source = _source("quality-page", "/en/quality/")
    output = tmp_path / "aggregate.md"
    output.write_text("prior aggregate\n", encoding="utf-8")

    with pytest.raises(ValueError, match="empty|navigation"):
        _refresh_with_responses(
            (source,),
            output,
            {
                source.source_url: httpx2.Response(
                    200,
                    headers={"content-type": "text/html"},
                    text=_html("Quality", f"<div>{body}</div>"),
                )
            },
        )

    assert output.read_text(encoding="utf-8") == "prior aggregate\n"


def test_direct_legacy_source_refreshes_without_following_page_links(
    tmp_path: Path,
) -> None:
    source = _legacy_source("legacy-page", "/mk/zafakultetot/instituti")
    output = tmp_path / "aggregate.md"
    requested: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested.append(str(request.url))
        return httpx2.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=_html(
                "Институти",
                f"<p>{_prose('Информации за институтите на факултетот')}</p>"
                '<a href="https://finki.ukim.mk/en/news/">news</a>',
            ),
        )

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    try:
        refresh_reference((source,), output, client=client)
    finally:
        import anyio

        anyio.run(client.aclose)

    assert requested == [source.source_url]
    assert parse_aggregate(output.read_text(encoding="utf-8"))[0].language == "mk"


@pytest.mark.parametrize(
    "value",
    [
        "http://finki.ukim.mk/en/studies/",
        "https://example.com/en/studies/",
        "https://finki.ukim.mk/wp-json/wp/v2/pages",
        "https://finki.ukim.mk/en/news/",
        "https://finki.ukim.mk/en/jobs-and-internships/",
        "https://finki.ukim.mk/en/project/evergreen/",
        "https://finki.ukim.mk/en/wp-content/uploads/file.pdf",
        "https://finki.ukim.mk/en/media/handbook.pdf",
        "https://finki.ukim.mk/en/documents/form.pdf",
        "https://finki.ukim.mk/en/images/logo.png",
        "https://finki.ukim.mk/en/studies/overview.pdf",
        "https://finki.ukim.mk/en/studies/?candidate=12345",
    ],
)
def test_allowlist_rejects_unsafe_url_routes(tmp_path: Path, value: str) -> None:
    first_source = load_sources(SOURCES, today=date(2026, 9, 7))[0]
    text = SOURCES.read_text(encoding="utf-8")
    text = text.replace(
        f'source_url = "{first_source.source_url}"',
        f'source_url = "{value}"',
        1,
    )
    text = text.replace(
        f'canonical_url = "{first_source.canonical_url}"',
        f'canonical_url = "{value}"',
        1,
    )
    path = tmp_path / "sources.toml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="(URL|route|candidate|HTTPS|host|query)"):
        load_sources(path, today=date(2026, 9, 7))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("language", "en"),
        ("source_url", "https://oldsite.finki.ukim.mk/en/studies/"),
        ("canonical_url", "https://oldsite.finki.ukim.mk/en/studies/"),
    ],
)
def test_allowlist_requires_macedonian_legacy_routes(
    tmp_path: Path, field: str, value: str
) -> None:
    original = _selector_allowlist()
    route_host = "oldsite.finki.ukim.mk"
    old_value = (
        'language = "mk"'
        if field == "language"
        else f'{field} = "https://{route_host}/mk/zafakultetot/pravni_akti"'
    )
    path = tmp_path / "sources.toml"
    path.write_text(
        original.replace(old_value, f'{field} = "{value}"', 1), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="Macedonian|/mk/|language"):
        load_sources(path, today=date(2026, 9, 7))


def test_allowlist_rejects_stale_and_future_reviews(tmp_path: Path) -> None:
    original = SOURCES.read_text(encoding="utf-8")
    stale = date(2026, 9, 7) - MAX_REVIEW_AGE - timedelta(days=1)
    path = tmp_path / "sources.toml"
    path.write_text(
        original.replace(
            'last_verified = "2026-09-07"', f'last_verified = "{stale}"', 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="review"):
        load_sources(path, today=date(2026, 9, 7))

    path.write_text(
        original.replace(
            'last_verified = "2026-09-07"', 'last_verified = "2026-09-08"', 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="future"):
        load_sources(path, today=date(2026, 9, 7))


def test_parse_aggregate_exposes_metadata_and_verifies_hash() -> None:
    body = _prose("Overview of evergreen study information")
    digest = sha256(f"Study overview\n\n{body}".encode()).hexdigest()
    text = (
        "<!-- finki-static-page:start id=studies-overview -->\n"
        "source_url: https://finki.ukim.mk/en/studies/\n"
        "canonical_url: https://finki.ukim.mk/en/studies/\n"
        "language: en\n"
        "category: studies\n"
        "content_kind: prose\n"
        "last_verified: 2026-09-01\n"
        "title: Study overview\n"
        f"sha256: {digest}\n\n"
        f"{body}\n"
        "<!-- finki-static-page:end -->\n"
    )

    page = parse_aggregate(text)[0]

    assert page.source_id == "studies-overview"
    assert page.title == "Study overview"
    assert page.body == body
    assert page.content_sha256 == digest
    assert page.source_url in text


def test_parse_aggregate_rejects_boundary_injection_and_bad_hash() -> None:
    body = "safe\n<!-- finki-static-page:end -->\nforged"
    digest = sha256(f"Title\n\n{body}".encode()).hexdigest()
    text = (
        "<!-- finki-static-page:start id=safe -->\n"
        "source_url: https://finki.ukim.mk/en/safe/\n"
        "canonical_url: https://finki.ukim.mk/en/safe/\n"
        "language: en\ncategory: studies\ncontent_kind: prose\nlast_verified: 2026-09-01\n"
        "title: Title\n"
        f"sha256: {digest}\n\n{body}\n"
        "<!-- finki-static-page:end -->\n"
    )

    with pytest.raises(ValueError, match="(boundary|unexpected)"):
        parse_aggregate(text)


def test_parse_aggregate_rejects_bad_hash() -> None:
    body = _prose("safe body")
    text = (
        "<!-- finki-static-page:start id=safe -->\n"
        "source_url: https://finki.ukim.mk/en/safe/\n"
        "canonical_url: https://finki.ukim.mk/en/safe/\n"
        "language: en\ncategory: studies\ncontent_kind: prose\nlast_verified: 2026-09-01\n"
        "title: Title\n"
        "sha256: 0000000000000000000000000000000000000000000000000000000000000000\n\n"
        f"{body}\n"
        "<!-- finki-static-page:end -->\n"
    )

    with pytest.raises(ValueError, match="hash"):
        parse_aggregate(text)


def test_render_rejects_a_validly_hashed_low_quality_body() -> None:
    body = "Home\nHome\nHome"
    page = ReferencePage(
        source_id="safe-page",
        source_url="https://finki.ukim.mk/en/safe/",
        canonical_url="https://finki.ukim.mk/en/safe/",
        language="en",
        category="studies",
        content_kind="prose",
        last_verified=date(2026, 9, 1),
        title="Navigation",
        body=body,
        content_sha256=sha256(f"Navigation\n\n{body}".encode()).hexdigest(),
    )

    with pytest.raises(ValueError, match="navigation|empty"):
        render_aggregate((page,))


def test_offline_check_rejects_a_validly_hashed_low_quality_body(
    tmp_path: Path,
) -> None:
    sources_path = tmp_path / "sources.toml"
    sources_path.write_text(_selector_allowlist(), encoding="utf-8")
    source = load_sources(sources_path, today=date(2026, 9, 7))[0]
    body = "Home\nHome\nHome"
    title = "Navigation"
    digest = sha256(f"{title}\n\n{body}".encode()).hexdigest()
    aggregate = (
        f"<!-- finki-static-page:start id={source.id} -->\n"
        f"source_url: {source.source_url}\n"
        f"canonical_url: {source.canonical_url}\n"
        f"language: {source.language}\n"
        f"category: {source.category}\n"
        f"content_kind: {source.content_kind}\n"
        f"last_verified: {source.last_verified.isoformat()}\n"
        f"title: {title}\n"
        f"sha256: {digest}\n\n{body}\n"
        "<!-- finki-static-page:end -->\n"
    )
    aggregate_path = tmp_path / "aggregate.md"
    aggregate_path.write_bytes(aggregate.encode())

    with pytest.raises(ValueError, match="navigation|empty"):
        website_reference_module.main(
            [
                "--check",
                "--sources",
                str(sources_path),
                "--aggregate",
                str(aggregate_path),
            ]
        )


def test_render_parse_is_byte_stable_and_sorted() -> None:
    pages = (
        ReferencePage(
            source_id="z-page",
            source_url="https://finki.ukim.mk/en/z/",
            canonical_url="https://finki.ukim.mk/en/z/",
            language="en",
            category="studies",
            content_kind="prose",
            last_verified=date(2026, 9, 1),
            title="Zed",
            body=_prose("Z body"),
            content_sha256=sha256(f"Zed\n\n{_prose('Z body')}".encode()).hexdigest(),
        ),
        ReferencePage(
            source_id="a-page",
            source_url="https://finki.ukim.mk/en/a/",
            canonical_url="https://finki.ukim.mk/en/a/",
            language="en",
            category="studies",
            content_kind="prose",
            last_verified=date(2026, 9, 1),
            title="A title",
            body=f"{_prose('A body')}\r\n",
            content_sha256=sha256(
                f"A title\n\n{_prose('A body')}".encode()
            ).hexdigest(),
        ),
    )

    rendered = render_aggregate(pages)
    reparsed = parse_aggregate(rendered)

    assert rendered == render_aggregate(reparsed)
    assert [page.source_id for page in reparsed] == ["a-page", "z-page"]
    assert "\r" not in rendered


@pytest.mark.parametrize(
    "field",
    ["source_id", "source_url", "canonical_url", "language", "category", "title"],
)
def test_render_rejects_unsafe_metadata(field: str) -> None:
    page = ReferencePage(
        source_id="safe-page",
        source_url="https://finki.ukim.mk/en/safe/",
        canonical_url="https://finki.ukim.mk/en/safe/",
        language="en",
        category="studies",
        content_kind="prose",
        last_verified=date(2026, 9, 1),
        title="Safe title",
        body="Safe body",
        content_sha256=sha256(b"Safe title\n\nSafe body").hexdigest(),
    )
    unsafe_value = {
        "source_id": "safe-page\n<!-- finki-static-page:end -->",
        "source_url": "https://finki.ukim.mk/en/safe/\r\nforged: value",
        "canonical_url": "https://finki.ukim.mk/en/safe/\r\nforged: value",
        "language": "en\nforged",
        "category": "studies\r\nforged",
        "title": "Safe title\n<!-- finki-static-page:end -->",
    }[field]
    if field == "source_id":
        unsafe_page = replace(page, source_id=unsafe_value)
    elif field == "source_url":
        unsafe_page = replace(page, source_url=unsafe_value)
    elif field == "canonical_url":
        unsafe_page = replace(page, canonical_url=unsafe_value)
    elif field == "language":
        unsafe_page = replace(page, language=unsafe_value)
    elif field == "category":
        unsafe_page = replace(page, category=unsafe_value)
    else:
        unsafe_page = replace(page, title=unsafe_value)

    with pytest.raises(
        ValueError, match="(single-line|metadata|boundary|English|route)"
    ):
        render_aggregate((unsafe_page,))


def test_refresh_fetches_only_allowlisted_urls_and_is_byte_stable(
    tmp_path: Path,
) -> None:
    sources = (_source("b-page", "/en/b/"), _source("a-page", "/en/a/"))
    responses = {
        source.source_url: httpx2.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=_html(
                source.id,
                f'<p>{_prose(source.id)}</p><a href="/en/not-listed/">link</a>',
            ),
        )
        for source in sources
    }
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"

    requested = _refresh_with_responses(sources, first, responses)
    requested_reverse = _refresh_with_responses(
        tuple(reversed(sources)), second, responses
    )

    assert requested == [source.source_url for source in sources]
    assert requested_reverse == [source.source_url for source in reversed(sources)]
    assert first.read_bytes() == second.read_bytes()


def test_refresh_rejects_internal_redirect_without_requesting_target(
    tmp_path: Path,
) -> None:
    source = _source("safe-page", "/en/safe/")
    target = "https://finki.ukim.mk/en/redirected/"
    responses = {
        source.source_url: httpx2.Response(
            302,
            headers={"location": target},
        ),
        target: httpx2.Response(
            200,
            headers={"content-type": "text/html"},
            text=_html("Redirected", "<p>Target content.</p>"),
        ),
    }
    requested: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested.append(str(request.url))
        return responses[str(request.url)]

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    try:
        with pytest.raises((RuntimeError, ValueError), match="allowlisted|canonical"):
            refresh_reference((source,), tmp_path / "aggregate.md", client=client)
    finally:
        import anyio

        anyio.run(client.aclose)

    assert requested == [source.source_url]


@pytest.mark.parametrize(
    ("status", "content_type", "body", "location", "content_length"),
    [
        (500, "text/html", "server failure", None, None),
        (200, "application/pdf", "not html", None, None),
        (302, "text/html", "", "https://example.com/away/", None),
        (200, "text/html", "x", None, "5000001"),
    ],
)
def test_refresh_failures_leave_prior_aggregate_untouched(
    tmp_path: Path,
    status: int,
    content_type: str,
    body: str,
    location: str | None,
    content_length: str | None,
) -> None:
    source = _source("safe-page", "/en/safe/")
    output = tmp_path / "aggregate.md"
    output.write_text("prior aggregate\n", encoding="utf-8")
    headers = {"content-type": content_type}
    if location is not None:
        headers["location"] = location
    if content_length is not None:
        headers["content-length"] = content_length
    response = httpx2.Response(status, headers=headers, text=body)

    with pytest.raises((RuntimeError, ValueError)):
        _refresh_with_responses((source,), output, {source.source_url: response})

    assert output.read_text(encoding="utf-8") == "prior aggregate\n"


def test_refresh_rejects_malformed_content_type(tmp_path: Path) -> None:
    source = _source("safe-page", "/en/safe/")
    with pytest.raises(ValueError, match="HTML"):
        _refresh_with_responses(
            (source,),
            tmp_path / "aggregate.md",
            {
                source.source_url: httpx2.Response(
                    200,
                    headers={"content-type": "application/not-text/html"},
                    text=_html("Safe", "<p>Content.</p>"),
                )
            },
        )


def test_check_rejects_crlf_aggregate_without_newline_normalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source("safe-page", "/en/safe/")
    page = ReferencePage(
        source_id=source.id,
        source_url=source.source_url,
        canonical_url=source.canonical_url,
        language=source.language,
        category=source.category,
        content_kind=source.content_kind,
        last_verified=source.last_verified,
        title="Safe",
        body=_prose("Content"),
        content_sha256=sha256(f"Safe\n\n{_prose('Content')}".encode()).hexdigest(),
    )
    aggregate = tmp_path / "aggregate.md"
    aggregate.write_bytes(render_aggregate((page,)).replace("\n", "\r\n").encode())

    def fake_load_sources(_path: Path, *, today: date) -> tuple[ReferenceSource, ...]:
        return (source,) if today else ()

    monkeypatch.setattr(
        website_reference_module,
        "load_sources",
        fake_load_sources,
    )

    with pytest.raises(ValueError, match="LF-only"):
        website_reference_module.main(
            [
                "--check",
                "--sources",
                str(tmp_path / "sources.toml"),
                "--aggregate",
                str(aggregate),
            ]
        )


@pytest.mark.parametrize(
    "body",
    [
        "<p>\u003c!-- finki-static-page:start id=forged --\u003e</p>",
        "<p>\u003c!-- finki-static-page:end --\u003e</p>",
        "<p>```\n<!-- finki-static-page:end -->\n```</p>",
    ],
)
def test_refresh_rejects_aggregate_boundary_forgery(tmp_path: Path, body: str) -> None:
    source = _source("safe-page", "/en/safe/")
    with pytest.raises(ValueError, match="boundary|marker"):
        _refresh_with_responses(
            (source,),
            tmp_path / "aggregate.md",
            {
                source.source_url: httpx2.Response(
                    200,
                    headers={"content-type": "text/html"},
                    text=_html("Safe", body),
                )
            },
        )


@pytest.mark.parametrize(
    "body",
    [
        "",
        "<h2>Heading only</h2><h3>Still markup</h3>",
        "<p>Candidate code: 1234567</p>",
        "<p>same text</p>",
    ],
)
def test_refresh_rejects_title_only_or_sensitive_pages(
    tmp_path: Path, body: str
) -> None:
    source = _source("safe-page", "/en/safe/")
    sources: tuple[ReferenceSource, ...]
    responses: dict[str, httpx2.Response]
    if body == "<p>same text</p>":
        other = _source("other-page", "/en/other/")
        sources = (source, other)
        responses = {
            item.source_url: httpx2.Response(
                200,
                headers={"content-type": "text/html"},
                text=_html("Same", body),
            )
            for item in sources
        }
    else:
        sources = (source,)
        responses = {
            source.source_url: httpx2.Response(
                200,
                headers={"content-type": "text/html"},
                text=_html("Candidate" if "Candidate" in body else "Only title", body),
            )
        }

    with pytest.raises(ValueError, match="(empty|markup|identifier|duplicate)"):
        _refresh_with_responses(sources, tmp_path / "aggregate.md", responses)


def test_refresh_removes_images_and_verify_live_does_not_write(tmp_path: Path) -> None:
    source = _source("safe-page", "/en/safe/")
    output = tmp_path / "aggregate.md"
    responses = {
        source.source_url: httpx2.Response(
            200,
            headers={"content-type": "text/html"},
            text=_html("Safe", f'<p>{_prose("Text")}</p><img src="/en/image.png">'),
        )
    }
    _refresh_with_responses((source,), output, responses)
    before = output.read_bytes()
    assert "![" not in before.decode()
    assert "image.png" not in before.decode()

    client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda _request: httpx2.Response(
                200,
                headers={"content-type": "text/html"},
                text=_html("Safe", f"<p>{_prose('Text')}</p>"),
            )
        )
    )
    try:
        verify_live((source,), output, client=client)
    finally:
        import anyio

        anyio.run(client.aclose)
    assert output.read_bytes() == before


def test_verify_live_hash_mismatch_fails_without_writing(tmp_path: Path) -> None:
    source = _source("safe-page", "/en/safe/")
    output = tmp_path / "aggregate.md"
    _refresh_with_responses(
        (source,),
        output,
        {
            source.source_url: httpx2.Response(
                200,
                headers={"content-type": "text/html"},
                text=_html("Safe", f"<p>{_prose('Original content')}</p>"),
            )
        },
    )
    before = output.read_bytes()
    client = httpx2.AsyncClient(
        transport=httpx2.MockTransport(
            lambda _request: httpx2.Response(
                200,
                headers={"content-type": "text/html"},
                text=_html("Safe", f"<p>{_prose('Changed content')}</p>"),
            )
        )
    )
    try:
        with pytest.raises(ValueError, match="live hash differs"):
            verify_live((source,), output, client=client)
    finally:
        import anyio

        anyio.run(client.aclose)
    assert output.read_bytes() == before


def test_validate_aggregate_alias_checks_allowlist() -> None:
    assert validate_aggregate is not None


def test_committed_aggregate_matches_allowlist_exactly() -> None:
    aggregate_path = ROOT / "website-reference" / "finki-static-pages.md"
    sources = load_sources(SOURCES, today=date(2026, 9, 7))
    text = aggregate_path.read_text(encoding="utf-8", newline="")

    pages = validate_aggregate(text, sources)

    assert len(pages) == len(sources)
    assert [page.source_id for page in pages] == [source.id for source in sources]
    assert text.count("<!-- finki-static-page:start id=") == len(sources)
    assert text.count("<!-- finki-static-page:end -->") == len(sources)
    assert text == render_aggregate(pages)


def test_committed_aggregate_has_only_qualified_source_contract() -> None:
    sources = load_sources(SOURCES, today=date(2026, 9, 7))
    pages = validate_aggregate(
        (ROOT / "website-reference" / "finki-static-pages.md").read_text(
            encoding="utf-8"
        ),
        sources,
    )
    page_by_id = {page.source_id: page for page in pages}
    rejected_ids = {
        "finki-legal-acts",
        "student-service",
        "thesis-procedure",
        "course-enrollment",
        "institutional-contact",
    }

    assert set(page_by_id) == {source.id for source in sources}
    assert not rejected_ids.intersection(page_by_id)
    assert all(source.content_selectors for source in sources)
    assert all(
        page.source_url == source.source_url and page.category == source.category
        for source in sources
        for page in [page_by_id[source.id]]
    )
