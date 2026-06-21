"""
Offline preprocessing for source-of-truth documents. Three tiers:
  - Tier A: clean text-layer PDFs + DOCX -> deterministic extraction (free, no API).
  - Tier B: scanned / corrupted-font PDFs -> Claude vision OCR (needs ANTHROPIC_API_KEY).
  - Ingest/fill: POST the reviewed Markdown to /documents, then drive /documents/fill.

Run from the repository root. Usage (ephemeral deps via uv):
  uv run --with pymupdf --with pypdf --with python-docx --with anthropic --with langchain-text-splitters --with boto3 \
      python tools/preprocess.py extract           # Tier A -> processed/
      python tools/preprocess.py ocr <pdf> [pages] # Tier B -> processed/
      python tools/preprocess.py upload [raw_dir]  # archive originals to R2 (provenance)
      python tools/preprocess.py ingest [api_url]  # POST processed/*.md to /documents
      python tools/preprocess.py fill [api_url]    # drive /documents/fill (all models, missing chunks)
      python tools/preprocess.py sync [api_url]    # ingest + prune renamed/removed docs (folder = source of truth)

Always HUMAN-REVIEW processed/*.md against the originals before ingesting —
these are legal texts and OCR/extraction errors change meaning.

ingest/fill need API_KEY; upload needs R2 creds (offline only — never used by the API runtime):
  R2_ACCOUNT_ID (or R2_ENDPOINT), R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, API_KEY
"""

import base64
import os
import re
import sys
from pathlib import Path

RAW_DIR = Path("raw")
OUT_DIR = Path("processed")

# Administrative / low student-FAQ-value documents excluded from the RAG corpus.
EXCLUDE = (
    "odluka_za_plati",
    "sistematizacija_finki",
    "finalen_izveshtaj",
    "lista na posrednici",
    "podatoci_od_javen_karakter",
)

# Documents whose text layer is unusable (scanned or legacy-font) -> Tier B vision OCR.
NEEDS_OCR = (
    "statut_i_delovnik",
    "pravilnik_za_standardite",
)

# Human-readable titles (used in chunk embeddings + citations); falls back to the
# prettified filename for anything not listed.
TITLES = {
    "264_statut_ukim-6.6.2019": "Статут на Универзитетот „Св. Кирил и Методиј“ во Скопје",
    "Pravilnik_studii_prv_vtor_ciklus_FINKI": "Правилник за студии на прв и втор циклус (ФИНКИ)",
    "Pravilnik_doktorski_studii_po_stara_programa": "Правилник за докторски студии (стара програма)",
    "Zakon_za_formiranje_na_FINKI": "Закон за основање на ФИНКИ",
    "zakon_za_visokoto_obrazovanie_nov": "Закон за високото образование",
    "cenovnik_finki_2024-25-2": "Ценовник на ФИНКИ 2024/25",
    "etichki_kodeks_ukim-finki": "Етички кодекс на УКИМ/ФИНКИ",
    "delovnik_za_rabota_-glasnik-682": "Деловник за работа",
    "pravilnik-za-obezbeduvanje-kvalitet-na-univerzitetot-sv.-kiril-i-metodij-vo-skopje": "Правилник за обезбедување квалитет (УКИМ)",
    "pravilnik-za-rabota-na-ovlasteno-lice-za-prierm-na-prijavi-na-korupcija": "Правилник за работа на овластено лице за прием на пријави за корупција",
    "procedura_za_prijava_na_korupcija": "Процедура за пријава на корупција",
    "procedura_za_zalbi_na_finki": "Процедура за жалби (ФИНКИ)",
    "procedura_za_zashtiteno_vnatreshno_prijavuvanje_na_fakultet_za_informatichki_nauki_i_kompjutersko_inzhenerstvo_skopje": "Процедура за заштитено внатрешно пријавување (ФИНКИ)",
    "statut_na_fakultetskoto_studentsko_sobranie_na_fakultetot_za_informatichki_nauki_i_kompjutersko_inzhenerstvo_-_skopje": "Статут на Факултетското студентско собрание (ФИНКИ)",
    "strategija_za_obezbeduvanje_kvalitet_na_univerzitetot_sv._kiril_i_metodij_vo_skopje_2024_-_2029": "Стратегија за обезбедување квалитет (УКИМ) 2024–2029",
    "upatstvo-za-samoevaluaczija-i-obezbeduvanje-i-oczenuvanje-na-kvalitetot-na-univerzitetot-sv.-kiril-i-metodij-vo-skopje-i-negovite-ediniczi": "Упатство за самоевалуација (УКИМ)",
    "statut_i_delovnik": "Статут и деловник (ФИНКИ)",
    "pravilnik_za_standardite_i_postapkata_za_nadvoreshna_evaluacija_i_samoevaluacija_sluzhben_vesnik_na_republika_severna_makedonija_br._153.2022": "Правилник за стандардите и постапката за надворешна евалуација и самоевалуација",
    "Правилник за ДИСЦИПЛИНСКА ОДГОВОРНОСТ НА СТУДЕНТИТЕ": "Правилник за дисциплинска одговорност на студентите",
}

