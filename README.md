# FINKI Hub / Documents

Source-of-truth corpus for the [`finki-hub/chat-bot`](https://github.com/finki-hub/chat-bot) RAG: official FINKI / UKIM governance documents (laws, rulebooks, statutes, procedures), converted to Markdown and structured by articles (членови). The bot retrieves from these chunks alongside the FAQ. Keeping them here makes every revision a reviewable pull request.

## Layout

```
processed/   reviewed Markdown — the tracked corpus (one file per document)
raw/         original PDFs/DOCX — the corpus source files, tracked here
tools/       offline CLI: preprocess.py + docpipe.py + website_content.py
website/     ignored local website snapshot created by website_content.py
rag-corpus/  optional local destination for an exported chat-bot RAG bundle
```

Both the originals (`raw/`) and the reviewed Markdown (`processed/`) are versioned here — this repo is the source of truth. Cloudflare R2 is an optional downstream mirror of the originals; chunks and embeddings live in the chat-bot's Postgres (regenerable from the Markdown at any time).

## Document metadata

Every reviewed file starts with one HTML comment containing pipe-separated metadata. The required currentness fields are:

- `authority_url` — a reachable HTTPS URL on an approved FINKI, UKIM, competent government-authority, or Official Gazette host. Prefer the direct official file; when no stable direct file exists, use the official authority, archive, or index page that establishes the document's provenance.
- `document_date` — the best authority-backed primary date: ISO `YYYY`, `YYYY-MM`, or `YYYY-MM-DD`; academic year `YYYY/YYYY`; Gazette issue `N/YYYY`; or `unresolved` when the document does not establish one.
- `date_kind` — what `document_date` means: `adopted`, `published`, `issued`, `coverage_period`, or `unresolved`.
- `date_precision` — `day`, `month`, `year`, `academic_year`, `gazette_issue`, or `none`.
- `date_source` — where the date came from: `document_text`, `official_gazette`, `official_webpage`, or `unresolved`.
- `date_confidence` — `high`, `medium`, `low`, or `none`.
- `current_status` — the reviewed legal or operational status; this must express uncertainty instead of assuming that a published file is current.
- `last_verified` — the ISO date on which a human or research pass last checked the authority evidence. It is not the document's legal date.

Use optional typed fields such as `issued`, `published`, `effective_from`, `amended_through`, `valid_until`, or `coverage_period` when they add meaning beyond the primary date. File creation, modification, export, and upload timestamps are never legal issuance evidence; they may only be recorded separately as weak provenance. See [METADATA.md](METADATA.md) for the corpus evidence ledger and allowed status values.

An optional `assistant_note` carries internal guidance for the chat-bot when a source must stay as published but misleads on its own. It must be one paragraph of at most 500 characters with no Discord mention or channel tokens (and, in a processed header, no `|`). It is passed through to ingest metadata unchanged; the chat-bot gives it to the model and never shows it to users.

The UKIM study rules (Gazette 417/2019) and separate amendment (607/2022) have [provenance, transitional provisions and conflict evidence](METADATA.md#ukim-study-rules-provenance-scope-and-conflicts-2026-10-16) recorded in the ledger. The exam-objection and grade-entry conflicts are handled in the chat-bot: the FAQ „Закаснет внес на оцена и запишување семестар без оцени“ states that neither procedure is applied in practice, and its assistant note tells the model not to present either regulation's version as the procedure to follow. Both additions are approved for production import from release `440d77c`.

## Working with it

Run from the repo root with [`uv`](https://github.com/astral-sh/uv):

```bash
uv run --with pymupdf --with pypdf --with python-docx --with anthropic \
       --with langchain-text-splitters --with boto3 python tools/preprocess.py <cmd>
```

- `extract` / `ocr <pdf>` — convert originals into `processed/*.md`. **Human-review every file against its original before ingesting** — these are legal texts.
- `upload [dir]` — mirror the originals to Cloudflare R2 for backup / public serving (optional; needs the `R2_*` env vars).
- `ingest [url]` then `fill [url]` — push the Markdown to the chat-bot `/documents` API and embed it. Idempotent by name (the filename stem); a revision under the **same filename** re-embeds only the changed document. Needs `API_KEY`.
- `sync [url]` then `fill [url]` — like `ingest`, but also **prunes** any stored document whose file was removed or **renamed**, so the API mirrors `processed/`. Use this whenever documents are renamed or retired. R2 originals are kept as an archive (orphaned keys are reported, not deleted).
- `audit` — validate all reviewed headers, including the `authority_url` scheme and official host, and report the corpus status distribution without contacting external services. Check URL reachability separately when authority evidence is reviewed or updated.

Document API commands accept loopback URLs by default. For a remote API, set
`DOCUMENT_API_ALLOWED_ORIGINS` to a comma-separated list of trusted origins
(scheme, hostname, and optional port), matching the URL passed to the command.
Use HTTPS for remote deployments. API requests do not follow redirects or use
environment-configured proxies, so the API key is not forwarded to another
destination.

## Public website content

Generate a fresh Markdown snapshot of the public FINKI website with:

```bash
uv run --locked python -m tools.website_content --output website
```

The generator combines the public WordPress REST API with a rendered-page crawl because staff listings, archive pages, English pages, subjects, and study programmes are not represented completely by REST records. It follows only canonical `finki.ukim.mk` HTML routes, streams responses before accepting HTML, and limits concurrent requests to four. Generated representations that publish seven-digit or `FIN`-prefixed identifiers in candidate context, or explicitly label values as the first seven identification-number digits, are excluded from every output surface so public candidate lists are not republished as a durable bulk dataset. When both REST and rendered representations are available, a match in either excludes the canonical URL.

Every run replaces an empty directory or a prior generator-owned snapshot with three deterministic surfaces. It refuses foreign directories and link-bearing output trees before modifying them:

- `website/documents/{language}/*.md` — one source-attributed Markdown file per canonical page or REST record.
- `website/manifest.json` — generator ownership, source URLs, aliases, WordPress identities, language, modification metadata, REST totals, crawled-page count, and whether `--max-pages` truncated the crawl.
- `website/finki-website.md` — the same documents combined into one portable Markdown file.

For safety, the generator writes a complete sibling staging snapshot before moving an existing owned snapshot into `.website-recovery-*` and installing the replacement. If installation fails, it restores the prior snapshot when possible and leaves staging or recovery artifacts available for inspection instead of recursively deleting them. The generator is intentionally single-writer; do not run concurrent commands against the same output directory.

Use `--max-pages 20` for a quick network smoke test. For a complete local audit, run the full command and require `crawl_truncated` to be `false` in `manifest.json`. Generated website snapshots are ignored and must not be committed: a complete crawl includes thousands of unreviewed, duplicated, historical, and time-sensitive pages that do not satisfy this repository's corpus standards. Re-running removes stale generated files; it does not modify `raw/` or the human-reviewed legal corpus in `processed/`.

Website output is ephemeral informational source material, not reviewed legal text. Do not pass it to `preprocess.py ingest` or `sync`, or track a curated subset, until the chat-bot has a dedicated website-ingestion contract with default-deny relevance, currentness, and conflict-resolution rules.

### RAG corpus release export

The repository's reviewed content is the complete source authority for a fast
RAG export: every Markdown document under `processed/` and every page block in
the checked-in `website-reference/` aggregate is discovered automatically.
There is no separate allowlist or manifest, and export eligibility never
depends on the wall clock or a document's currentness status. Raw PDFs/DOCX,
code, tests, build configuration, generated website snapshots, and exporter
artifacts are not emitted; raw files remain provenance inputs for processed
documents.

Run the release export from a clean, pinned checkout. The exporter has no
filesystem output-path option: it emits the complete bundle on stdout and
keeps all source/release reports on stderr. Capture stdout into the external
release directory chosen by the operator:

```bash
uv run --locked python -m tools.rag_corpus_bundle
tmp="$(mktemp ../release-bundle.json.XXXXXX)"
if uv run --locked python -m tools.rag_corpus_bundle --release \
    >"$tmp" 2>../release-bundle.report; then
  mv -n "$tmp" ../release-bundle.json
else
  rm -f "$tmp"
  exit 1
fi
uv run --locked pytest tests/test_rag_corpus_fast_export.py -q
```

The final export is credential-free, atomically written, and emits stable
canonical JSON. The command prints `bundle_sha256`, the SHA-256 of the exact
JSON bytes; provide that value to the importer as its trusted expected bundle
hash. Every discovered corpus file and every referenced raw provenance file
must be tracked in, byte-for-byte identical to, and present in `HEAD`; raw
identities and bytes contribute to `source_tree_sha256`. The exporter requires
`raw/`, rejects traversal, external, and symlinked corpus/provenance inputs,
and derives the eligible corpus path inventory from `HEAD`, rejecting sparse
or skip-worktree omissions and unexpected materialized files. It rejects any
dirty repository (including unrelated files) for release. `bundle_sha256` is
reported on stderr, so redirected stdout remains the exact deterministic JSON
artifact. The caller owns final placement/atomic installation in the external
directory (the example stages and atomically installs with `mv -n`); the
exporter never opens or overwrites a caller-provided path and does not crawl,
fetch, or reprocess raw files.

### Curated website reference

The separate `website-reference/` corpus is classified as `official_website_informational`: a deliberately narrow, 28-page manually reviewed snapshot of public FINKI pages, lower authority than the reviewed legal documents in `processed/`. Directly selected pages may include admissions information, dates or quotas, public institutional contacts or person listings, payment/account details, and public PDF links. Each source declares an explicit `content_kind`: 22 prose pages, two structured pages, three person lists, and one link catalog. A person-list page must contain multiple distinct human-name labels linked to official FINKI profile routes; validation rejects the whole page if the roster is empty, duplicate-only, boilerplate, or navigation-shaped. Visible role text and published email links are preserved.

Each source has an explicitly reviewed CSS selector and only exact source-page URLs are fetched. The refresh never crawls or fetches linked documents, PDFs, or assets; it retains only sanitized links found on directly selected pages. Candidate identifiers, undisclosed or private data, and asset ingestion remain prohibited. Every change requires manual review for upstream drift and suitability.

A source may also set `assistant_note` (see [Document metadata](#document-metadata)). It is copied into the page's aggregate metadata, outside the page text and its `sha256`, and into the page's ingest metadata.

FINKI website content is publicly attributed to FINKI and remains **all rights reserved**; this repository's copy is for internal informational/reference use, not republication or redistribution of the upstream material. The generator fetches only exact URLs in `website-reference/sources.toml`, never follows page links, never fetches PDFs/assets or external hosts, and permits only exact source-scoped canonical redirects. Use the bounded commands below from the repository root:

```bash
uv run --locked python -m tools.website_reference --refresh
uv run --locked python -m tools.website_reference --check
uv run --locked python -m tools.website_reference --verify-live
```

Custom `--sources` and `--aggregate` CLI paths must stay inside this repository;
parent traversal, symlinks, junctions, and nonregular input files are rejected.

Reviewer workflow: inspect every generated `finki-static-page` block, confirm the visible source and canonical URLs, check for prohibited or stale material, run `--check` and `--verify-live`, and review the resulting diff before accepting a change. Page-level ingestion is deferred until the chat-bot has a dedicated contract for relevance, currentness, provenance, conflict resolution, and this source class. The full `website/` snapshots remain ignored and must not be ingested; they are an unreviewed crawl, not a curated reference corpus.

## License

MIT — see [LICENSE](LICENSE).
