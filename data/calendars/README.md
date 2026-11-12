# Crop calendars

Two tables, built 2026-11-12 by the methods agent from the publications of CONAB, the
Brazilian national supply company (Companhia Nacional de Abastecimento), listed below. The raw PDFs, the extracted text and the intermediate bar tables are in
`F:\relative-land-productivity-data\calendars\raw`, not in the repo.

## conab_calendar.csv

One row per state x crop x season. Columns:

- `state`: two-letter UF.
- `crop`: CONAB crop name without accents (Soja, Milho, Feijao, Arroz, Algodao, Sorgo, Trigo,
  Amendoim, Girassol, Mamona, Aveia, Canola, Centeio, Cevada, Triticale, Cafe,
  Cana-de-acucar), plus Pastagem, Citrus, Outras perenes, Dende and Mosaico de usos for the
  MapBiomas classes that have no CONAB calendar.
- `season`: `1st`, `2nd`, `3rd`, `winter`, `perennial`, `semi-perennial` (sugarcane), `mixed`.
- `sowing_start_month`, `sowing_end_month`, `harvest_start_month`, `harvest_end_month`: calendar
  month numbers, 1 to 12, inclusive. A window that crosses the new year reads as, for example,
  sowing 9 to 12 and harvest 1 to 4. For sugarcane the sowing columns hold the development
  period that CONAB draws, not planting. Blank where CONAB gives nothing.
- `cycle_days_min`, `cycle_days_max`: the crop cycle length printed on the CONAB crop title
  page (for example soybean 105 to 135 days).
- `mapbiomas_classes`: the MapBiomas Collection 10 class or classes the crop maps to. 39
  soybean, 40 rice, 62 cotton, 20 sugarcane, 46 coffee, 47 citrus, 48 other perennial, 35 oil
  palm, 15 pasture, 21 mosaic of uses. Every other grain (maize, beans, sorghum, wheat, peanut,
  sunflower, castor, oats, canola, rye, barley, triticale) maps to `19;41`, the two temporary
  crop classes.
- `source`, `source_url`, `source_year`, `notes`.

Sources:

1. Grains: CONAB, Calendário de Plantio e Colheita de Grãos no Brasil 2022 (June 2022
   edition, ISSN 2318-6852),
   https://www.gov.br/conab/pt-br/acesso-a-informacao/institucional/publicacoes/arquivos-de-paginas/calendariozplantiozezcolheitazjunz2022.pdf.
   The calendar pages are bar charts, not tables: one panel per region, one row per state,
   twelve month columns from October to September, orange bars for sowing, blue for harvest,
   green where both overlap. The bars were read from the PDF vector drawings and mapped onto
   the month grid lines of the same panel (`extract_conab_calendar.py`, kept in the raw
   folder). A bar edge inside a month counts that month when it covers at least a quarter of
   it. 479 bars gave 197 state x crop-page windows; every window has both a sowing and a
   harvest bar. Where CONAB draws two separate bars of one kind (rice in Alagoas and Roraima,
   wheat in Goiás, second-season maize in the Distrito Federal and Paraíba) the table keeps
   the longest harvest bar and the sowing bar that precedes it, and `notes` lists all bars.
   The 2022 edition is the latest on the CONAB site; the page also lists a March 2021 revision.
2. Coffee: CONAB, Acompanhamento da Safra Brasileira de Café, v.12 n.4, December 2025,
   Table 4 (monthly harvest share by state, 2025 crop),
   https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/safra-de-cafe/4o-levantamento-de-cafe-safra-2025/boletim-cafe-dezembro-2025.
   Harvest months are the months with a nonzero share. States absent from the table (AC, PA,
   CE, PE, MS, DF) take the "Outros" group, April to September; the remaining states take
   the same window as a placeholder.
