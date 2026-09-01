import re
import sys
from pathlib import Path
from typing import Final

if __package__:
    from tools import document_api, document_metadata, document_ocr, document_storage
else:
    import document_api
    import document_metadata
    import document_ocr
    import document_storage

RAW_DIR = Path("raw")
OUT_DIR = Path("processed")
R2_PREFIX = "documents/"

EXPLICITLY_EXCLUDED_SOURCES: Final = frozenset(
    {
        "vodich-za-studenti.pdf",
        "pravilnik-za-prijavi-za-korupcija-glasnik-485-2020.pdf",
    }
)

NEEDS_OCR = (
    "statut_i_delovnik",
    "pravilnik_za_standardite",
    "procedura_za_prijava",
    "procedura_za_zalbi",
    "strategija_za_obezbeduvanje",
    "cenovnik_finki",
)

CURATED_SOURCE_FILES: Final = frozenset(
    {
        "grading_scale_1.pdf",
        "zakon-zashtita-lichni-podatoci-42-2020.pdf",
        "izmeni-zakon-zashtita-lichni-podatoci-294-2021.pdf",
        "dopolnuvanje-zakon-zashtita-lichni-podatoci-101-2025.pdf",
    }
)

TITLES = {
    "264_statut_ukim-6.6.2019": "Статут на Универзитетот „Св. Кирил и Методиј“ во Скопје",
    "Pravilnik_studii_prv_vtor_ciklus_FINKI": "Правилник за студии на прв и втор циклус (ФИНКИ)",
    "Pravilnik_doktorski_studii_po_stara_programa": "Правилник за докторски студии (стара програма)",
    "Zakon_za_formiranje_na_FINKI": "Закон за основање на ФИНКИ",
    "zakon_za_visokoto_obrazovanie_nov": "Закон за високото образование",
    "cenovnik_finki_2024-25-2": "Ценовник на ФИНКИ 2024/25",
    "etichki_kodeks_ukim-finki": "Етички кодекс на УКИМ/ФИНКИ",
    "grading_scale_1": "Скала на оценување / Grading Scale (ФИНКИ)",
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

MetadataError = document_metadata.MetadataError
_header_value = document_metadata.header_value
_source_filenames = document_metadata.source_filenames


def slug(stem: str) -> str:
    normalized = stem.lower().replace(" ", "-")
    normalized = re.sub(r"[^a-z0-9а-ш\-]+", "-", normalized)
    return re.sub(r"-+", "-", normalized).strip("-")


def title_for(stem: str) -> str:
    return TITLES.get(stem, stem.replace("_", " ").replace("-", " ").strip())


def is_excluded(name: str) -> bool:
    return name.casefold() in EXPLICITLY_EXCLUDED_SOURCES


def needs_ocr(name: str) -> bool:
    lowered = name.lower()
    return any(fragment in lowered for fragment in NEEDS_OCR)


def docx_to_markdown(path: Path) -> str:
    from docx import Document

    document = Document(str(path))
    output: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        output.append(f"\n# {text}\n" if re.match(r"^Член\s+\d+", text) else text)
    return "\n".join(output).strip()


def extract_tier_a(raw_dir: Path) -> None:
    if __package__:
        from tools import docpipe
    else:
        import docpipe

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for source in sorted(raw_dir.iterdir()):
        if source.is_dir():
            continue
        if source.name in CURATED_SOURCE_FILES:
            print(f"SKIP  (curated set) {source.name}")
            continue
        if is_excluded(source.name):
            print(f"SKIP  (excluded)   {source.name}")
            continue
        if needs_ocr(source.name):
            print(
                f"SKIP  (Tier B OCR) {source.name}  -> run: preprocess.py ocr '{source}'"
            )
            continue

        output = OUT_DIR / f"{slug(source.stem)}.md"
        if output.exists():
            print(f"SKIP  (processed exists) {source.name}  -> {output.name}")
            continue

        if source.suffix.lower() == ".docx":
            markdown = docx_to_markdown(source)
        elif source.suffix.lower() == ".pdf":
            raw = docpipe.extract_pdf(str(source))
            cyrillic = sum(1 for character in raw if "Ѐ" <= character <= "ӿ")
            latin = sum(
                1 for character in raw if character.isascii() and character.isalpha()
            )
            if len(raw.strip()) < 50 or cyrillic / (cyrillic + latin + 1) < 0.85:
                print(f"WARN  (no usable text -> needs OCR) {source.name}")
                continue
            _, markdown = docpipe.to_markdown(raw)
        else:
            continue

        header = (
            f"<!-- title: {title_for(source.stem)} | source: {source.name} | "
            "TIER A extraction -->\n\n"
        )
        output.write_text(header + markdown, encoding="utf-8")
        print(f"OK    Tier A         {source.name}  -> {output.name}")


def ocr_pdf(path: Path, page_range: str | None = None) -> None:
    document_ocr.ocr_pdf(
        path,
        OUT_DIR,
        title_for(path.stem),
        slug(path.stem),
        page_range,
    )


def upload_originals(raw_dir: Path) -> None:
    document_storage.upload_originals(
        raw_dir,
        R2_PREFIX,
        EXPLICITLY_EXCLUDED_SOURCES,
    )


def audit_corpus(
    directory: Path | None = None,
    raw_directory: Path | None = None,
) -> dict[str, int]:
    processed = directory or OUT_DIR
    originals = (
        RAW_DIR if directory is None and raw_directory is None else raw_directory
    )
    return document_metadata.audit_corpus(processed, originals)


def ingest(api_url: str) -> None:
    document_api.ingest(api_url, OUT_DIR, R2_PREFIX)


def fill(api_url: str) -> None:
    document_api.fill(api_url)


def sync(api_url: str) -> None:
    document_api.sync(api_url, OUT_DIR, R2_PREFIX)


def _print_help() -> None:
    print(
        "Usage: preprocess.py [extract [raw_dir] | ocr <pdf> [pages] | upload [raw_dir] | "
        "ingest [api_url] | fill [api_url] | sync [api_url] | audit]"
    )


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    command = sys.argv[1] if len(sys.argv) > 1 else "extract"
    if command in {"-h", "--help", "help"}:
        _print_help()
    elif command == "extract":
        extract_tier_a(Path(sys.argv[2]) if len(sys.argv) > 2 else RAW_DIR)
    elif command == "ocr":
        if len(sys.argv) < 3:
            sys.exit("Usage: preprocess.py ocr <pdf> [pages]")
        ocr_pdf(Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else None)
    elif command == "upload":
        upload_originals(Path(sys.argv[2]) if len(sys.argv) > 2 else RAW_DIR)
    elif command == "ingest":
        ingest(sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8880")
    elif command == "fill":
        fill(sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8880")
    elif command == "sync":
        sync(sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8880")
    elif command == "audit":
        statuses = audit_corpus()
        print(f"OK    audited {sum(statuses.values())} documents")
        for status, count in statuses.items():
            print(f"  {status}: {count}")
    else:
        sys.exit(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
