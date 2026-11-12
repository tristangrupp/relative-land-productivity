# Relative land productivity, Brazil 2020 to 2024: project brief

Written 2026-11-12 by the orchestrating session. Every agent on this project reads this file
first. It states the goal, the data, the compute rules, the folder contract and the writing
rules. Agents append to the "Decisions" section at the bottom when they settle something other
agents depend on. Nobody edits another agent's section.

## Goal

A public web map at https://tristangrupp.github.io/relative-land-productivity/ that shows,
field by field across Brazil, where crop and pasture productivity rose or fell between 2020 and
2024, broken out by crop type. The purpose is to say, at the field level, which land use
decision could be improved: restore the land, switch the crop, change the land use pattern,
abandon the field, intensify, or improve yields on the same crop.

Productivity is measured from the greenness record over the growing season, with the growing
season taken from CONAB crop calendars per crop and state. The measure must not confuse NDVI
with productivity when the weather swings: precipitation and temperature changes that move
NDVI without moving yield have to be corrected for. The quantity of interest is relative
productivity, a field against its peers in the same crop and region, compared between 2020 and
2024.

Pasture fields additionally use the MapBiomas Collection 10 pasture vigor product (low, medium,
high per pixel, 2020 to 2024), which already is a biome-normalized productivity class.

## Priority geography

Preferred: all of Brazil. If compute does not allow it, tier 1 first: Mato Grosso, Pará,
Amazonas, Acre, Rondônia, Roraima, Amapá. Tier 2: Mato Grosso do Sul, Goiás, Tocantins,
Maranhão. Build every pipeline so it runs per state and resumes, then order the run tier 1,
tier 2, rest.

## The field boundaries

`E:\trazo4_master_parquet_seamfix` is the best all-country Trazo4 copy: 236,165,655 fields with
the seam repair. Hive layout `country=Brazil\state=<State>\year=<YYYY>\part-0.parquet`. Columns
and read patterns: `D:\WRI\Field Boundaries\trazo-fields\release\README.md`. Short version:

- `fid`, `layer`, `geography`, `Id`, `area_ha` (ESRI:102033 equal area), `mbmode` (int16, modal
  MapBiomas class of that year), `mbcov_area_m2`, `mbvalid_area_m2`, `hansen_loss_year`,
  `hansen_loss_frac`, `hansen_frac_2019..2024`, `geom` (WKB, EPSG:4326), `geom_bbox` (struct,
  GeoParquet 1.1 bbox covering), plus `seam_repair` and `seam_src_fids`.
- `country`, `state`, `year` live only in the path. Read a lone part with
  `pyarrow.parquet.ParquetFile(path).read()`, not `pq.read_table` (it conflicts on `year`).
- Many layers declare MultiPolygon but hold single Polygons, and about 9 percent of rows have
  ArcGIS ring self-touches. Run `shapely.make_valid` and promote Polygon to MultiPolygon before
  any union, overlay or tile cut.
- `Table.take` on the big layers overflows 32-bit WKB offsets. Cast `geom` to `large_binary`
  first.
- Nothing is land-cover filtered. `mbmode` holds forest, water, urban and mining too. MapBiomas
  codes in use: 39 soybean, 15 pasture, 19 and 41 temporary crop, 20 sugarcane, 40 rice,
  62 cotton, 21 mosaic of uses, 9 forest plantation, 18 agriculture, 46 coffee, 47 citrus,
  48 other perennial, 35 oil palm, 3 forest, 4 savanna, 12 grassland, 24 urban, 30 mining,
  33 water.
- DuckDB `ST_Area_Spheroid` is badly wrong on these polygons. Use `area_ha`, or reproject to
  ESRI:102033.

Brazil counts in the seamfix copy (all classes / agricultural classes 39,15,19,41,20,40,62,21,
18,46,47,48,35,9):

| year | fields | agricultural |
|---|---|---|
| 2020 | 26,298,376 | 23,636,217 |
| 2024 | 29,176,172 | 26,554,283 |

Tier 1 2024: Mato Grosso 1,299,476; Pará 1,553,660; Amazonas 279,435; Acre 194,242; Rondônia
643,631; Roraima 112,815; Amapá 54,372.

