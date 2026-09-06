# Expanded FINKI Website Reference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand PR #10 into a safely curated set of evergreen FINKI HTML pages whose extracted bodies exclude template navigation and other disallowed material.

**Architecture:** The TOML allowlist owns both direct source URLs and approved CSS content selectors. The generator fetches only those exact URLs, extracts a configured article container, sanitizes it through the existing Markdown path, and fails closed when body quality is too navigation-shaped. A manually reviewed aggregate remains the only tracked content artifact.

**Tech Stack:** Python 3.14, `selectolax`, `markdownify`, `httpx2`, Pydantic, pytest, Ruff, MyPy.

**Spec:** `docs/superpowers/specs/2026-09-06-expanded-finki-website-reference-design.md`

## Global Constraints

- Work in `E:\finki-hub-documents\.worktrees\curated-website-reference` on existing PR branch `feat/curated-website-reference`.
- Add only explicit, direct HTTPS FINKI HTML source URLs. Prefer `finki.ukim.mk` / `www.finki.ukim.mk`; use `oldsite.finki.ukim.mk` only as a direct fallback.
- Retain a fixed allowlist: no crawler, REST inventory, recursive link traversal, PDFs/assets, external hosts, or unapproved redirects.
- Do not change the broad crawler's global host policy. Curated host handling stays opt-in in `website_reference` and its `fetch_public` call.
- Include only evergreen study guides/programmes, student procedures/services, institutional/about text, legal HTML indexes, and institutional contact text after manual review.
- Exclude entire sources containing announcements, calls, quotas, deadlines, rankings, results, schedules, defenses, staff/person directories, financial/bank data, jobs, projects, archives, feeds, assets, or candidate identifiers. Do not redact article text to make a source eligible.
- Preserve stable ID, original URL, canonical URL, language, category, last review date, selector list, visible aggregate metadata, normalized SHA-256, deterministic LF-only output, atomic writes, privacy gates, and duplicate detection.
- Preserve the current two reviewed pages unless a replacement has passed the same tests and manual review.
- HTML pages only. Reviewed legal PDFs remain in their existing corpus pipeline. Do not change chatbot/retrieval ingestion.

---

### Task 1: Selector-aware Markdown extraction

**Files:**
- Modify: `tools/website_markdown.py`
- Modify: `tests/test_website_markdown.py`

**Interfaces:**
- Extend `document_from_page` to `document_from_page(html: str, url: str, *, content_selectors: Sequence[str] | None = None) -> WebsiteDocument`.
- When `content_selectors` is supplied, evaluate selectors in listed order and require a matching node; raise `WebsiteContentError` when no configured selector matches. Existing callers without selectors keep the current generic root selection.

- [ ] Write a failing test that passes a page with a navigation-heavy `<main>` and a nested `#article-body`; assert only the configured `#article-body` text reaches `document.markdown`.
- [ ] Run `uv run --locked pytest -q tests/test_website_markdown.py::test_document_from_page_uses_configured_content_selector` and confirm it fails because the keyword argument is unsupported.
- [ ] Write a failing test for ordered selectors: a missing first selector and matching second selector must extract the second node; a list of unmatched selectors must raise `WebsiteContentError` with the source URL.
- [ ] Implement `_content_root(parser, content_selectors=...)` so configured candidates are selected before sanitization. Retain generic `main` → `article` → `body` fallback only when `content_selectors is None`.
- [ ] Run `uv run --locked pytest -q tests/test_website_markdown.py`; confirm existing rendered-page safety/link tests remain green.
- [ ] Commit `feat: extract curated page content selectors`.

### Task 2: Selector allowlist contract and navigation-quality gates

**Files:**
- Modify: `tools/website_reference.py`
- Modify: `tests/test_website_reference.py`
- Modify: `tests/test_website_http.py`
- Modify: `pyproject.toml` only if newly added test/module paths need explicit MyPy registration

**Interfaces:**
- Extend `ReferenceSource` with `content_selectors: tuple[str, ...]`.
- Require TOML key `content_selectors` as a non-empty list of safe single-line CSS selectors; it is never rendered as aggregate metadata.
- Add `extract_reference_document(html: str, source: ReferenceSource) -> WebsiteDocument` as the curated-only adapter that calls `document_from_page(..., content_selectors=source.content_selectors)` using a compatibility URL only when required by the shared normalizer.
- Add `has_substantive_prose(markdown: str) -> bool` and `is_navigation_shaped(markdown: str) -> bool` helpers; both must be true/false respectively before a page can be rendered.

