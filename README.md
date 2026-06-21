# FINKI Hub / Documents

Source-of-truth corpus for the [`finki-hub/chat-bot`](https://github.com/finki-hub/chat-bot)
RAG. These are the official **governance documents** of FINKI / UKIM — laws,
rulebooks (правилници), statutes (статути), procedures (процедури), codes and
strategies — converted to clean Markdown and structured by членови (articles).

The chat bot answers from two retrieval sources, searched together in one reranked
pass: the **FAQ** (the `question` table in the chat-bot DB) and the **chunks of these
documents** (the `document` / `chunk` tables). This repo is the tracked, reviewable
home of the latter; the bot never reads this repo directly — it ingests the Markdown
through the chat-bot API (see [Ingestion](#ingestion)).

Keeping the corpus in its own repo means a document revision (a law is amended, a
rulebook is replaced) is a normal pull request with a readable diff, reviewed and
released on its own cadence — independent of the application code.

## Where each artifact lives

- **Reviewed Markdown → git, here** (`processed/*.md`). Small, diffable, the **source
  of truth for ingest**. Each file starts with an HTML-comment header carrying its
  title and original source filename.
- **Original PDFs/DOCX → Cloudflare R2** (off-git, for provenance + re-processing).
  `raw/` is a local **gitignored** staging area for files before they're uploaded;
  each document's R2 key is stored in its `metadata` at ingest time.
- **Chunks + embeddings → PostgreSQL / pgvector** (the chat-bot's runtime store, fully
  regenerable from the Markdown here via ingest + fill).

## Layout

```
processed/   reviewed Markdown — the tracked corpus (one file per document)
raw/         local staging for originals (gitignored; archived to R2)
tools/       offline content-prep CLI (preprocess.py + docpipe.py)
.github/     ingest workflow (CI on merge)
```

## Pipeline

The tooling is offline-only and never runs in the chat-bot request path. Run it from
the repo root with ephemeral dependencies via [`uv`](https://github.com/astral-sh/uv):

```bash
uv run --with pymupdf --with pypdf --with python-docx --with anthropic \
       --with langchain-text-splitters --with boto3 \
  python tools/preprocess.py <command>
```

1. **Stage** originals into `raw/` (or point the tools at any folder).
2. **Convert** to Markdown — verbatim; illegible text becomes `[нечитливо]`:
   - `preprocess.py extract` — Tier A: clean text-layer PDFs + DOCX (deterministic, free).
   - `preprocess.py ocr <pdf> [pages]` — Tier B: scanned / legacy-font PDFs via Claude vision.
3. **Human-review** each `processed/*.md` against its original. These are legal texts —
   extraction/OCR errors change meaning. This step is not optional.
4. **Archive** originals to R2: `preprocess.py upload [raw_dir]`
   (needs `R2_ACCOUNT_ID`/`R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`).
5. **Ingest + embed** (or let CI do it — see below):
   - `preprocess.py ingest [api_url]` — POST each `processed/*.md` to `/documents`
     (chunked server-side, idempotent by name, R2 key attached to metadata).
   - `preprocess.py fill [api_url]` — drive `/documents/fill` for all models over chunks
     still missing embeddings. Both need `API_KEY`.

### Revisions

Ingest is keyed by document `name` (the filename stem). Re-ingesting an **unchanged**
file is a no-op (the API short-circuits on a content hash); a **changed** file fully
replaces the old document and its chunks. `fill` only embeds chunks whose embedding
columns are still `NULL`, so a revision re-embeds just the changed document — not the
whole corpus.

## Ingestion via CI

[`.github/workflows/ingest.yaml`](.github/workflows/ingest.yaml) runs `ingest` then
`fill` on every push to `main` that touches `processed/**`, and on manual dispatch.
Configure once under **Settings → Secrets and variables → Actions**:

- variable `INGEST_API_URL` — the chat-bot API base URL (no trailing slash)
- secret `INGEST_API_KEY` — the API's `API_KEY`

If the API is only reachable on a private network, point the job at a **self-hosted
runner** that can reach it (change `runs-on` in the workflow).

## Chunking

Chunks are sized to ~1300–1650 chars (~380–420 tokens on the `multilingual-e5-large`
tokenizer, measured at ~4.36 chars/token on this Macedonian corpus); e5's 512-token
window is the binding constraint across the configured embedding models. The chunker
itself lives in the chat-bot API (`app/llms/chunking.py`) and runs at ingest time;
`tools/docpipe.py` here is a standalone harness for validating extraction + chunk sizes.

## License

This project is licensed under the terms of the MIT license.
