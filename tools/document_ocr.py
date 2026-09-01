import base64
from pathlib import Path

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


def ocr_pdf(
    path: Path,
    out_dir: Path,
    title: str,
    slug: str,
    page_range: str | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{slug}.md"
    if output.exists():
        print(f"SKIP  (processed exists) {path.name}  -> {output.name}")
        return

    import anthropic
    import pypdf

    client = anthropic.Anthropic()
    reader = pypdf.PdfReader(str(path))
    page_count = len(reader.pages)
    window = 20
    ranges = (
        [tuple(map(int, page_range.split("-")))]
        if page_range
        else [
            (start, min(start + window, page_count))
            for start in range(0, page_count, window)
        ]
    )

    parts: list[str] = []
    for start, end in ranges:
        writer = pypdf.PdfWriter()
        for page in range(start, end):
            writer.add_page(reader.pages[page])
        buffer = __import__("io").BytesIO()
        writer.write(buffer)
        data = base64.standard_b64encode(buffer.getvalue()).decode()
        print(f"  OCR pages {start}-{end} of {page_count} ...")
        text: list[str] = []
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
                        {
                            "type": "text",
                            "text": "Транскрибирај го документот според упатствата.",
                        },
                    ],
                },
            ],
        ) as stream:
            text.extend(stream.text_stream)
            message = stream.get_final_message()
        if message.stop_reason == "max_tokens":
            print(
                f"  WARN: pages {start}-{end} hit max_tokens — narrow the page window"
            )
        parts.append("".join(text))

    header = (
        f"<!-- title: {title} | source: {path.name} | TIER B Claude vision OCR -->\n\n"
    )
    output.write_text(header + "\n\n".join(parts), encoding="utf-8")
    print(f"OK    Tier B OCR -> {output.name}")
