# FINKI Hub / Documents

Source-of-truth corpus for the [`finki-hub/chat-bot`](https://github.com/finki-hub/chat-bot) RAG: official FINKI / UKIM governance documents (laws, rulebooks, statutes, procedures), converted to Markdown and structured by articles (членови). The bot retrieves from these chunks alongside the FAQ. Keeping them here makes every revision a reviewable pull request.

## Layout

```
processed/   reviewed Markdown — the tracked corpus (one file per document)
raw/         original PDFs/DOCX — the corpus source files, tracked here
tools/       offline CLI: preprocess.py + docpipe.py
```

Both the originals (`raw/`) and the reviewed Markdown (`processed/`) are versioned here — this repo is the source of truth. Cloudflare R2 is an optional downstream mirror of the originals; chunks and embeddings live in the chat-bot's Postgres (regenerable from the Markdown at any time).

## Working with it

Run from the repo root with [`uv`](https://github.com/astral-sh/uv):

```bash
uv run --with pymupdf --with pypdf --with python-docx --with anthropic \
       --with langchain-text-splitters --with boto3 --with posthog python tools/preprocess.py <cmd>
```

- `extract` / `ocr <pdf>` — convert originals into `processed/*.md`. **Human-review every file against its original before ingesting** — these are legal texts.
- `upload [dir]` — mirror the originals to Cloudflare R2 for backup / public serving (optional; needs the `R2_*` env vars).
- `ingest [url]` then `fill [url]` — push the Markdown to the chat-bot `/documents` API and embed it. Idempotent by name (the filename stem); a revision under the **same filename** re-embeds only the changed document. Needs `API_KEY`.
- `sync [url]` then `fill [url]` — like `ingest`, but also **prunes** any stored document whose file was removed or **renamed**, so the API mirrors `processed/`. Use this whenever documents are renamed or retired. R2 originals are kept as an archive (orphaned keys are reported, not deleted).

### Analytics (optional)

`ingest`/`sync` emit a `document_ingested` PostHog event per document (metadata only — `doc_id`, `chunk_count`, `bytes`, `source`; never document text). Set `POSTHOG_KEY` (and optionally `POSTHOG_HOST`, default `https://eu.i.posthog.com`) to enable; leave `POSTHOG_KEY` unset for a no-op. The fleet's public ingest key is `phc_xXEqLMnYeDPuXA6HHwuasQMdSufDGryS8vZZuHmu9Qwd`.

## License

MIT — see [LICENSE](LICENSE).
