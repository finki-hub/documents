# FINKI Hub / Documents

Source-of-truth corpus for the [`finki-hub/chat-bot`](https://github.com/finki-hub/chat-bot)
RAG: official FINKI / UKIM governance documents (laws, rulebooks, statutes, procedures),
converted to Markdown and structured by articles (членови). The bot retrieves from these chunks
alongside the FAQ. Keeping them here makes every revision a reviewable pull request.

## Layout

```
processed/   reviewed Markdown — the tracked corpus (one file per document)
raw/         local staging for originals (gitignored; archived to R2)
tools/       offline CLI: preprocess.py + docpipe.py
```

Markdown lives here in git; the original PDFs/DOCX go to Cloudflare R2; chunks and
embeddings live in the chat-bot's Postgres (regenerable from the Markdown at any time).

## Working with it

Run from the repo root with [`uv`](https://github.com/astral-sh/uv):

```bash
uv run --with pymupdf --with pypdf --with python-docx --with anthropic \
       --with langchain-text-splitters --with boto3 python tools/preprocess.py <cmd>
```

- `extract` / `ocr <pdf>` — convert originals into `processed/*.md`.
  **Human-review every file against its original before ingesting** — these are legal texts.
- `upload [dir]` — archive originals to R2 (needs the `R2_*` env vars).
- `ingest [url]` then `fill [url]` — push the Markdown to the chat-bot `/documents` API and
  embed it. Idempotent by name; a revision re-embeds only the changed document. Needs `API_KEY`.

## License

MIT — see [LICENSE](LICENSE).