3. Sugarcane: CONAB, Acompanhamento da Safra Brasileira de Cana-de-Açúcar, v.14 n.1, April
   2026, per-state phase charts (Quadro 1 to 7) for SP, MG, GO, MS, MT, AL and PE,
   https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/safra-de-cana-de-acucar/arquivos-boletins/1o-levantamento-safra-2026-27/e-book_boletim-de-safras-cana_1o-lev-2026-27.pdf.
   Centro-Sul states: development May to March, milling April to December. Alagoas and
   Pernambuco: development October to August, milling September to March. Other Northeast
   states take the Alagoas window, every other state the São Paulo window (the November 2025
   bulletin says the Centro-Sul and Norte regions mill April to December and the Nordeste
   August to March). The bulletin text gives Rio Grande do Norte July to February.
4. Pasture, citrus, other perennial, oil palm and mosaic have no CONAB calendar. Their window
   is the full agricultural year. The MapBiomas pasture vigor product itself uses a 24-month
   NDVI window (Pasture Appendix ATBD Collection 10 v2, section 8).

## class_window_lookup.csv

What the extraction and analysis stages read: one row per state x MapBiomas class, 324
rows, with the NDVI integration window inside the September to August agricultural year
defined in `methods/METHODS.md`.

- `window_start_month`, `window_end_month`: calendar months, inclusive. `window_months` is
  the length.
- `window_rule`: how the window was chosen. Soybean (39), rice (40) and cotton (62) use the
  CONAB first-season window of that state, sowing start to harvest end. The temporary crop
  classes 19 and 41 use the union of the state's first and second season maize windows,
  because MapBiomas lumps maize, beans, cassava, wheat and more into them and maize is the
  dominant one in 23 of 27 states by harvested area (IBGE PAM 2023, table 5457; the
  exceptions are cassava in AL, AP, AM and RJ, wheat in RS and beans in PE). The dominant
  crop and its share are in `dominant_other_crop_pam2023` and `dominant_share_pct`; for
  maize the season with the larger area (PAM table 839) is named. Sugarcane, coffee,
  citrus, other perennial, oil palm, pasture and mosaic use the full year.
- `clipped_to_year`: 1 when the CONAB season crosses the agricultural year boundary and the
  window keeps only the longest part inside it. Cotton in the Centro-Oeste (sown December,
  harvested to September) loses September; soybean in Roraima and Alagoas (sown April to
  June, harvested August to October) keeps April to August.
- `fallback`: `neighbor XX` when CONAB has no row for that crop in that state and the window
  of a neighboring state was used (soybean in AC, AM, CE, ES, PB, PE, RJ, RN, SE; rice in BA
  and DF; cotton in 13 states where it is marginal). `no CONAB maize row` for Roraima's
  classes 19 and 41, which take the full year.

## Missing calendars and the fallback

CONAB covers grains, coffee and sugarcane only. Cassava, the dominant temporary crop in
Amazonas, Amapá, Alagoas and Rio de Janeiro, has no CONAB calendar; those states' classes
19 and 41 use the maize windows or the full year. Citrus, oil palm and other perennials have
none; they use the full year.

The Sacks global calendar at
`D:\WRI\Field Boundaries\Crop Calendars\ALL_CROPS_netCDF_0.5deg_filled` is the fallback for
any state x crop that a later check finds wrong. It is a 0.5 degree netCDF per crop
(`Soybeans.crop.calendar.fill.nc`, `Maize.crop.calendar.fill.nc`, `Maize.2.crop.calendar.fill.nc`,
`Cassava.crop.calendar.fill.nc`, `Rice.crop.calendar.fill.nc`, `Cotton.crop.calendar.fill.nc`
and others) with variables `plant.start`, `plant.end`, `harvest.start`, `harvest.end` in day
of year. Read with xarray and `decode_timedelta=False`. At 13 S, 56 W (Mato Grosso) the
soybean file gives planting day 291 to 365 and harvest day 59 to 152, which matches the
CONAB window of September to December and January to April within one month.
