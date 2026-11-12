# Relative land productivity, Brazil 2020 to 2024

A public web map that shows, field by field across Brazil, where crop and pasture
productivity rose or fell between 2020 and 2024, broken out by crop type. For each field
it states which land use decision the evidence points to: restore, switch crop, change the
land use pattern, abandon, intensify, improve yields, or keep.

Live: **https://tristangrupp.github.io/relative-land-productivity/**

Productivity is measured from the Sentinel-2 greenness record over the growing season,
with the growing season taken from the planting and harvest calendars that CONAB, the Brazilian national supply company, publishes per crop and state. Rainfall and
temperature changes that move greenness without moving yield are corrected for. The
quantity on the map is relative productivity: a field against the median of its peers in
the same crop and region, compared between 2020 and 2024. Pasture fields additionally use
the MapBiomas Collection 10 pasture vigor classes.

The suggestions are screening results from satellite greenness. They are not agronomic
advice.

## Status

The site is up with placeholder data: 2,576 real Trazo4 field outlines near Sorriso, Mato
Grosso, with random attribute values, so the interface can be exercised. The page shows a
banner while that is the case. The pipeline stages below are being built in parallel.

## Folder layout

```
BRIEF.md                 the project brief every agent reads first
README.md                this file
docs/                    the published static site, served by GitHub Pages from main /docs
  index.html             the map
  app.js                 map, layers, legend, field card
  config.js              tile URLs, attribute names, class definitions, state list
  style.css              tokens and layout
  methods.html           the methods page
  about.html             purpose, data sources, caveat
  STYLE.md               what the site takes from the two sites it matches
  DATA_CONTRACT.md       the attribute contract between the tiles and the page
  data/                  the placeholder tiles and statistics
pipeline/                numbered stages, one script each, each resumable per state
methods/METHODS.md       the productivity method, written before extraction starts
data/calendars/          CONAB calendar tables (small, committed)
data/summaries/          small JSON and CSV the site reads (committed)
serve.py                 local static server with HTTP range support
```

Bulk data lives outside the repository in `F:\relative-land-productivity-data` (fields,
grid, raw Earth Engine tiles, weather, extracted metrics, tiles before upload). Published
tiles go to `s3://wri-datalab-sandbox/trazofields/trazo4/relative-land-productivity/tiles/`.

## Running the site locally

```powershell
python serve.py            # http://127.0.0.1:8810
```

`serve.py` exists because Python's stock static handler ignores `Range` headers. PMTiles
readers ask for byte ranges; without 206 responses every tile request downloads the whole
archive.

The map reads MapLibre GL and the pmtiles protocol from unpkg at pinned versions, and the
basemap from OpenFreeMap, so it needs a network connection even when served locally.

`docs/config.js` holds every URL and attribute name. `USE_PLACEHOLDER: true` keeps the
page on `docs/data/`; set it to `false` to read the S3 tiles.

## Pipeline

| stage | script | what it does | state |
|---|---|---|---|
| s01 | `pipeline/s01_*` | prepare field GeoParquet per state and year from the Trazo4 seamfix copy, with valid geometries | not yet built |
| s02 | `pipeline/s02_*` | the extraction grid and tile index | not yet built |
| s03 | `pipeline/s03_*` | per-field greenness and weather extraction through Earth Engine computePixels, resumable per state | not yet built |
| s04 | `pipeline/s04_*` | relative productivity, weather adjustment, change classes, decisions | not yet built |
| s05 | `pipeline/s05_*` | PMTiles with tippecanoe, summary layer, stats.json, upload to S3 | not yet built |
| site | `docs/` | the map, wired to the tiles through `docs/config.js` | built, on placeholder data |

## Writing rules

Plain prose, active voice, short sentences. No em dashes or en dashes anywhere, including
code comments, commit messages, and JSON keys. No form of the verb "carry". American
spelling.