2020 and 2024 polygons are different delineations of the same land. The change map lives on the
2024 geometries: compute every metric for both years on the 2024 polygons (the pixels exist
whatever the boundary), and compute the 2020 metrics on the 2020 polygons as well for the 2020
map and for fields that disappeared. The 2020 crop type of a 2024 polygon comes from the
MapBiomas 2020 coverage raster
(`s3://wri-datalab-sandbox/trazofields/mapbiomas/brazil_coverage_2020.tif`, 785 MB, public
read), modal class inside the polygon, so crop switching is visible per field.

## Other inputs

- CONAB crop calendars: Calendário de Plantio e Colheita, published per crop and state by
  CONAB. Not on disk. `D:\WRI\Field Boundaries\Crop Calendars\ALL_CROPS_netCDF_0.5deg_filled`
  is the Sacks global calendar, a fallback only. CONAB field mapping shapefiles (crop type
  reference) are in `D:\WRI\Field Boundaries\CONAB` and `D:\WRI\Field Boundaries\Brazil Data`.
- MapBiomas Collection 10 as GeoTIFF downloads, never through Earth Engine: land cover
  coverage per year from the MapBiomas public bucket
  (`https://storage.googleapis.com/mapbiomas-public/initiatives/brasil/collection_10/lclu/coverage/brasil_coverage_<YYYY>.tif`,
  check the exact path on the MapBiomas download page) or the copies already on
  `s3://wri-datalab-sandbox/trazofields/mapbiomas/brazil_coverage_<YYYY>.tif` (public read, 2019
  to 2024, about 790 MB each; confirm which collection they are from the file metadata);
  pasture vigor, biomass and age from the MapBiomas pasture quality downloads. The Pará pipeline
  stages `s03_zonal.py` and `s05_tiles.py` under
  `D:\generative restoration\restoration-explorer-para\pipeline\` remain useful patterns for
  zonal reduction and PMTiles; its `s01_ee_rasters.py` is an Earth Engine downloader and must
  not be reused.
- Sentinel-2: Planetary Computer STAC `sentinel-2-l2a`, bands B04, B08, SCL, signed with
  `planetary_computer.sign`, loaded with `odc.stac` at the target resolution so reads use the
  COG overviews. The drought repo did exactly this, see
  `C:\Users\grupp\src\agriculture-and-drought\pipeline\field_response.py`.
- Weather: CHIRPS monthly GeoTIFFs from
  `https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_monthly/tifs/`, and a public monthly
  temperature product covering 2015 to 2024 (TerraClimate on the Planetary Computer if 2024 is
  published, otherwise ERA5 from the Planetary Computer or AWS open data mirrors).

## Compute rules (not negotiable)

- No Earth Engine, in any form. The user forbade the project `tkt-tristan` on 2026-11-12 and
  then chose the Planetary Computer path for everything. Scripts must not import `ee`.
- All reduction to fields runs on this machine: download or stream the rasters, build
  exactextract coverage weights once per grid, reduce every band as a sparse matrix product.
- No AWS compute of any kind. S3 is storage only.
- S3 target: `s3://wri-datalab-sandbox/trazofields/trazo4/` with AWS profile `mfr-datalab`
  (SSO; `aws s3 ls` works right now). If the session expires: `aws sso login --profile
  mfr-datalab --no-browser`, print the URL and stop; the user approves it in Edge. The bucket is
  public read with CORS, so PMTiles served from it work on GitHub Pages. Put this project's
  outputs under `trazofields/trazo4/relative-land-productivity/`.