OCR_SYSTEM = (
    "Ти си прецизен транскриптор на македонски правни документи (закони, правилници, "
    "статути). Транскрибирај го дадениот документ ДОСЛОВНО во чист Markdown. Не сумирај, "
    "не перифразирај, не преведувај и не додавај ништо. Зачувај го точниот текст.\n\n"
    "Структура:\n"
    "- Секој член како наслов: `# Член N`\n"
    "- Ставовите и точките под соодветниот член, со оригиналната нумерација\n"
    "- Табелите како Markdown табели; листите како Markdown листи\n"
    "- Ако некој текст е нечитлив, стави `[нечитливо]` — НЕ погодувај\n\n"
    "Врати ИСКЛУЧИВО ја транскрипцијата, без коментар, без вовед, без заклучок."
)


def slug(stem: str) -> str:
    s = stem.lower().replace(" ", "-")
    s = re.sub(r"[^a-z0-9а-ш\-]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def title_for(stem: str) -> str:
    return TITLES.get(stem, stem.replace("_", " ").replace("-", " ").strip())


def is_excluded(name: str) -> bool:
    low = name.lower()
    return any(x in low for x in EXCLUDE)


def needs_ocr(name: str) -> bool:
    low = name.lower()
    return any(x in low for x in NEEDS_OCR)


def docx_to_markdown(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    out: list[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        if re.match(r"^Член\s+\d+", text):
            out.append(f"\n# {text}\n")
        else:
            out.append(text)
    return "\n".join(out).strip()


def extract_tier_a(raw_dir: Path) -> None:
    import docpipe  # local: tools/docpipe.py (pulls in PyMuPDF — only needed for extraction)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for src in sorted(raw_dir.iterdir()):
        if src.is_dir():
            continue
        stem = src.stem
        if is_excluded(src.name):
            print(f"SKIP  (excluded)   {src.name}")
            continue
        if needs_ocr(src.name):
            print(f"SKIP  (Tier B OCR) {src.name}  -> run: preprocess.py ocr '{src}'")
            continue

        if src.suffix.lower() == ".docx":
            md = docx_to_markdown(src)
        elif src.suffix.lower() == ".pdf":
            raw = docpipe.extract_pdf(str(src))
            cyr = sum(1 for c in raw if "Ѐ" <= c <= "ӿ")
            lat = sum(1 for c in raw if c.isascii() and c.isalpha())
            if len(raw.strip()) < 50 or cyr / (cyr + lat + 1) < 0.85:
                print(f"WARN  (no usable text -> needs OCR) {src.name}")
                continue
            _, md = docpipe.to_markdown(raw)
        else:
            continue

        out = OUT_DIR / f"{slug(stem)}.md"
        header = f"<!-- title: {title_for(stem)} | source: {src.name} | TIER A extraction — REVIEW BEFORE INGEST -->\n\n"
        out.write_text(header + md, encoding="utf-8")
        print(f"OK    Tier A         {src.name}  -> {out.name}")


def ocr_pdf(path: Path, page_range: str | None = None) -> None:
    import anthropic
    import pypdf

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic()

    reader = pypdf.PdfReader(str(path))
    n = len(reader.pages)
    # Process in page windows so each response stays well under the output token cap.
    window = 20
    ranges = (
        [tuple(map(int, page_range.split("-")))]
        if page_range
        else [(i, min(i + window, n)) for i in range(0, n, window)]
    )

    parts: list[str] = []
    for start, end in ranges:
        writer = pypdf.PdfWriter()
        for p in range(start, end):
            writer.add_page(reader.pages[p])
        buf = __import__("io").BytesIO()
        writer.write(buf)
        data = base64.standard_b64encode(buf.getvalue()).decode()
        print(f"  OCR pages {start}-{end} of {n} ...")
        text = []
        with client.messages.stream(
            model="claude-opus-4-8",
            max_tokens=64000,
            thinking={"type": "adaptive"},
            system=OCR_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": data,
                            },
                        },
                        {"type": "text", "text": "Транскрибирај го документот според упатствата."},
                    ],
                },
            ],
        ) as stream:
            for chunk in stream.text_stream:
                text.append(chunk)
            msg = stream.get_final_message()
        if msg.stop_reason == "max_tokens":
            print(f"  WARN: pages {start}-{end} hit max_tokens — narrow the page window")
        parts.append("".join(text))

    stem = path.stem
    out = OUT_DIR / f"{slug(stem)}.md"
    header = f"<!-- title: {title_for(stem)} | source: {path.name} | TIER B Claude vision OCR — REVIEW BEFORE INGEST -->\n\n"
    out.write_text(header + "\n\n".join(parts), encoding="utf-8")
    print(f"OK    Tier B OCR -> {out.name}")


