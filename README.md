# Relative land productivity, Brazil 2020 to 2024

See AGENTS.md for agent instructions, WORKLOG.md for project status and DECISIONS.md
for the decision register.

This map shows how the relative productivity of crops and pasture changed across Brazil
between the 2020 and 2024 agricultural years. It suggests land use options such as
restoration, improving yields or converting existing pasture to crops.

Live: **https://tristangrupp.github.io/relative-land-productivity/**

The map compares each field with nearby fields of the same crop. It measures greenness
from satellite images during the growing season, using CONAB crop calendars and adjusting
for rainfall and temperature. Area recommendations compare crops and pasture with the same
uses across Brazil. Use the suggestions to identify fields for further investigation.

## Status

The 13 November 2026 release covered 24,554,482 Trazo4 fields across all 27 states
and marked another 748,022 fields from 2020 as abandoned.

- The initial release used MODIS MOD13Q1 (250 m, 16-day NDVI). A MODIS pixel is larger than
  78 percent of fields. The site’s About page lists the states that use 30 m Sentinel-2.
- Pasture scores use NDVI because no public GeoTIFF of MapBiomas pasture vigor was available.
- The weather model explained little (median R squared 0.15 across 134 crop and state
  pairs). Adjusted soybean scores correlated weakly with municipal yields (Spearman
  0.06 in 2020 and 0.18 in 2024). See section 8 of `docs/methods.html`.
- In the initial release, 375,000 fields had too few clear observations in one year.
  The map gave no suggestion for 2,020,646 fields that were newly cropped or lacked data.

## Folder layout

```
BRIEF.md                 the project brief every agent reads first
README.md                this file
docs/                    the published static site, served by GitHub Pages from main /docs
  index.html             the map
  app.js                 map, layers, legend, field card, confidence control
  config.js              tile URLs, attribute names, class definitions, state list
  style.css              tokens and layout
  methods.html           the methods page, written from methods/METHODS.md and pipeline/ANALYZE.md
  about.html             purpose, what the release holds, data sources, caveats
  STYLE.md               what the site takes from the two sites it matches
  DATA_CONTRACT.md       the attribute contract between the tiles and the page
  data/                  the placeholder tiles and statistics (kept for development)
pipeline/                numbered stages, one script each, each resumable per state
methods/METHODS.md       the productivity method, written before extraction started
data/calendars/          CONAB calendar tables (small, committed)
data/summaries/          weather_fit.csv and validation.csv (small, committed)
serve.py                 local static server with HTTP range support
```

Bulk data lives outside the repository in `F:\relative-land-productivity-data` (fields,
grid, weather, extracted metrics, analysis tables, tiles before upload). Published tiles are
public read at
`https://wri-datalab-sandbox.s3.amazonaws.com/trazofields/trazo4/relative-land-productivity/tiles/`:
`fields.pmtiles` (6.40 GB, zoom 9 to 13), `summary.pmtiles` (H3 resolution 6 at zooms 3
to 9) and `stats.json`.

## Running the site locally

```powershell
python serve.py            # http://127.0.0.1:8810
```

`serve.py` exists because Python's stock static handler ignores `Range` headers. PMTiles
readers ask for byte ranges; without 206 responses every tile request downloads the whole
archive. With `USE_PLACEHOLDER: false` the local page reads the S3 tiles directly, so the
range handling only matters for the placeholder set.

The map reads MapLibre GL and the pmtiles protocol from unpkg at pinned versions, and the
basemap from OpenFreeMap, so it needs a network connection even when served locally.

`docs/config.js` holds every URL and attribute name. `USE_PLACEHOLDER: true` keeps the
page on `docs/data/`; it is `false` in the released site.

## Pipeline

| stage | script | what it does |
|---|---|---|
| s01 | `pipeline/s01_*` | prepare field GeoParquet per state and year from the Trazo4 seamfix copy, with valid geometries |
| s02 | `pipeline/s02_*` | the extraction grid and tile index |
| s03 | `pipeline/s03_*` | per-field greenness (MODIS MOD13Q1; Sentinel-2 in `s03g` and `s03h`), MapBiomas class and weather extraction, resumable per state; see `pipeline/EXTRACT.md` and `pipeline/EXTRACT_S2.md` |
| s04 | `pipeline/s04_*` | metrics, relative productivity, weather adjustment, change classes, decisions, validation; see `pipeline/ANALYZE.md` |
| s05 | `pipeline/s05_*` | PMTiles with tippecanoe, summary layer, stats.json, upload to S3 |
| s06 | `pipeline/s06_ecoregion_peers.py` | RESOLVE 2017 ecoregion scores: field against ecoregion, cell against ecoregion (the area term), ecoregion against nation; see `pipeline/EXPLORE_ECOREGIONS.md` |
| s07 | `pipeline/s07_weather_refit.py`, `pipeline/s07_decisions.py` | the ecoregion weather refit test (not adopted) and the two-tier decisions, written into `fields_scored.parquet` (`decision`, `decision_computed`, `area_decision`, `area_level`, `decision_v1`, `eco_id`, `eco_trend`, `biome`, `source`, the native vegetation and regrowth columns) and `docs/data/ecoregions.json`; the area call per H3 resolution 6 cell with resolution 5 fallback, the IBGE biome per field (`biome` step) and native vegetation, patch size and regrowth around each field from MapBiomas 2020, 2023 and 2024 (`native` step); run after s04_change and s06 score, before s05; see `pipeline/DECISIONS_V2.md` |
| s08 | `pipeline/s08_s2_compare.py` | Sentinel-2 change classes, the calibration of s2 to the MODIS national reference, the comparison with MODIS and the noise measurement that sets a swapped state's change scale; writes under `analysis\source=s2\`; see `pipeline/S2_MATO_GROSSO.md` |
| s09 | `pipeline/s09_swap_state_to_s2.py --state <State>` | switches one state of the live map from MODIS to Sentinel-2 (assemble, metrics, relative, compare and calibrate, swap, decisions, tiles, upload); keeps the MODIS tables under `analysis\source=modis\`; records the state in `analysis\sources.json` and `data/summaries/sources.json`. Mato Grosso since 14 November 2026 |
| site | `docs/` | the map, wired to the tiles through `docs/config.js` |

## Writing rules

Plain prose, active voice, short sentences. No em dashes or en dashes anywhere, including
code comments, commit messages, and JSON keys. No form of the verb "carry". American
spelling.