- Do not modify anything under `E:\`. Do not delete data folders. Write new folders instead.
- GPU is not needed for this project.
- Disk: data root is `F:\relative-land-productivity-data` (606 GB free on F:). Never write bulk
  data into the git repo.

## Python environments

- `E:\Water\water intelligence\wci_tools\.venv\Scripts\python.exe` (3.12): geopandas 1.2,
  shapely 2.2, duckdb, pyarrow, rasterio 1.5, exactextract 0.3, earthengine-api, pystac_client,
  planetary_computer, xarray, rioxarray, h3. Best for extraction and zonal work.
- `C:\Users\grupp\miniconda3\envs\ftwtools\python.exe` (3.12): geopandas, rasterio, ee,
  odc.stac, stackstac; no duckdb, no exactextract.
- `C:\Users\grupp\AppData\Local\ESRI\conda\envs\crop\python.exe` (3.11): GDAL network reads
  crash here. Avoid.
- `duckdb` CLI is on PATH. tippecanoe v2.80 and tile-join live in WSL `Ubuntu-22.04`
  (`wsl -d Ubuntu-22.04 -- tippecanoe ...`; Windows paths are `/mnt/f/...`). No GDAL CLI on
  Windows PATH; use rasterio.
- Per-field reduction pattern that scales: build exactextract coverage weights once per grid
  (cell id plus coverage fraction), then every band is a sparse matrix product. The wci_tools
  Ohio pipeline does this for 289k fields in 2 minutes per layer.

## Folder contract

```
C:\Users\grupp\src\relative-land-productivity\     git repo, pushed to GitHub, Pages from docs/
  BRIEF.md                 this file
  README.md                project readme (site agent owns)
  docs/                    the published static site (site agent owns)
  pipeline/                numbered stages, one script each, each resumable per state
  methods/METHODS.md       the productivity method, written before extraction starts
  data/calendars/          CONAB calendar tables (small, committed)
  data/summaries/          small JSON and CSV the site reads (committed)
F:\relative-land-productivity-data\
  fields\                  prepared field GeoParquet per state and year
  grid\                    the extraction grid and tile index
  raw\s2\                  Sentinel-2 composites per tile and period
  raw\mapbiomas\           MapBiomas coverage and pasture rasters
  weather\
  extracted\               per-field metrics per state and year
  tiles\                   PMTiles before upload
```

## Writing rules for everything a person reads

Plain prose, active voice, short sentences. No em dashes or en dashes anywhere, including code
comments, commit messages and JSON keys. No form of the verb "carry". American spelling. Do not
grade your own prose, do not give the reader stage directions, no two-beat fragments for rhythm,
say each fact once. Define a term the first time it appears. Commit messages end with
`Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

Report numbers exactly, say what was verified and how, and say when something has not been
seen running.

## Agents and ownership

| agent | owns | depends on |
|---|---|---|
| methods | `methods/METHODS.md`, `data/calendars/` | nothing |
| fields | `F:\...\fields`, `F:\...\grid`, `pipeline/s01_*`, `pipeline/s02_*` | nothing |
| probe | `pipeline/s03_*` prototype, `F:\...\weather`, throughput numbers | nothing |
| site | repo scaffold, `docs/`, `README.md`, GitHub Pages | nothing |
| extract | the full `s03` run | methods, fields, probe |
| analyze | `s04` metrics and change classes, `s05` tiles, S3 upload | extract |
| integrate | site wired to real tiles and summaries | analyze, site |

## Decisions

Append dated entries here. Keep each one to a few lines.

- 2026-11-12 orchestrator: NDVI source is Planetary Computer Sentinel-2 L2A with SCL cloud
  masking, composited locally per tile and period, target 30 m. 30 m keeps a whole country
  feasible (median field 2.1 ha is about 23 pixels). The probe agent measures whether 20 m is
  affordable for tier 1 and records the answer here. An Earth Engine plan existed for a few
  hours the same day and was dropped.
- 2026-11-12 orchestrator: time windows are two 12-month agricultural years, the same months in
  both, chosen by the methods agent so that first and second season crops both fall inside.
  Composite cadence is set by the methods agent (monthly or 16-day) and costed by the probe.
- 2026-11-12 probe: stopped after 4 tiles (project forbidden); one cold measurement, 39 s
  and 3.58 MB per 30 m monthly tile, parallel throughput unmeasured. For a 48 hour budget:
  tier 1 at 30 m monthly (3,536 tiles, 84,864 requests, needs about 19 in flight), all
  Brazil at 30 m monthly only with about 48 in flight and reduce-then-delete; see pipeline/PROBE.md.
- 2026-11-12 site: the tile attribute contract is fixed in `docs/config.js` (`ATTR`,
  `SUMMARY_ATTR`) and written out in `docs/DATA_CONTRACT.md`. Fields layer: fid, area_ha,
  crop_2020, crop_2024, prod_2020, prod_2024, change, change_class, vigor_2020, vigor_2024,
  decision, n_obs_2020, n_obs_2024, muni_code. Tile names on S3: fields.pmtiles (layer
  `fields`, zoom 9 to 14), summary.pmtiles (layer `summary`, zoom 3 to 9), stats.json. The
  site is live on placeholder data; flip `USE_PLACEHOLDER` to false when the real tiles exist.
