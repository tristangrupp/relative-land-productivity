# Work log and decision record

This file is the running record of the project: what exists, what was decided and why, what
is open, and how to resume. It exists so that the work survives a context reset in the
orchestrating session. Every agent and every session that changes the project appends to the
log at the bottom, dated, before it ends. BRIEF.md stays the contract agents read first; this
file is the memory. Newest entries go last. Do not rewrite earlier entries; correct them with
a new entry.

## What the project is

A GitHub Pages map, https://tristangrupp.github.io/relative-land-productivity/, of per-field
productivity change in Brazil between the 2020 and 2024 agricultural years (1 September to
31 August), by crop type, with a suggested land use decision per field. Productivity is
relative greenness: the seasonal NDVI integral inside the CONAB crop calendar window,
weather-adjusted, against peers of the same crop. The purpose is to say, field by field and
region by region, which land use decision the evidence points to: restore, switch crop,
intensify, improve yields, abandon, keep.

Repo: https://github.com/tristangrupp/relative-land-productivity (Pages from main, `docs/`).
Local clone: `C:\Users\grupp\src\relative-land-productivity`.
Data root: `F:\relative-land-productivity-data` (fields, grid, weather, raw, extracted,
analysis, tiles). Never modify `E:\`.
Published artifacts: `https://wri-datalab-sandbox.s3.amazonaws.com/trazofields/trazo4/relative-land-productivity/`
with `tiles/fields.pmtiles` (6.36 GB, zoom 9 to 13), `tiles/summary.pmtiles` (39 MB, H3
cells, zoom 3 to 9), `tiles/stats.json`, and `fields/year=2024/state=<State>/fields_scored.parquet`
plus `fields/abandoned/state=<State>.parquet` (54 objects, 12.9 GB). AWS profile
`mfr-datalab` (SSO), S3 is storage only.

## Rules that hold

- No Earth Engine in any form, and never the project tkt-tristan. Planetary Computer COGs read
  locally instead. No AWS compute. Local compute only.
- Fields come from `E:\trazo4_master_parquet_seamfix` (read only). 2024 polygons are the map
  unit; the 2020 crop is the MapBiomas 2020 mode inside the 2024 polygon.
- Prose rules: no em or en dashes, no form of the verb "carry", American spelling, plain
  prose, numbers exact. Chat replies terse, deliverables normal prose.
- The user's preferences on the map, stated 13 Nov 2026: the default view is productivity
  change 2020 vs 2024; the national view must be dense (many small cells, not a few large
  ones); crop names must show on hover in every view; crop switched, newly cropped and
  abandoned draw at 50 percent opacity.

## Pipeline, in order

`pipeline/` scripts, Python `E:\Water\water intelligence\wci_tools\.venv\Scripts\python.exe`
(never bare `python`, it is a broken wrapper), tippecanoe in WSL Ubuntu-22.04.

| stage | script | output |
|---|---|---|
| fields | s01_prepare_fields.py | fields\year=\state=\fields.parquet (54 files) |
| grid | s02_grid.py | grid.json, tiles.parquet, field_tiles |
| weather | s03b_weather.py | weather\{chirps,tmax,tmin}\YYYY-MM.tif (360 files) |
| MODIS | s03c_modis_fetch.py, s03d_modis_weights.py, s03e_modis_reduce.py | extracted\modis\year=\state=\ndvi_16day.parquet (54) |
| MapBiomas classes | s03f_mapbiomas_fields.py | extracted\mapbiomas\year=\state=\classes.parquet (54) |
| Sentinel-2 | s03g_s2_fetch_reduce.py, s03h_s2_assemble.py | extracted\s2\tiles\<tile>.parquet, then year=\state=\ndvi_monthly.parquet |
| cross-year reduce | s04_xyear_reduce.py | analysis\modis_xyear (2020 composites on 2024 weights) |
| metrics | s04_metrics.py | analysis\metrics\source=\polys=\ay=\<State>.parquet |
| relative | s04_relative.py | analysis\relative\source=\polys=\ay=\<State>.parquet, weather_fit.json |
| change and decision | s04_change.py | analysis\year=2024\state=\fields_scored.parquet, analysis\abandoned |
| validation | s04_validate.py | data/summaries/validation.csv |
| tiles | s05_tiles.py | tiles\fields.pmtiles, summary.pmtiles, stats.json |
| upload | s05_upload.py | S3 (skips same-size objects, retries dropped connections) |
| runner | s04_run_all.py | analysis\run_all.log |
| ecoregions | s06_ecoregion_peers.py (in progress) | analysis\ecoregions, data/summaries/ecoregions*.csv |

Reports: pipeline/PROBE.md, EXTRACT.md, EXTRACT_S2.md, ANALYZE.md, EXPLORE_ECOREGIONS.md
(pending). Methods: methods/METHODS.md. Site contract: docs/DATA_CONTRACT.md.

## Current state, 13 November 2026, 08:30

- National MODIS release is live: 24,554,482 fields on 2024 outlines, 190.7 Mha, plus 748,022
  abandoned 2020 outlines. Change classes: stable 63.8 percent, crop switched 9.9, decline 7.2,
  gain 6.8, newly cropped 6.7, large decline 2.1, large gain 2.0, no data 1.5. Low confidence
  82.9 percent (field under one MODIS pixel or few clear composites).
- Validation against IBGE municipal yields is weak: raw integral Spearman 0.46 soybean 2020,
  0.48 sugarcane 2024, nothing for maize; prod and change below 0.24 everywhere. The map is
  relative greenness, not yield.
- Weather regression explains little: 134 of 176 class by state pairs fitted, median R
  squared 0.15.
- Pasture vigor is null everywhere (MapBiomas vigor needs the platform wizard, which the user
  has not approved submitting).
