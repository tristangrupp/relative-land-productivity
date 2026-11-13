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
| 2020 | 26,297,376 | 21,632,817 |
| 2024 | 29,176,172 | 24,554,482 |

Tier 1 2024: Mato Grosso 1,299,476; Pará 1,553,660; Amazonas 279,435; Acre 194,242; Rondônia
643,631; Roraima 112,815; Amapá 54,372.

2020 and 2024 polygons are different delineations of the same land. The change map lives on the
2024 geometries: compute every metric for both years on the 2024 polygons (the pixels exist
whatever the boundary), and compute the 2020 metrics on the 2020 polygons as well for the 2020
map and for fields that disappeared. The 2020 crop type of a 2024 polygon comes from the
MapBiomas 2020 coverage raster
(`s3://wri-datalab-sandbox/trazofields/brazil_coverage_2020.tif`, 785 MB, public read), modal class inside the polygon, so crop switching is visible per field.

## Other inputs

- CONAB crop calendars: Calendário de Plantio e Colheita, published per crop and state by
  CONAB. Not on disk. `D:\WRI\Field Boundaries\Crop Calendars\ALL_CROPS_netCDF_0.5deg_filled`
  is the Sacks global calendar, a fallback only. CONAB field mapping shapefiles (crop type
  reference) are in `D:\WRI\Field Boundaries\CONAB` and `D:\WRI\Field Boundaries\Brazil Data`.
- MapBiomas Collection 10 as GeoTIFF downloads, never through Earth Engine: land cover
  coverage per year from the MapBiomas public bucket
  (`https://storage.googleapis.com/mapbiomas-public/initiatives/brasil/collection_10/lclu/coverage/brasil_coverage_<YYYY>.tif`,
  check the exact path on the MapBiomas download page) or the copies already on
  `s3://wri-datalab-sandbox/trazofields/brazil_coverage_<YYYY>.tif` (directly under trazofields,
  public read, 2019 to 2024, about 790 MB each, EPSG:4326, 154470 x 146483 px, pixel
  0.0002694945852358564, origin -74.02099974839176 / 5.435705784207225, uint8, no overviews);
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
- 2026-11-12 probe (Planetary Computer, no Earth Engine): a 30 m monthly 1024-px tile
  takes 60 to 220 s and about 50 MB of COG reads on this machine's shared link, and 4 or 8
  tiles in flight give the same 0.35 to 0.37 tiles per minute, so tier 1 at 30 m monthly
  (84,864 tile loads) is 1,800 to 3,800 hours, 38 to 80 times a 48 hour budget; 20 m and
  16-day double it. Recommendation: 30 m monthly only, tier 1 only, Mato Grosso first,
  with scene thinning and a dedicated link measured before committing; all Brazil is out
  of reach on this path. Subtract the 1000 reflectance offset on baseline 04.00 scenes
  (2022 onward) or NDVI is compressed. Details and tables in pipeline/PROBE.md.
- 2026-11-12 methods: agricultural year runs 1 September to 31 August ("2020" is 2019-09-01
  to 2020-08-31), so September soybean sowing in MT, MS, PR, SC, SP and the August end of
  second-season maize both fall inside.
- 2026-11-12 methods: cadence is monthly, 12 per-pixel maximum NDVI composites per year from
  SCL-masked Sentinel-2 L2A (drop SCL 0, 1, 3, 8, 9, 10, 11), with a clear-scene count band;
  gaps filled by linear interpolation and a per-field valid-month count kept as the flag.
- 2026-11-12 methods: peer region is the H3 resolution 5 cell (about 253 km²) of the field
  centroid, per class and year, minimum 30 fields, falling back to resolution 4 then 3.
- 2026-11-12 methods: headline metric is the seasonal NDVI integral above the field's own
  annual minimum, summed over the state x class calendar window from
  `data/calendars/class_window_lookup.csv`; peak NDVI, peak timing and the full-year integral
  are kept as diagnostics. Temperature: TerraClimate yearly netCDF from the Idaho server (the
  Planetary Computer copies end in 2021 and 2020), else NASA POWER monthly.
- 2026-11-12 site: the tile attribute contract is fixed in `docs/config.js` (`ATTR`,
  `SUMMARY_ATTR`) and written out in `docs/DATA_CONTRACT.md`. Fields layer: fid, area_ha,
  crop_2020, crop_2024, prod_2020, prod_2024, change, change_class, vigor_2020, vigor_2024,
  decision, n_obs_2020, n_obs_2024, muni_code. Tile names on S3: fields.pmtiles (layer
  `fields`, zoom 9 to 14), summary.pmtiles (layer `summary`, zoom 3 to 9), stats.json. The
  site is live on placeholder data; flip `USE_PLACEHOLDER` to false when the real tiles exist.
