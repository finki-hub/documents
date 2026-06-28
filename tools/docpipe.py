"""
Offline document pipeline (experimental): extract -> Markdown -> member-aware chunk.

Run with ephemeral deps:
    uv run --with pymupdf --with langchain-text-splitters --with transformers \
        python tools/docpipe.py <pdf-or-md-path>

Chunk sizes are measured against the real multilingual-e5-large tokenizer; the
512-token window is the binding constraint across the configured embedding models.
"""

import re
import sys
from collections import Counter

import fitz  # PyMuPDF

MEMBER_RE = re.compile(r"^Член\s+\d+")
MEMBER_SPLIT = re.compile(r"(?=^Член\s+\d+)", re.MULTILINE)
STAV_SPLIT = re.compile(r"(?=^\(\d+\))", re.MULTILINE)
PAGENUM_RE = re.compile(r"^\d{1,3}$")


def extract_pdf(path: str) -> str:
    """Extract text, dropping repeated headers/footers and bare page numbers."""
    doc = fitz.open(path)
    pages = [p.get_text("text") for p in doc]
    doc.close()

    firsts: Counter[str] = Counter()
    lasts: Counter[str] = Counter()
    for pg in pages:
        ls = [ln.strip() for ln in pg.splitlines() if ln.strip()]
        if ls:
            firsts[ls[0]] += 1
            lasts[ls[-1]] += 1
    threshold = max(3, int(len(pages) * 0.4))
    repeated = {s for s, n in {**firsts, **lasts}.items() if n >= threshold}

    out: list[str] = []
    for pg in pages:
        for ln in pg.splitlines():
            s = ln.strip()
            if not s or s in repeated or PAGENUM_RE.fullmatch(s):
                continue
            out.append(s)
    return "\n".join(out)


def to_markdown(text: str) -> tuple[str, str]:
    """Detect structure; return (mode, markdown). mode in {member, heading}."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    joined = "\n".join(lines)
    if not MEMBER_SPLIT.search(joined):
        return "heading", _reflow(lines)

    parts = MEMBER_SPLIT.split(joined)
    md: list[str] = []
    preamble = parts[0].strip()
    if preamble:
        md.append(_para(preamble.splitlines()))
    for part in parts[1:]:
        plines = part.splitlines()
        header = plines[0].strip()
        body = _para(plines[1:])
        md.append(f"# {header}\n\n{body}".rstrip())
    return "member", "\n\n".join(md)


def _para(lines: list[str]) -> str:
    """Space-join wrapped lines, breaking before став markers '(1)'."""
    text = " ".join(ln.strip() for ln in lines if ln.strip())
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s(\(\d+\))\s", r"\n\n\1 ", text)
    return text


def _reflow(lines: list[str]) -> str:
    return _para(lines)


def chunk(markdown: str, mode: str, token_len, target=380, hard=450, overlap=48):
    """One chunk per член where it fits; recursively sub-split long ones."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    sub = RecursiveCharacterTextSplitter(
        chunk_size=target,
        chunk_overlap=overlap,
        length_function=token_len,
        separators=["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""],
    )

    units: list[tuple[str, str]] = []
    if mode == "member":
        blocks = re.split(r"(?=^# Член\s+\d+)", markdown, flags=re.MULTILINE)
        for b in blocks:
            b = b.strip()
            if not b:
                continue
            m = re.match(r"# (Член\s+\d+)", b)
            label = m.group(1) if m else "Преамбула"
            body = re.sub(r"^# Член\s+\d+\s*", "", b).strip()
            units.append((label, body))
    else:
        units.append(("", markdown))

    chunks: list[tuple[str, str]] = []
    for label, body in units:
        if token_len(body) <= hard:
            chunks.append((label, body))
        else:
            for piece in sub.split_text(body):
                chunks.append((label, piece))
    return chunks


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    path = sys.argv[1]
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-large")

    def tlen(s: str) -> int:
        return len(tok.encode(s, add_special_tokens=False))

    import glob
    import os

    if os.path.isdir(path):
        files = sorted(glob.glob(os.path.join(path, "*.pdf")))
        print(
            f"{'MODE':8} {'CHUNKS':>6} {'MAXTOK':>6} {'>512':>5} {'MEMBERS':>7}  FILE"
        )
        total = 0
        for f in files:
            try:
                raw = extract_pdf(f)
                if len(raw.strip()) < 50:
                    print(
                        f"{'SCANNED':8} {'-':>6} {'-':>6} {'-':>5} {'-':>7}  {os.path.basename(f)}"
                    )
                    continue
                cyr = sum(1 for c in raw if "Ѐ" <= c <= "ӿ")
                lat = sum(1 for c in raw if c.isascii() and c.isalpha())
                if cyr / (cyr + lat + 1) < 0.85:
                    print(
                        f"{'CORRUPT':8} {'-':>6} {'-':>6} {'-':>5} {'-':>7}  {os.path.basename(f)}  (legacy font -> route to vision)"
                    )
                    continue
                mode, md = to_markdown(raw)
                ch = chunk(md, mode, tlen)
                title = os.path.basename(f)
                sizes = [
                    tlen(f"passage: Наслов: {title} ({lb})\nСодржина: {b}")
                    for lb, b in ch
                ]
                over = sum(1 for s in sizes if s > 512)
                total += len(ch)
                nm = len({lb for lb, _ in ch if lb.startswith("Член")})
                print(
                    f"{mode:8} {len(ch):6} {max(sizes):6} {over:5} {nm:7}  {os.path.basename(f)}"
                )
            except Exception as e:
                print(
                    f"{'ERR':8} {'-':>6} {'-':>6} {'-':>5} {'-':>7}  {os.path.basename(f)} -> {e}"
                )
        print(f"\nTOTAL CHUNKS (text-layer PDFs): {total}")
        return

    if path.lower().endswith(".pdf"):
        mode, md = to_markdown(extract_pdf(path))
    else:
        with open(path, encoding="utf-8") as fp:
            md = fp.read()
        md = re.sub(r"<!--.*?-->", "", md, flags=re.DOTALL).strip()
        mode = "member" if re.search(r"^# Член\s+\d+", md, re.MULTILINE) else "heading"
    doc_title = path.split("/")[-1].split("\\")[-1]
    chunks = chunk(md, mode, tlen)

    # embed string mirrors the FAQ format ("Наслов: ...\nСодржина: ...")
    sizes = []
    over = 0
    for label, body in chunks:
        title = f"{doc_title} ({label})" if label else doc_title
        embed = f"passage: Наслов: {title}\nСодржина: {body}"
        n = tlen(embed)
        sizes.append(n)
        if n > 512:
            over += 1

    print(f"=== {doc_title}")
    print(f"mode={mode}  chars={len(md)}  chunks={len(chunks)}")
    print(
        f"embed-token sizes: min={min(sizes)} median={sorted(sizes)[len(sizes) // 2]} "
        f"max={max(sizes)} >512={over}"
    )
    print("\n--- markdown head ---")
    print(md[:700])
    print("\n--- sample chunks ---")
    for (label, body), n in list(zip(chunks, sizes))[:4]:
        print(f"\n[{label}] ({n} embed-tokens)\n{body[:320]}")


if __name__ == "__main__":
    main()
