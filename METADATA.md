# Corpus metadata evidence ledger

Audit date: **2026-09-07**

UKIM study-rules addition reviewed: **2026-10-16** (37 processed documents; the earlier corpus-wide audit date is unchanged).

This ledger records the authority evidence behind the machine-readable headers in `processed/`. It deliberately distinguishes an act's legal date from a report's coverage period, a consolidated text's amendment cutoff, and a file's technical timestamps.

## Status vocabulary

- `current`: authoritative evidence supports present use.
- `presumed_current`: current through the stated version or amendment, but no exhaustive later-act search was available.
- `currentness_unresolved`: the act or publication is real, but present validity was not established.
- `historical`: retained for historical or transitional questions, not ordinary current guidance.
- `superseded` / `likely_superseded`: replacement is explicit or strongly indicated.
- `stale_review_required`: operational content, contacts, or statutory references require periodic review.
- `informational`: guidance or a report, not a governing act.
- `authority_unresolved`: the supplied text lacks evidence that it was formally adopted.
- `foundational`: an establishment act retained for institutional-history questions.

## Evidence

| Document | Primary date | Kind / precision | Status | Evidence and authority source |
|---|---:|---|---|---|
| `264-statut-ukim-6-6-2019` | 2019-06 | adopted / month | current | Text says “Скопје, јуни 2019” and repeals the 2008 statute; [official UKIM PDF](https://ukim.edu.mk/wp-content/uploads/2021/05/264_statut_ukim-6.6.2019.pdf). |
| `cenovnik-finki-2024-25-2` | 2024-07-04 | adopted / day | presumed_current | Date and 2024/25 applicability are printed in the text; it remains valid until replaced; [official FINKI PDF](https://finki.ukim.mk/wp-content/uploads/2026/07/cenovnik_finki_2024-25-2.pdf). |
| `delovnik-za-rabota-glasnik-682` | 2024-04-22 | published / day | presumed_current | University Gazette 682; adopted 2024-04-01 and effective on publication; [FINKI legal acts](https://www.finki.ukim.mk/mk/zafakultetot/pravni_akti). |
| `dopolnuvanje-pravilnik-studii-ukim-607-2022` | 2022-03-31 | adopted / day | currentness_unresolved | Senate session 19; Gazette 607, published/effective 2022-04-06. Adds only article 82(4) to 417/2019, plus its own commencement clause. [Official PDF](https://ukim.edu.mk/wp-content/uploads/2024/10/77_427342087.pdf); full scope and conflict evidence below. |
| `etichki-kodeks-ukim-finki` | 2021-05-10 | published / day | current | University Gazette 549; adopted 2021-05-06 and effective on publication; [UKIM ethical code](https://ukim.edu.mk/univerzitet/dokumenti-2/normativni-akti-2/drugi-akti/etichki-kodeks/). |
| `grading-scale-finki` | unresolved | unresolved / none | current | The PDF carries no authoritative issuance date; FINKI's current [undergraduate documents and procedures page](https://finki.ukim.mk/studii-2/poddrshka/dokumenti-i-proceduri/dokumenti-i-proceduri-dodiplomski/) links it as the official grading scale. |
| `izveshtaj-samoevaluacija-finki-2023-2024` | 2023/2024 | coverage_period / academic_year | informational | The report states its coverage period; no signed issuance date is visible; [FINKI reports](https://finki.ukim.mk/za-nas/administracija-i-dokumenti/izveshtai-za-fakultetot/). |
| `lista-informacii-javen-karakter-finki` | 2012-10-30 | issued / day | stale_review_required | Archive number/date and immediate effect are printed; current FINKI page links a newer upload without a visible issuance date: [public-information page](https://finki.ukim.mk/en/za-nas/administracija-i-dokumenti/sloboden-pristap-do-informacii-od-javen-karakter/). |
| `lista-posrednici-voznemiruvanje-rabotno-mesto-finki` | 2026-05-18 | issued / day | current | Archive number/date and immediate effect are printed; personnel list requires periodic review; [official PDF](https://finki.ukim.mk/sites/default/files/u703/odluka-lista-za-posrednici-za-zastita-od-voznemirvanje-na-rabotno-mesto.pdf). |
| `odluka-plati-nadomestoci-finki-2026-02-19` | 2019-09-26 | adopted / day | currentness_unresolved | Base decision date is printed and an [official consolidated copy](https://finki.ukim.mk/wp-content/uploads/2026/07/odluka_za_plati_2024_-_so_vneseni_site_izmeni_zakluchno_so_19.02.2026.pdf) is available; the claimed 2026 cutoff still lacks a separate amendment register. |
| `odluka-sovet-kvalitet-finki` | 2019-09-26 | issued / day | stale_review_required | Decision 02-684/1; member mandates were three years and student mandates two years; [FINKI reports](https://finki.ukim.mk/za-nas/administracija-i-dokumenti/izveshtai-za-fakultetot/). |
| `partnerstvo-industrija` | unresolved | unresolved / none | current | The public [SharePoint URL](https://finkiukim-my.sharepoint.com/:w:/g/personal/webadmin_finki_ukim_mk/Edd0HpQSmINIg35ovJGIItYBiZFzz3Vj3KdKGCck87oYKw) was user-confirmed as current on 2026-09-07; automated direct HTTP access returns 403. This is provenance/currentness evidence only, not a legal issued or effective date. |
| `pravilnik-doktorski-studii-po-stara-programa` | unresolved | unresolved / none | historical | Text expressly limits scope to the period through 2011-12-31; no adoption or publication date is present. |
| `pravilnik-iii-ciklus-2020` | 2020-12-31 | published / day | presumed_current | University Gazette 530/2020; [UKIM guide page and governing-rule reference](https://ukim.edu.mk/studii/informacii-za-studentite/vodich-za-studenti/). |
| `pravilnik-kvalitet-nastava-finki` | 2024-05-16 | adopted / day | current | Decision 02-629/2 and immediate effect are printed; [FINKI reports](https://finki.ukim.mk/za-nas/administracija-i-dokumenti/izveshtai-za-fakultetot/). |
| `pravilnik-standardi-evaluacija-153-2022` | 2022-07-06 | published / day | presumed_current | Official Gazette 153/2022; effective 2022-07-14; [UKIM quality system](https://ukim.edu.mk/univerzitet/kvalitet/sistem-za-kvalitet/). |
| `pravilnik-studii-prv-vtor-ciklus-finki` | 2013-07-04 | adopted / day | currentness_unresolved | FINKI decision 02-959/1; no later-currentness evidence was established; [FINKI legal acts](https://www.finki.ukim.mk/mk/zafakultetot/pravni_akti). |
| `pravilnik-studii-prv-vtor-ciklus-ukim-417-2019` | 2018-11-27 | adopted / day | currentness_unresolved | Senate session 26; Gazette 417, published/effective 2019-01-29. Full Macedonian text, articles 1–101, from the [official archive PDF](https://archive.ukim.edu.mk/dokumentacija/74_668210497.pdf). Header uses the approved-host [UKIM rules index](https://ukim.edu.mk/doktorska-shkola/studii/dokumenti/normativni-akti/); its current direct 417 link serves an English version, not these archived Macedonian bytes. See provenance and transitional limits below. |
| `pravilnik-za-obezbeduvanje-kvalitet-na-univerzitetot-sv-kiril-i-metodij-vo-skopje` | 2024-03-04 | published / day | current | University Gazette 674/2024; adopted 2024-02-28 and effective on publication; [UKIM quality system](https://ukim.edu.mk/univerzitet/kvalitet/sistem-za-kvalitet/). |
| `pravilnik-za-rabota-na-ovlasteno-lice-za-prierm-na-prijavi-na-korupcija` | unresolved | unresolved / none | currentness_unresolved | Officially linked, but the text has no adoption/publication date; [official PDF](https://finki.ukim.mk/sites/default/files/u703/pravilnik-za-rabota-na-ovlasteno-lice-za-prierm-na-prijavi-na-korupcija.pdf). |
| `procedura-pristap-ispravka-lichni-podatoci` | 2017-10-17 | issued / day | likely_superseded | Document 03-197; current FINKI privacy page links a newer 2026 upload: [privacy documents](https://finki.ukim.mk/za-nas/administracija-i-dokumenti/zashtita-na-lichni-podatoci/dokumenti/). |
| `procedura-za-prijava-na-korupcija` | unresolved | unresolved / none | currentness_unresolved | Officially listed, but no dated approval or revision record appears; [official PDF](https://finki.ukim.mk/sites/default/files/u703/procedura_za_prijava_na_korupcija.pdf). |
| `procedura-za-zalbi-na-finki` | unresolved | unresolved / none | currentness_unresolved | Officially listed, but no issuance/adoption date appears; [official PDF](http://finki.ukim.mk/sites/default/files/u703/procedura_za_zalbi_na_finki.pdf). |
| `procedura-za-zashtiteno-vnatreshno-prijavuvanje-na-fakultet-za-informatichki-nauki-i-kompjutersko-inzhenerstvo-skopje` | 2016-08-25 | issued / day | stale_review_required | Archive number/date are printed; terminology and statutory references require currentness review; [official PDF](http://finki.ukim.mk/sites/default/files/u703/procedura_za_zashtiteno_vnatreshno_prijavuvanje_na_fakultet_za_informatichki_nauki_i_kompjutersko_inzhenerstvo_skopje.pdf). |
| `sistematizacija-rabotni-mesta-finki-aneks-16` | 2023-12-29 | published / day | presumed_current | University Gazette 669; adopted 2023-12-11 and effective on publication. No later annex search was conclusive. |
| `statut-i-delovnik` | 2019-09-10 | adopted / day | currentness_unresolved | Date applies to the FINKI statute component; the combined extract does not expose a distinct date for the rules-of-procedure component; [FINKI legal acts](https://www.finki.ukim.mk/mk/zafakultetot/pravni_akti). |
| `statut-na-fakultetskoto-studentsko-sobranie-na-fakultetot-za-informatichki-nauki-i-kompjutersko-inzhenerstvo-skopje` | 2024-04-18 | adopted / day | currentness_unresolved | Adoption date is printed; exact Faculty Council approval/effective date is absent; [FINKI legal acts](https://www.finki.ukim.mk/mk/zafakultetot/pravni_akti). |
| `strategija-za-obezbeduvanje-kvalitet-na-univerzitetot-sv-kiril-i-metodij-vo-skopje-2024-2029` | 2024-06-24 | adopted / day | current | Senate decision 02-779/6; valid for 2024–2029; [official UKIM-hosted copy](https://fzf.ukim.edu.mk/wp-content/uploads/1.1.%D0%90.-%D0%A1%D1%82%D1%80%D0%B0%D1%82%D0%B5%D0%B3%D0%B8%D1%98%D0%B0-%D0%BD%D0%B0-%D0%BA%D0%B2%D0%B0%D0%BB%D0%B8%D1%82%D0%B5%D1%82-%D0%A3%D0%9A%D0%98%D0%9C-2024-2029.pdf). |
| `upatstvo-za-samoevaluaczija-i-obezbeduvanje-i-oczenuvanje-na-kvalitetot-na-univerzitetot-sv-kiril-i-metodij-vo-skopje-i-negovite-ediniczi` | 2024-03-04 | published / day | current | University Gazette 674/2024; adopted 2024-02-28, effective on publication, and repeals the 2013 instruction; [UKIM quality system](https://ukim.edu.mk/univerzitet/kvalitet/sistem-za-kvalitet/). |
| `vodich-doktorski-studii` | 2022-04-21 | published / day | informational | Official webpage publication metadata; this guide explains but is not the 2020 governing rule; [UKIM guide page](https://ukim.edu.mk/studii/informacii-za-studentite/vodich-za-studenti/). |
| `zakon-sloboden-pristap-javni-informacii` | 2019-05-16 | adopted / day | currentness_unresolved | Adoption/promulgation date and delayed application rule are in the text; exact Gazette issue and later amendments were not established. |
| `zakon-studentski-standard-111-2026` | 111/2026 | published / gazette_issue | presumed_current | Consolidated from Gazette 15/2013 through 111/2026; the calendar publication date and exhaustive later-act check remain unresolved; [Official Gazette portal](https://slvesnik.com.mk/). |
| `zakon-subvencioniran-studentski-obrok-74-2025` | 74/2025 | published / gazette_issue | presumed_current | Consolidated from Gazette 31/2020 through 74/2025; [Official Gazette portal](https://slvesnik.com.mk/). |
| `zakon-za-formiranje-na-finki` | 2010-12-30 | published / day | foundational | Official Gazette 171/2010; applies from 2011-01-01 and enters into force on the eighth day after publication. |
| `zakon-za-visokoto-obrazovanie-nov` | 2018-05-02 | adopted / day | currentness_unresolved | Adoption/promulgation date is printed; exact Gazette publication and the current consolidated amendment trail were not established. |
| `zakon-zashtita-lichni-podatoci-42-2020` | 2020-02-16 | published / day | presumed_current | Official Gazette 42/2020, consolidated with 294/2021 and 101/2025; [Official Gazette portal](https://slvesnik.com.mk/). |
| `правилник-за-дисциплинска-одговорност-на-студентите` | unresolved | unresolved / none | authority_unresolved | Supplied DOCX contains blank placeholders and no adoption date, archive number, or publication record. |

## Canonical authority URLs

The 33 direct-file URLs below were downloaded and verified byte-identical to their tracked `raw/` sources by SHA-256 on 2026-09-01. This partnership program uses a user-confirmed official FINKI SharePoint URL; automated direct HTTP access returns 403. The disciplinary rulebook also uses an official FINKI authority page because its SharePoint file is not a stable direct URL.

- `264-statut-ukim-6-6-2019` — <https://finki.ukim.mk/wp-content/uploads/2026/06/264_statut_ukim-6.6.2019.pdf>
- `cenovnik-finki-2024-25-2` — <https://finki.ukim.mk/wp-content/uploads/2026/07/cenovnik_finki_2024-25-2.pdf>
- `delovnik-za-rabota-glasnik-682` — <https://finki.ukim.mk/wp-content/uploads/2026/06/delovnik_za_rabota_-glasnik-682.pdf>
- `etichki-kodeks-ukim-finki` — <https://finki.ukim.mk/wp-content/uploads/2026/06/etichki_kodeks_ukim-finki.pdf>
- `grading-scale-finki` — <https://finki.ukim.mk/wp-content/uploads/2026/06/grading_scale_1.pdf>
- `izveshtaj-samoevaluacija-finki-2023-2024` — <https://finki.ukim.mk/wp-content/uploads/2026/06/finalen_izveshtaj_za_samoevaluacija_2023-24.pdf>
- `lista-informacii-javen-karakter-finki` — <https://finki.ukim.mk/wp-content/uploads/2026/06/podatoci_od_javen_karakter.pdf>
- `lista-posrednici-voznemiruvanje-rabotno-mesto-finki` — <https://finki.ukim.mk/wp-content/uploads/2026/07/odluka-voznemiruvanje.pdf>
- `odluka-plati-nadomestoci-finki-2026-02-19` — <https://finki.ukim.mk/wp-content/uploads/2026/07/odluka_za_plati_2024_-_so_vneseni_site_izmeni_zakluchno_so_19.02.2026.pdf>
- `odluka-sovet-kvalitet-finki` — <https://finki.ukim.mk/wp-content/uploads/2026/06/odluka_za_formiranje_sovet_za_kvalitet_na_finki.pdf>
- `partnerstvo-industrija` — <https://finkiukim-my.sharepoint.com/:w:/g/personal/webadmin_finki_ukim_mk/Edd0HpQSmINIg35ovJGIItYBiZFzz3Vj3KdKGCck87oYKw>
- `pravilnik-doktorski-studii-po-stara-programa` — <https://finki.ukim.mk/wp-content/uploads/2026/06/pravilnik_doktorski_studii_po_stara_programa.pdf>
- `pravilnik-iii-ciklus-2020` — <https://ukim.edu.mk/wp-content/uploads/2025/04/pravilnik-iii_ciklus-31.12.2020-glasnik_530.pdf>
- `pravilnik-kvalitet-nastava-finki` — <https://finki.ukim.mk/wp-content/uploads/2026/06/pravilnik_za_obezbeduvanje_i_ocenuvanje_na_kvalitetot_na_nastavata_na_finki.pdf>
- `pravilnik-standardi-evaluacija-153-2022` — <https://finki.ukim.mk/wp-content/uploads/2026/06/pravilnik_za_standardite_i_postapkata_za_nadvoreshna_evaluacija_i_samoevaluacija_sluzhben_vesnik_na_republika_severna_makedonija_br._153.2022.pdf>
- `pravilnik-studii-prv-vtor-ciklus-finki` — <https://finki.ukim.mk/wp-content/uploads/2026/06/pravilnik_studii_prv_vtor_ciklus_finki.pdf>
- `pravilnik-za-obezbeduvanje-kvalitet-na-univerzitetot-sv-kiril-i-metodij-vo-skopje` — <https://finki.ukim.mk/wp-content/uploads/2026/06/pravilnik-za-obezbeduvanje-kvalitet-na-univerzitetot-sv.-kiril-i-metodij-vo-skopje.pdf>
- `pravilnik-za-rabota-na-ovlasteno-lice-za-prierm-na-prijavi-na-korupcija` — <https://finki.ukim.mk/sites/default/files/u703/pravilnik-za-rabota-na-ovlasteno-lice-za-prierm-na-prijavi-na-korupcija.pdf>
- `procedura-pristap-ispravka-lichni-podatoci` — <https://finki.ukim.mk/wp-content/uploads/2026/08/399_procedura-za-pristap-na-subjektite-na-lichni-podatoci.pdf>
- `procedura-za-prijava-na-korupcija` — <https://finki.ukim.mk/wp-content/uploads/2026/06/procedura_za_prijava_na_korupcija.pdf>
- `procedura-za-zalbi-na-finki` — <https://finki.ukim.mk/wp-content/uploads/2026/06/procedura_za_zalbi_na_finki.pdf>
- `procedura-za-zashtiteno-vnatreshno-prijavuvanje-na-fakultet-za-informatichki-nauki-i-kompjutersko-inzhenerstvo-skopje` — <https://finki.ukim.mk/wp-content/uploads/2026/06/procedura_za_zashtiteno_vnatreshno_prijavuvanje_na_fakultet_za_informatichki_nauki_i_kompjutersko_inzhenerstvo_skopje.pdf>
- `sistematizacija-rabotni-mesta-finki-aneks-16` — <https://finki.ukim.mk/wp-content/uploads/2026/07/sistematizacija_finki_finalno_0.pdf>
- `statut-i-delovnik` — <https://finki.ukim.mk/wp-content/uploads/2026/06/statut_i_delovnik.pdf>
- `statut-na-fakultetskoto-studentsko-sobranie-na-fakultetot-za-informatichki-nauki-i-kompjutersko-inzhenerstvo-skopje` — <https://finki.ukim.mk/wp-content/uploads/2026/07/statut_na_fakultetskoto_studentsko_sobranie_na_fakultetot_za_informatichki_nauki_i_kompjutersko_inzhenerstvo_-_skopje.pdf>
- `strategija-za-obezbeduvanje-kvalitet-na-univerzitetot-sv-kiril-i-metodij-vo-skopje-2024-2029` — <https://finki.ukim.mk/wp-content/uploads/2026/06/strategija_za_obezbeduvanje_kvalitet_na_univerzitetot_sv._kiril_i_metodij_vo_skopje_2024_-_2029.pdf>
- `upatstvo-za-samoevaluaczija-i-obezbeduvanje-i-oczenuvanje-na-kvalitetot-na-univerzitetot-sv-kiril-i-metodij-vo-skopje-i-negovite-ediniczi` — <https://finki.ukim.mk/wp-content/uploads/2026/06/upatstvo-za-samoevaluaczija-i-obezbeduvanje-i-oczenuvanje-na-kvalitetot-na-univerzitetot-sv.-kiril-i-metodij-vo-skopje-i-negovite-ediniczi.pdf>
- `vodich-doktorski-studii` — <https://ukim.edu.mk/wp-content/uploads/2025/04/vodich-za-studenti.pdf>
- `zakon-sloboden-pristap-javni-informacii` — <https://finki.ukim.mk/wp-content/uploads/2026/08/zakon-za-sloboden-pristap-do-informaciite-od-javen-karakter.pdf>
- `zakon-studentski-standard-111-2026` — <https://portal.mdt.gov.mk/post-body-files/zakoni-mon-file-GeVe.docx>
- `zakon-subvencioniran-studentski-obrok-74-2025` — <https://portal.mdt.gov.mk/post-body-files/zakoni-mon-file-U1XW.pdf>
- `zakon-za-formiranje-na-finki` — <https://finki.ukim.mk/wp-content/uploads/2026/06/zakon_za_formiranje_na_finki.pdf>
- `zakon-za-visokoto-obrazovanie-nov` — <https://finki.ukim.mk/wp-content/uploads/2026/06/zakon_za_visokoto_obrazovanie_nov.pdf>
- `zakon-zashtita-lichni-podatoci-42-2020` — <https://azlp.mk/wp-content/uploads/2022/11/zakon_za_zastita_na_licnite_podatoci.pdf>
- `правилник-за-дисциплинска-одговорност-на-студентите` — <https://finki.ukim.mk/za-nas/administracija-i-dokumenti/pravni-akti-i-dokumenti/>

## UKIM study rules: provenance, scope and conflicts (2026-10-16)

This is repository review evidence, not part of either act. The objection and grade-entry conflicts below are resolved downstream rather than in this repository: in practice FINKI applies neither procedure, which the chat-bot FAQ „Закаснет внес на оцена и запишување семестар без оцени“ and its assistant note state. This ledger and the conflict notes are still **not** exported as machine-readable conflict metadata.

### Originals and extraction

Both URLs below were fetched again on 2026-10-16 and matched the retained originals byte-for-byte by SHA-256:

| Tracked original in `raw/` | Official download | SHA-256 | Scope of processed text |
|---|---|---|---|
| `pravilnik-studii-prv-vtor-ciklus-ukim-417-2019.pdf` | <https://archive.ukim.edu.mk/dokumentacija/74_668210497.pdf> | `9852f353799149f039fa7e6c58a76bc79641d9f211eec99728cb091c6e4b5bc2` | PDF pages 1–22 = Gazette pages 3–24: preamble, all 101 articles, rector signature. PDF page 23 = printed page 25 contains only the running header/page number. |
| `dopolnuvanje-pravilnik-studii-ukim-607-2022.pdf` | <https://ukim.edu.mk/wp-content/uploads/2024/10/77_427342087.pdf> | `1f4d8a427f53d7d41dc8056defb196d1ce8510dc6c16b662e9370688f4234827` | PDF page 1 = Gazette page 14, right column from the amendment preamble; PDF page 2 = Gazette page 15, left column through the Senate president signature. Other acts on these pages are retained in the raw PDF but excluded from this act's Markdown. |

The [official rules index](https://ukim.edu.mk/doktorska-shkola/studii/dokumenti/normativni-akti/) lists the base rule, this amendment and a separate Annex 1. The archive host is not in the existing metadata host allowlist, so the base document uses this approved official index as `authority_url`, with the exact Macedonian download and hash recorded here. No new metadata fields or host-policy changes are needed. The 2024 upload directory is not an adoption date.

Extraction used local PyMuPDF 1.28.2 text spans, with left-column-then-right-column ordering, the full-width 417 preamble handled separately, and running headers/footers removed. The 417 legacy-font alphabet was mapped to Unicode Macedonian by font, preserving the Latin ECTS grades and “Diploma Supplement”. Wrapped lines were reflowed, three discretionary word splits joined, and embedded Latin `e`/`o` homoglyphs in Macedonian words normalized. No OCR or translation was used. All source text was reviewed in reading order against the PDFs; targeted rendered-page checks covered the typography, grade table, disputed provisions, terminal clauses and both amendment pages. Article headings and PDF/printed-page comment locators are retained; `source_pages` uses PDF page numbers. Source wording/typos are not silently rewritten: for example, article 70 has “од од”, article 90 “Едницата”, and article 81 visibly prints `сP` (Latin P), which is preserved rather than guessing the intended glyph. The raw source remains decisive for these anomalies.

The base is the publication text, not a consolidation through 2022. The amendment is a separate complete two-article act. Article 97 refers to Annex 1 and article 99 requires its later adoption; that separate annex is not contained in the 417 source and is not synthesized here. No claim is made that this pair is the entire later amendment/annex chain.

### Closing clauses and currentness

The preamble dates adoption of 417 to **27 November 2018**; the Gazette header dates publication to **29 January 2019**. On printed page 24 (PDF page 22):

- **Article 98** permits faculty/institute general acts for their specifics, then states: “Одлуките од ставот 1 на овој член не смеат да бидат во спротивност со овој Правилник. Во случај на спротивност, се применува овој Правилник.” This supplies an express priority rule for conflicting unit acts; it is stronger evidence than merely choosing the newer date.
- **Article 99**: “Анексот 1 од член 97 од овој Правилник ќе се донесе во рок од 6 месеци од влегувањето во сила на овој Правилник.”
- **Article 100**: “Овој Правилник влегува во сила со денот на објавувањето во Универзитетски гласник.” Thus the recorded effective date is 2019-01-29.
- **Article 101**: “Студентите запишани до влегувањето во сила на овој Правилник, продолжуваат да студираат според правилата утврдени со студиските програми и одредбите од овој Правилник доколку се поповолни за нив.” Preserve this cohort/favourability condition when answering transitional questions.

There is **no explicit repeal clause** in the complete 417 text and no express wholesale repeal of FINKI's 2013 decision. Article 98 resolves the general priority of conflicting provisions, but does not justify marking every provision of the older faculty document superseded. FINKI 2013 article 32 (PDF page 14) explicitly repeals its own 2012 predecessor, not the later UKIM act.

607's preamble dates adoption to **31 March 2022**, and its Gazette headers show **6 April 2022**. Article 1 adds article 82(4): when an emergency, crisis or war is declared in the country from which a student transfers, the competent unit body may allow transfer even if fewer than 60% of programme credits will be completed at UKIM. Article 2 says: “Овој Правилник влегува во сила со денот на објавувањето во Универзитетски гласник.” Thus its effective date is 2022-04-06. It does not amend examination, objection or grade-entry rules.

These originals and the current index establish provenance and the specific amendment relationship, but not an exhaustive absence of later changes or present applicability to every cohort. Both additions therefore use `currentness_unresolved`; the existing 2013 document retains that status. No `amended_through` claim or synthetic consolidated text is supplied.

### Conflicting exam provisions

These are comparisons of the original Macedonian acts, not translations presented as legal text. The FINKI references below are to `raw/Pravilnik_studii_prv_vtor_ciklus_FINKI.pdf`.

| Topic | FINKI decision 02-959/1 (2013) | UKIM Gazette 417/2019 | Review finding |
|---|---|---|---|
| Commission examination | Article 11, PDF p. 4: “четвртиот пат, по барање на студентот” before a three-member commission. | Article 51, printed pp. 13–14 / PDF pp. 11–12: “Ако наставникот двапати го оцени испитот на студентот” with grade 5, the student may request a three-member commission from the dean/director; the original examiner is excluded. | Fourth attempt versus a right after two failing grades. Article 98's priority rule must be considered, along with article 101 for pre-entry-into-force students. |
| Objection | Article 14, PDF p. 5: to the dean within 24 hours of electronic grade entry; teacher reconsideration within 24 hours if the dean finds the conditions met, with a subsequent commission procedure. | Article 50, printed p. 13 / PDF p. 11: to the subject teacher within 3 working days of publication; reconsideration within 7 working days if the teacher finds the conditions met. Unit acts may regulate commission examination in these cases. | Different recipient, trigger, deadline and procedure. Do not combine the 24-hour trigger with the UKIM procedure. |
| Grade entry | Article 13, PDF p. 5: electronic entry within 10 working days plus 1 working day per 50 students from the exam; return of applications within 10 working days after the exam. | Article 56, printed p. 14 / PDF p. 12: final grades entered electronically and on applications, and delivered with the final-assessment report, within 5 working days from finality of the grade. Article 49 separately regulates publication within 7 working days of examination and inspection within 2 working days of publication. | The clock starts at different events; publication, finality and entry must remain distinct. |

**Higher-grade repeats are not a local-only rule.** UKIM article 60 (printed p. 15 / PDF p. 13) expressly allows a requested repeat for a higher final grade within at most four months of the exam; request goes to the dean, who annuls the grade by decision, and the repeat grade is final. FINKI article 14 also contains a four-month repeat rule, with different administrative routing.
