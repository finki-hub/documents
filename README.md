# FINKI Hub / Documents

Source-of-truth corpus for the [`finki-hub/chat-bot`](https://github.com/finki-hub/chat-bot) RAG: official FINKI / UKIM governance documents (laws, rulebooks, statutes, procedures), converted to Markdown and structured by articles (членови). The bot retrieves from these chunks alongside the FAQ. Keeping them here makes every revision a reviewable pull request.

## Layout

```
processed/   reviewed Markdown — the tracked corpus (one file per document)
raw/         original PDFs/DOCX — the corpus source files, tracked here
tools/       offline CLI: preprocess.py + docpipe.py
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

## License

MIT — see [LICENSE](LICENSE).
