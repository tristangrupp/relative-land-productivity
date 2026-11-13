# Relative land productivity, Brazil 2020 to 2024

A public web map that shows, field by field across Brazil, where crop and pasture
productivity rose or fell between the 2020 and 2024 agricultural years, broken out by crop
type. For each field it states which land use decision the evidence points to: restore,
switch crop, change the land use pattern, abandon, intensify, improve yields, or keep.

Live: **https://tristangrupp.github.io/relative-land-productivity/**

Productivity is measured from the satellite greenness record over the growing season, with
the growing season taken from the planting and harvest calendars that CONAB, the Brazilian
national supply company, publishes per crop and state. Rainfall and temperature changes that
move greenness without moving yield are corrected for. The quantity on the map is relative
productivity: a field against the median of its peers in the same crop and region, compared
between 2020 and 2024.

The suggestions are screening results from satellite greenness. They are not agronomic
advice.

## Status

Released on real data on 13 November 2026: 24,554,482 Trazo4 fields in all 27 states, plus
748,022 fields from the 2020 delineation shown as abandoned. The greenness source of this
release is MODIS MOD13Q1 (250 m, 16-day NDVI). Its caveats, stated on the site:

- 78 percent of fields are smaller than one MODIS pixel; 83 percent of fields are marked
  low confidence, and the map can fade or hide them. A Sentinel-2 run at 30 m is being
  extracted for Mato Grosso and the other tier 1 states and will replace the MODIS values
  there.
- Pasture vigor from MapBiomas is not implemented (no public GeoTIFF was found); the vigor
  attributes are null and the vigor view is left off the map.
- The weather regression explains little (median R squared 0.15 over 134 fitted crop by
  state pairs) and the municipal yield validation is weak (soybean Spearman 0.06 in 2020
  and 0.18 in 2024 for the adjusted relative metric). `docs/methods.html` section 8 has the
  table and the reasons.
- 375,000 fields have no data (too few clear composites in one year) and 2,020,646 fields
  get no suggestion (newly cropped or no data).

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
`fields.pmtiles` (6.36 GB, zoom 9 to 13), `summary.pmtiles` (26 MB, H3 resolution 4 at zooms 3
to 5, 5 at zooms 6 to 7, 6 at zooms 8 to 9) and `stats.json`.

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
| site | `docs/` | the map, wired to the tiles through `docs/config.js` |

No Google Earth Engine is used anywhere. Every raster is downloaded or streamed and reduced
to fields on one machine.

## Writing rules

Plain prose, active voice, short sentences. No em dashes or en dashes anywhere, including
code comments, commit messages, and JSON keys. No form of the verb "carry". American
spelling.
