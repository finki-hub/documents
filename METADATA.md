# Corpus metadata evidence ledger

Audit date: **2026-09-01**

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
| `cenovnik-finki-2024-25-2` | 2024-07-04 | adopted / day | presumed_current | Date and 2024/25 applicability are printed in the text; it remains valid until replaced. No public decision URL was located. |
| `delovnik-za-rabota-glasnik-682` | 2024-04-22 | published / day | presumed_current | University Gazette 682; adopted 2024-04-01 and effective on publication; [FINKI legal acts](https://www.finki.ukim.mk/mk/zafakultetot/pravni_akti). |
| `etichki-kodeks-ukim-finki` | 2021-05-10 | published / day | current | University Gazette 549; adopted 2021-05-06 and effective on publication; [UKIM ethical code](https://ukim.edu.mk/univerzitet/dokumenti-2/normativni-akti-2/drugi-akti/etichki-kodeks/). |
| `grading-scale-finki` | unresolved | unresolved / none | current | The PDF carries no authoritative issuance date; FINKI's current [undergraduate documents and procedures page](https://finki.ukim.mk/studii-2/poddrshka/dokumenti-i-proceduri/dokumenti-i-proceduri-dodiplomski/) links it as the official grading scale. |
| `izveshtaj-samoevaluacija-finki-2023-2024` | 2023/2024 | coverage_period / academic_year | informational | The report states its coverage period; no signed issuance date is visible; [FINKI reports](https://finki.ukim.mk/za-nas/administracija-i-dokumenti/izveshtai-za-fakultetot/). |
| `lista-informacii-javen-karakter-finki` | 2012-10-30 | issued / day | stale_review_required | Archive number/date and immediate effect are printed; current FINKI page links a newer upload without a visible issuance date: [public-information page](https://finki.ukim.mk/en/za-nas/administracija-i-dokumenti/sloboden-pristap-do-informacii-od-javen-karakter/). |
| `lista-posrednici-voznemiruvanje-rabotno-mesto-finki` | 2026-05-18 | issued / day | current | Archive number/date and immediate effect are printed; personnel list requires periodic review; [official PDF](https://finki.ukim.mk/sites/default/files/u703/odluka-lista-za-posrednici-za-zastita-od-voznemirvanje-na-rabotno-mesto.pdf). |
| `odluka-plati-nadomestoci-finki-2026-02-19` | 2019-09-26 | adopted / day | currentness_unresolved | Base decision date is printed; the claimed 2026 consolidation cutoff lacks an amendment register or public source. |
| `odluka-sovet-kvalitet-finki` | 2019-09-26 | issued / day | stale_review_required | Decision 02-684/1; member mandates were three years and student mandates two years; [FINKI reports](https://finki.ukim.mk/za-nas/administracija-i-dokumenti/izveshtai-za-fakultetot/). |
| `pravilnik-doktorski-studii-po-stara-programa` | unresolved | unresolved / none | historical | Text expressly limits scope to the period through 2011-12-31; no adoption or publication date is present. |
| `pravilnik-iii-ciklus-2020` | 2020-12-31 | published / day | presumed_current | University Gazette 530/2020; [UKIM guide page and governing-rule reference](https://ukim.edu.mk/studii/informacii-za-studentite/vodich-za-studenti/). |
| `pravilnik-kvalitet-nastava-finki` | 2024-05-16 | adopted / day | current | Decision 02-629/2 and immediate effect are printed; [FINKI reports](https://finki.ukim.mk/za-nas/administracija-i-dokumenti/izveshtai-za-fakultetot/). |
| `pravilnik-standardi-evaluacija-153-2022` | 2022-07-06 | published / day | presumed_current | Official Gazette 153/2022; effective 2022-07-14; [UKIM quality system](https://ukim.edu.mk/univerzitet/kvalitet/sistem-za-kvalitet/). |
| `pravilnik-studii-prv-vtor-ciklus-finki` | 2013-07-04 | adopted / day | currentness_unresolved | FINKI decision 02-959/1; no later-currentness evidence was established; [FINKI legal acts](https://www.finki.ukim.mk/mk/zafakultetot/pravni_akti). |
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