- 2026-11-12 orchestrator: the extraction grid is the grid of the S3 coverage GeoTIFFs
  `trazofields/brazil_coverage_<YYYY>.tif`, read from their headers with rasterio, not the Earth
  Engine asset grid (which differs by about 1 pixel in longitude and 110 pixels in latitude).
- 2026-11-12 fields: the extraction grid is the pixel grid of the MapBiomas Collection 10
  coverage GeoTIFFs `s3://wri-datalab-sandbox/trazofields/brazil_coverage_<YYYY>.tif` (public
  read; 2020 and 2024 share it): EPSG:4326, 154,470 x 146,483 pixels of 0.0002694945852358564
  degrees, upper left origin (-74.02099974839176, 5.435705784207225), read from the file header
  with rasterio. Tiles are 1024 x 1024 pixels anchored at that origin, named r<row>_c<col>, row
  0 north and col 0 west, 151 x 144 tiles over the raster. `pipeline/s02_grid.py` writes
  `F:\relative-land-productivity-data\grid\grid.json`, `tiles.parquet` and `field_tiles\`.
  Tiles that touch a prepared 2020 or 2024 field: 8,007 in total, 3,406 in tier 1, 1,475 in
  tier 2, 3,126 in tier 3; 47,014,021 field-tile pairs. Prepared fields (agricultural classes,
  after make_valid, no empties): 21,632,817 for 2020 and 24,554,482 for 2024. The agricultural
  column in the table above overstates both years by about 2.0 million; the per-class counts of
  the seamfix files give these lower numbers and no excluded class accounts for the gap.
- 2026-11-12 orchestrator: the machine's internet link is shared with two other projects'
  downloads until at least tomorrow night (a 4.6 MB/s AguaTrack pull until about 18:40 today
  and a Planetary Computer Sentinel-2 fetch with three workers for another day), and the probe
  measured 0.37 tiles per minute on it. Tier 1 at 30 m is therefore 38 to 80 times a 48 hour
  budget. Decision: run the national product on MODIS MOD13Q1 (Planetary Computer collection
  `modis-13Q1-061`, 250 m, 16-day NDVI with VI quality), reduced to every field with coverage
  weights and a confidence flag by field area (fields under one MODIS pixel, 6.25 ha, are low
  confidence). Sentinel-2 at 30 m stays as a later upgrade for Mato Grosso and then tier 1,
  with scene thinning, once the link is free. The methods apply unchanged except that the
  cadence is 16 days (23 composites per agricultural year) instead of monthly.
- 2026-11-12 extract-s2: Sentinel-2 30 m monthly maximum NDVI per field runs as
  `pipeline/s03g_s2_fetch_reduce.py` (fetch, mask, composite, sparse reduction, no raster
  kept) with weights from `s03g_weights.py` and assembly in `s03h_s2_assemble.py`; details
  in `pipeline/EXTRACT_S2.md`. Measured on 20 Mato Grosso tiles for January 2024 with 4
  tiles in flight: 9.05 tile-months per minute, 44 MB per tile-month, 6.6 MB/s, after
  dropping the MGRS granules that only repeat another granule's pixels (135 items read fell
  to 81). Eight tiles in flight gave no more. The read volume is three times the 15 MB
  expected: one granule-day of B04, B08 and SCL at the 20 m overview costs 10 to 15 MB with
  block over-read. Day rule in production: the three least cloudy days (four when all three
  exceed 60 percent cloud), and `--min-days 2` stops at two days once the chance a pixel was
  clear on a kept day reaches 0.98; thinning to three days lowered the soybean January
  median by 0.025 on the Sorriso tile against all seven days. Projection at the measured
  rate: Mato Grosso (24,312 tile-months) 45 h and 1.07 TB, tier 1 (81,744) 151 h and 3.6 TB,
  tier 2 (35,400) 65 h and 1.56 TB; the first two minutes of the production run with
  `--min-days 2` ran at 13.9 tile-months per minute and 33.7 MB each (Mato Grosso 29 h at
  that rate). Running since 14:35 as a detached process (pid 36992), tier 1 then tier 2,
  progress in `F:\relative-land-productivity-data\extracted\s2\progress.log`; peak memory
  0.65 GB for the whole process.
- 2026-11-12 extract: the MODIS run is `s03c_modis_fetch.py` (Terra MOD13Q1 only, 23 composites
  per agricultural year from day 241 of the year before to day 225, 18 sinusoidal tiles that
  touch fields, three files in flight on the shared link), `s03d_modis_weights.py` (exactextract
  coverage weights per tile and year on the native 231.656 m grid, CSR under `weights\modis`),
  `s03e_modis_reduce.py` (coverage-weighted mean per field, pixel_reliability 2 and 3 and
  MODLAND QA 2 and 3 masked, a composite is missing for a field when under half its covered
  area is valid, 23 raw columns plus 23 linearly interpolated columns and `n_valid`, under
  `extracted\modis`) and `s03f_mapbiomas_fields.py` (modal MapBiomas class per field from the
  2020 and 2024 coverage rasters by pixel-center rasterization, under `extracted\mapbiomas`).
  Facts the analyze agent must plan around: 78 percent of fields are under 6.25 ha, so most read
  one or two shared cells (`small_field`, `n_cells`, `dominant_share` are in the tables); Terra
  composite A2024225 does not exist on the Planetary Computer and is interpolated; Pará
  wet-season composites are valid for 31 to 45 percent of fields, so `n_valid` must gate the
  classes; pasture vigor is null because no public GeoTIFF was found (the MapBiomas platform
  offers a Collection 11 "Vigor condition" custom GeoTIFF per year without a login, untested).
  Details and numbers in `pipeline/EXTRACT.md`.
- 2026-11-12 analyze: stages `s04_xyear_reduce.py` (2020 composites reduced with the 2024
  weights, since the extract tables couple polygon year and composite year), `s04_metrics.py`
  (source flag modis or s2; integrals in NDVI-months; weather baseline is the nine complete
  agricultural years 2016 to 2024), `s04_relative.py` (peer class pools MapBiomas 19 and 41;
  layer 2 fitted only with at least 30 groups over both years, evaluated inside the fitted
  anomaly range, capped at half the intercept), `s04_change.py` (METHODS.md SD thresholds;
  `no_data` and decision `none` are extra values the site must tolerate; abandoned and newly
  cropped use the class rule only, no overlay), `s04_validate.py`, `s05_tiles.py` (fields
  zoom 9 to 13 with overzoom beyond, nothing dropped at 12 and 13, smallest-first
  coalescing at 9 to 11, tippecanoe output on the WSL disk), `s05_upload.py`. The national
  run is `s04_run_all.py`, started 22:35 as pid 37580, log
  `F:\relative-land-productivity-data\analysis\run_all.log`. Details in `pipeline/ANALYZE.md`.
- 2026-11-13 integrate: the site reads the released S3 tiles (`USE_PLACEHOLDER` false). Read
  back from the PMTiles metadata: the fields layer runs zoom 9 to 13 (not 14) and MapLibre
  overzooms it; it holds `confidence` (high or low) and no vigor attributes, and `r_adj_*`
  are not in the tiles; the summary layer is H3 resolution 6 with `share_no_data` and no
  `mean_vigor_change`. The site adds legend entries for `no_data` and decision `none`, a
  low-confidence control (draw, fade, hide) in the Where card, the stats.json shares of no
  data and low confidence (83 percent nationally), and SD-threshold legend text. The pasture
  vigor view is left off the nav. `docs/methods.html` is written from METHODS.md and
  ANALYZE.md with the weather fit (134 of 176 pairs, median R squared 0.15) and the national
  validation table. Verified with curl: range requests on both PMTiles return 206 with
  `Access-Control-Allow-Origin: *`, and the remote stats.json is byte-identical to the local
  copy.

### 2026-11-13 orchestrator, work log
WORKLOG.md at the repo root is the running record of state, decisions and open items, kept
so the work survives a context reset. Every agent appends a dated entry to its Log section
before it ends, in addition to the Decisions entry here.
- 2026-11-13 ecoregions: `pipeline/s06_ecoregion_peers.py` scores the 2024 polygons against
  RESOLVE 2017 ecoregion peers (Scale B) and each ecoregion against the nation (Scale C) on the
  same weather-adjusted metric as `s04_relative.py`; the field assignment uses a 0.005 degree
  raster of ECO_ID under `analysis\ecoregions\`. Finding: the field-level classes agree with
  the cell design on 80.2 percent of fields, so ecoregion peers do not change the field map,
  and only Scale C and the plain weather-adjusted change can judge a whole region. Recommended
  design: keep the cell peers for the field term, add the cell-within-ecoregion term as the
  area term and Scale C per ecoregion and class as a region layer. Report:
  `pipeline/EXPLORE_ECOREGIONS.md`.