- [ ] Write failing allowlist tests that reject a missing, empty, non-string, CR/LF-containing, or aggregate-marker-bearing `content_selectors` field.
- [ ] Write failing route tests accepting direct `/mk/` routes on `finki.ukim.mk`, `www.finki.ukim.mk`, and `oldsite.finki.ukim.mk`, while rejecting lookalikes, wrong language prefixes, queries, assets, and every redirect target not exactly canonical.
- [ ] Write failing mocked refresh tests using `<main>` navigation plus `#article-body` prose. Assert the configured selector is used, no linked URL is requested, and the generated body excludes navigation labels.
- [ ] Write failing gate tests for link-list output with no sentence-like prose, repeated navigation labels, and prose-heavy article content. Assert the first two abort refresh without replacing a prior aggregate and the prose-heavy page succeeds.
- [ ] Implement strict TOML parsing and source validation; derive allowed hosts from each source canonical URL only for the curated `fetch_public` call, preserving global crawler policy.
- [ ] Implement curated conversion adapter, selector use, and deterministic quality gates. Define metrics as: at least 160 non-link Unicode letters/digits, at least one prose line of 40+ non-link characters, and fewer link-label characters than prose characters. Treat repeated normalized non-link labels occurring three or more times as navigation-shaped.
- [ ] Run `uv run --locked pytest -q tests/test_website_reference.py tests/test_website_http.py tests/test_website_markdown.py`, Ruff, formatter, and MyPy; commit `feat: validate curated website content bodies`.

### Task 3: Curate current-host HTML sources and aggregate

**Files:**
- Modify: `website-reference/sources.toml`
- Modify: `website-reference/finki-static-pages.md`
- Modify: `README.md`
- Modify: `tests/test_website_reference.py`

**Interfaces:**
- Every source TOML table supplies direct `source_url`/`canonical_url`, `language = "mk"`, category, review date, and one or more reviewed content selectors.
- The aggregate has exactly one parsed `finki-static-page` block per final source and remains validated by `validate_aggregate`.

- [ ] Start from the bounded current-host candidate set: Study Guide; KNI, IKI, KE, INFO, and KN-3 programme pages; student service; student practice; thesis procedure; course-enrollment rules; electronic-document instructions; About Faculty; Strategic Goals; and institutional contact. Do not add PDFs, annual report indexes, admissions hubs, or a candidate that fails the global constraints.
- [ ] For each candidate, inspect its fetched HTML without following links, record a page-specific content selector, and run a one-source temporary refresh. Remove the candidate if the extracted body has disallowed content, weak prose, sensitive identifiers, or a stale historical-only purpose that cannot be made clear by its category.
- [ ] Update `sources.toml` only with sources that pass direct HTTP/content/manual review. Retain the existing two pages unless superseded by an approved equivalent.
- [ ] Add a failing committed-aggregate regression asserting every configured source has a non-empty selector list, every aggregate source/category exactly matches TOML, and the aggregate contains no rejected candidate ID.
- [ ] Run `uv run --locked python -m tools.website_reference --refresh`; inspect every generated block for navigation text, source correctness, stale dates, quotas/results, personal data, and unapproved links. Remove failed sources and repeat only for remaining allowlisted URLs.
- [ ] Update README with current-host preference, source-selector review policy, final retained page count/categories, and the existing no-crawl/PDF/authority/freshness disclosures.
- [ ] Run `--check`, `--verify-live`, all focused reference/HTTP/Markdown tests, the full suite, Ruff, formatter, MyPy, `python tools/preprocess.py audit`, and `git diff --check`; commit `docs: expand curated FINKI website reference`.

### Task 4: Review and update PR #10

**Files:**
- Review all changed files.

- [ ] Inspect `git status`, `git diff --check`, full diff from `origin/main`, branch log, and PR file list; ensure only the approved specification, source contract/tool/tests, corpus, and documentation changed.
- [ ] Request independent review of selector safety, host/redirect confinement, quality-gate false positives, current-versus-legacy source selection, source body quality, and aggregate provenance.
- [ ] Resolve every Critical/Important finding with focused tests and scoped re-review.
- [ ] Push the updated feature branch and verify PR #10 reflects the expanded corpus plus validation evidence. Preserve the PR as open for human review.