R2_PREFIX = "documents/"


def _r2_client():
    import boto3

    endpoint = os.environ.get("R2_ENDPOINT") or (
        f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
    )
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def upload_originals(raw_dir: Path) -> None:
    """Archive the (non-excluded) original source files to R2 for provenance."""
    bucket = os.environ.get("R2_BUCKET")
    if not bucket:
        sys.exit("Set R2_BUCKET (+ R2_ACCOUNT_ID/R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY).")
    client = _r2_client()
    for src in sorted(raw_dir.iterdir()):
        if src.is_dir() or is_excluded(src.name):
            continue
        key = f"{R2_PREFIX}{src.name}"
        client.upload_file(str(src), bucket, key)
        print(f"OK    uploaded {src.name} -> r2://{bucket}/{key}")
    print("\nOriginals archived. The R2 key is stored in each document's metadata at ingest time.")


def _source_filename(content: str) -> str | None:
    """Pull the original filename out of the processed-Markdown header comment."""
    m = re.search(r"source:\s*(.+?\.(?:pdf|docx))", content, re.IGNORECASE)
    return m.group(1).strip() if m else None


def ingest(api_url: str) -> None:
    import json
    import urllib.request

    api_key = os.environ.get("API_KEY")
    if not api_key:
        sys.exit("Set API_KEY in the environment to ingest.")

    for md_path in sorted(OUT_DIR.glob("*.md")):
        content = md_path.read_text(encoding="utf-8")
        title_match = re.search(r"<!--\s*title:\s*([^|]+?)\s*\|", content)
        title = title_match.group(1).strip() if title_match else md_path.stem
        source_file = _source_filename(content)
        metadata = (
            {"source_file": source_file, "r2_key": f"{R2_PREFIX}{source_file}"}
            if source_file
            else None
        )
        body = {
            "name": md_path.stem,
            "title": title,
            "content": content,
            "source_type": "markdown",
            "metadata": metadata,
        }
        req = urllib.request.Request(
            f"{api_url}/documents/",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-api-key": api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req) as resp:  # noqa: S310
                result = json.loads(resp.read())
                print(f"OK    ingested {md_path.name} -> {result.get('chunk_count')} chunks")
        except Exception as e:  # noqa: BLE001
            print(f"FAIL  {md_path.name}: {e}")
    print("\nNow run: preprocess.py fill  (or POST /documents/fill) to generate embeddings.")


def fill(api_url: str) -> None:
    """Drive /documents/fill for all models over chunks still missing embeddings."""
    import json
    import urllib.request

    api_key = os.environ.get("API_KEY")
    if not api_key:
        sys.exit("Set API_KEY in the environment to fill embeddings.")

    body = {"all_models": True, "all_chunks": False}
    req = urllib.request.Request(
        f"{api_url}/documents/fill",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-api-key": api_key},
        method="POST",
    )
    ok = err = 0
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                evt = json.loads(line[len("data:"):].strip())
                if evt.get("status") == "ok":
                    ok += 1
                else:
                    err += 1
                    print(f"  FAIL [{evt.get('model')}] {evt.get('name')}: {evt.get('error')}")
                done = ok + err
                if done % 50 == 0:
                    print(f"  ... {done}/{evt.get('total')} ({err} errors)")
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Fill request failed: {e}")
    if err:
        sys.exit(f"\nFill finished with errors: {ok} ok, {err} failed.")
    print(f"\nFill complete: {ok} ok, {err} errors.")


def sync(api_url: str) -> None:
    """Reconcile the API to processed/: ingest current files, then prune documents whose file is gone.

    The processed/ folder is the source of truth, so renames and removals are handled by deleting any
    stored document whose name no longer matches a file. R2 originals are kept (archive) — orphaned
    keys are reported, not deleted.
    """
    import json
    import urllib.parse
    import urllib.request

    api_key = os.environ.get("API_KEY")
    if not api_key:
        sys.exit("Set API_KEY in the environment to sync.")

    ingest(api_url)

    desired = {p.stem for p in OUT_DIR.glob("*.md")}
    list_req = urllib.request.Request(
        f"{api_url}/documents/list",
        headers={"x-api-key": api_key},
        method="GET",
    )
    try:
        with urllib.request.urlopen(list_req) as resp:  # noqa: S310
            stored = json.loads(resp.read())
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Failed to list documents: {e}")

    orphans = [d for d in stored if d["name"] not in desired]
    if not orphans:
        print("\nIn sync: every stored document has a matching file; nothing to prune.")
    else:
        print(f"\nPruning {len(orphans)} document(s) with no matching file (rename/removal):")
        for d in orphans:
            name = d["name"]
            del_req = urllib.request.Request(
                f"{api_url}/documents/{urllib.parse.quote(name, safe='')}",
                headers={"x-api-key": api_key},
                method="DELETE",
            )
            try:
                with urllib.request.urlopen(del_req) as resp:  # noqa: S310
                    deleted = json.loads(resp.read())
                r2 = (deleted.get("metadata") or {}).get("r2_key")
                note = f"  (R2 original kept as archive: {r2})" if r2 else ""
                print(f"  pruned {name}{note}")
            except Exception as e:  # noqa: BLE001
                print(f"  FAIL pruning {name}: {e}")

    print("\nNow run: preprocess.py fill  to embed any new/changed chunks.")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "extract"
    if cmd == "extract":
        raw_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else RAW_DIR
        extract_tier_a(raw_dir)
    elif cmd == "ocr":
        ocr_pdf(Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "upload":
        upload_originals(Path(sys.argv[2]) if len(sys.argv) > 2 else RAW_DIR)
    elif cmd == "ingest":
        ingest(sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8880")
    elif cmd == "fill":
        fill(sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8880")
    elif cmd == "sync":
        sync(sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8880")
    else:
        sys.exit(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
