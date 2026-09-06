# Expanded FINKI Website Reference Design

## Goal

Expand PR #10 from its two-page safety baseline into a curated, reviewable set of evergreen FINKI HTML pages suitable for later page-level retrieval. The corpus remains documents-only: this work does not ingest anything into the chatbot.

## Scope and source policy

- Include only explicit, direct, public FINKI HTML pages with useful evergreen body text.
- Prefer current `finki.ukim.mk` / `www.finki.ukim.mk` routes. Use direct `oldsite.finki.ukim.mk` routes only when there is no equivalent current page.
- Keep a fixed TOML allowlist. Never crawl, enumerate REST content, follow page links, or fetch an asset, PDF, external host, or unapproved redirect target.
- Select pages from study guides and programme descriptions, stable student procedures/services, institutional/about pages, legal HTML indexes, and institutional contact details.
- Exclude entire pages containing announcements, calls, quotas, deadlines, rankings, results, schedules, defenses, staff/person directories, financial/bank data, jobs, projects, archives, feeds, or candidate identifiers. Do not redact article body text merely to make a source eligible.
- PDFs remain out of scope; reviewed legal documents continue through their existing pipeline.

## Allowlist contract

Each source retains its stable ID, visible source/canonical URLs, language, category, review date, and adds an ordered non-empty `content_selectors` list.

The selector list is part of the review contract: it identifies the page-specific article container to extract. The generator must not accept a generic `main`, `article`, or `body` fallback for an expanded source if all configured selectors fail quality checks. This fails closed rather than publishing template navigation as content.

Current and legacy FINKI hosts are allowed only in the curated generator through explicit source validation and explicit HTTP host parameters. The broad crawler host policy remains unchanged. Cross-host redirects, including current-to-legacy redirects, remain rejected before their target is requested.

## Extraction and quality gates

The Markdown conversion path accepts configured selector candidates and evaluates them in order. For each candidate it removes shared page chrome, images, scripts, forms, and unsafe links before conversion. It chooses the first candidate that passes all gates; otherwise refresh fails for that source without replacing the aggregate.

Gates retain existing privacy, duplicate, aggregate-boundary, content-type, size, and headings-only checks and add navigation-shape checks:

- minimum non-link prose characters and sentence-like prose;
- maximum link-label-to-prose ratio;
- repeated short-label detection;
- rejection of known navigation/skip/menu-only output.

Thresholds are fixture-backed and conservative. They do not fetch extra URLs or attempt semantic redaction.

## Curation workflow

1. Build a bounded candidate list from official navigation.
2. Capture/review each candidate’s existing HTML structure to choose its content selector.
3. Add fixture tests showing the selected body is retained and navigation/template content is excluded.
4. Add the candidate to the allowlist only after its direct response, generated body, and policy suitability are manually reviewed.
5. Run atomic refresh, offline check, and non-writing live verification.
6. Review the aggregate section-by-section before committing it to PR #10.

The final page count is determined by qualification, not a numerical target. The PR must document every retained category and why potentially useful candidates were excluded.

## Testing and verification

Tests cover current-host and legacy-host fixtures, selector ordering, selector failure, navigation-dump rejection, link-heavy output rejection, direct allowlist fetches, host and redirect rejection, deterministic aggregate rendering, and aggregate/allowlist equality.

Before updating the PR, run the focused reference/HTTP/Markdown suites, the full test suite, Ruff, formatting, MyPy, corpus audit, offline check, and bounded live verification. New live pages require a manual aggregate review after the final refresh.

## Non-goals

- No PDF extraction.
- No whole-site crawler or automatic discovery.
- No bespoke page-body redaction policy.
- No changes to chatbot, retrieval, embeddings, database, or source-authority ordering.