- Sentinel-2 extraction (pid 36992, tiers 1 and 2, detached) still running since 12 Nov 14:35;
  about 700 of 4,881 tile parquets by 06:30 on 13 Nov. When Mato Grosso assembles, rerun
  metrics with `--source s2` per state. The water downloaders in session grupp-32 stay paused
  until it ends.
- The ecoregion exploration agent is running (started 13 Nov about 07:15): RESOLVE 2017
  ecoregions as the peer reference, three scales (field vs cell, field vs ecoregion with the
  cell-vs-ecoregion term, ecoregion vs nation), report to pipeline/EXPLORE_ECOREGIONS.md.

## Open items

1. Decision revamp (agreed in principle 13 Nov, see the log): two-tier rules built on the
   ecoregion scores, area term plus field term. Blocked on the ecoregion agent's outputs.
2. "Change land use pattern" is a label on crop-switched fields, not advice; it goes away in
   the revamp (crop-switched fields get judged by their 2024 level: switch paid off or failed).
3. Pasture vigor: user to decide whether to submit the MapBiomas platform jobs.
4. Sentinel-2 refinement for Mato Grosso, then tier 1, then tier 2.
5. The user may want conversion of pasture to crop never suggested inside the Amazon biome
   (asked, not yet answered).

## How to resume after a context reset

1. Read this file, then BRIEF.md (Decisions section at the bottom), then pipeline/ANALYZE.md.
2. Check processes: `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 's03g|s04|s05|s06' }`.
   The Sentinel-2 run logs to `F:\relative-land-productivity-data\extracted\s2\progress.log`.
3. Check agents with ListAgents; a running subagent reports by SubagentHandback.
4. Site changes: edit `docs/`, test with `python serve.py` (port 8810, serves docs/), bump the
   `?v=` cache busters in docs/index.html, commit, push main, wait for Pages (about a minute),
   check in Chrome. Tiles: `s05_tiles.py summary` rebuilds the summary in about 2.5 minutes,
   `s05_upload.py --tiles --check` uploads and checks public read.
5. GitHub auth in Git Bash: `export GH_TOKEN=$(printf 'protocol=https\nhost=github.com\n' | git credential fill | sed -n 's/^password=//p')`.

## Log

### 2026-11-12

- Project started. Agents: methods, fields, probe, site in parallel; then extract; then
  analyze; then integrate. The user forbade the Earth Engine project tkt-tristan and then
  chose no Earth Engine at all; the probe was rebuilt on Planetary Computer COGs.
- Shared network link made national Sentinel-2 infeasible (0.37 tiles per minute), so the
  national release uses MODIS MOD13Q1 at 250 m and Sentinel-2 is a later refinement for
  tiers 1 and 2.
- Grid: the header of the S3 coverage GeoTIFF (EPSG:4326, 0.000269 degree pixels, 1024 pixel
  tiles, 8,007 tiles touch fields).
- MODIS fetch ended 22:08. Composite 2024225 has no Terra item on Planetary Computer; the
  assembler now treats a composite recorded in missing.json as NaN and interpolates
  (commit f5e9b86).
- Analyze ran nationally 22:35 to 23:59 (commit a46bf93); the upload failed once on a dropped
  connection and was resumed with skip and retry (8462fb3), finished 00:33 with 54 objects.

### 2026-11-13

- 00:08 Integrate: site on real tiles (d6c6f8c), confidence control, no_data and none
  classes, legend states SD thresholds, methods and about rewritten. Reporting pass filled
  ANALYZE.md (0849386). stats.json counts include the abandoned 2020 outlines in
  change_class.abandoned and decision.restore, so shares divide by n_fields of 2024 outlines.
- 07:00 User direction: make the frontiers of change visible at the national zoom; default
  view change 2020 vs 2024; crop names on hover from the MapBiomas mode codes, legend from
  the source.coop mapbiomas-brazil collection.
  Done (a9c6cf9, d9dc0ee, 6d05208): summary tiles at three H3 levels by zoom band (40 km at
  zoom 3, 15 km at 4 to 5, 6 km at 6 to 9); the change view colors a cell by share of fields
  declining minus share gaining (steps 5 and 15 points), balanced cells in a gray that shows
  on the basemap. A 100 km level and a faded balanced color were tried and rejected by the
  user as "way too huge" and "too sparse". Crop 2020 and 2024 named in every field tooltip.
- 07:15 User asked whether relative productivity works at ecoregion scale so that calls can
  be made about whole regions (restore the frontier). Ecoregion exploration agent launched
  with RESOLVE 2017 ecoregions; the answer in principle: any peer-relative score cancels the
  mean of its reference, so a region can only be judged against a larger reference
  (ecoregion against nation), and the cell-within-ecoregion term is the frontier signal.
- 07:40 User: "change land use pattern" is meaningless as a recommendation. It is in fact a
  label on the 2,424,420 crop-switched fields. To be removed in the revamp.
- 07:50 User set the direction for the decision revamp: three different stories must be
  told apart (decline with a crop switch, decline on the same crop, pasture low next to high
  crops, everything low and declining across an area means restore the area). Agreed design:
  ecoregion reference scores stay as the backbone, the immediate area (H3 cell) stays, and
  the decision blends them: the field-vs-ecoregion score splits into an area term (cell vs
  ecoregion, the land use tradeoff) and a field term (field vs cell, management). Area call
  first, field call second. Area labels: restore area, good land underused (crops high,
  pasture low: intensify or convert), system misfit (crops low, pasture fine), area fine.
  Field labels: improve yields, keep, switch paid off, switch failed, newly cropped and low
  (strongest restore case), abandoned. Implementation waits for the ecoregion agent's
  per-field and per-cell outputs.
- 08:30 This log created at the user's request so the work survives context compaction.
