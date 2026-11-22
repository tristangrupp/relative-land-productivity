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
with `tiles/fields.pmtiles` (6.40 GB, zoom 9 to 13), `tiles/summary.pmtiles` (92.4 MB, H3
resolution 6 cells, zoom 3 to 9), `tiles/stats.json`, and `fields/year=2024/state=<State>/fields_scored.parquet`
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
- Rules of 14 Nov 2026 (decisions round 2): area call per 6 km cell with 15 km fallback;
  low-confidence fields labeled "too small to judge yet" with the computed call kept; states
  switch to Sentinel-2 one by one through pipeline/s09_swap_state_to_s2.py, with a `source`
  attribute per field (Mato Grosso first); native vegetation near a field weighted by patch
  size, regrowth inside it giving assisted natural regeneration; each field shows one
  treatment plus other options, never a site plan; restore, assisted natural regeneration,
  restore candidate and recently converted land in one distinguishable green family; native,
  regrowth and CAR details in the field card only, not on the map, legend or tooltip.

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
| ecoregions | s06_ecoregion_peers.py | analysis\ecoregions, data/summaries/ecoregions*.csv |
| weather refit test | s07_weather_refit.py (not adopted) | analysis\weather_refit, data/summaries/weather_refit_compare.json |
| decisions v2 | s07_decisions.py national, area, fields, report, lookup (after s04_change and s06 score, before s05) | analysis\decisions, columns in fields_scored, data/summaries/decisions_v2*, docs/data/ecoregions.json |
| s2 comparison | s08_s2_compare.py all --state <State> (after s04_metrics and s04_relative --source s2 --no-summary-copy) | analysis\source=s2\, data/summaries/s2_mt_*.csv; never writes the live MODIS tables |

Reports: pipeline/PROBE.md, EXTRACT.md, EXTRACT_S2.md, ANALYZE.md, EXPLORE_ECOREGIONS.md,
DECISIONS_V2.md, S2_MATO_GROSSO.md. Methods: methods/METHODS.md. Site contract: docs/DATA_CONTRACT.md.

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
- The ecoregion exploration is done (commit a43f8c8, report pipeline/EXPLORE_ECOREGIONS.md):
  per-field Scale B tables under `analysis\ecoregions\fields\<State>.parquet`, the cell term
  in `data/summaries/cell_vs_ecoregion.csv`, the ecoregion-class Scale C rows in
  `data/summaries/ecoregions.csv`. Ecoregion peers agree with the cell design on 80.2 percent
  of fields; the regional call comes from Scale C and the plain change.
- Decisions version 2 (13 Nov, report pipeline/DECISIONS_V2.md, METHODS.md section 7): area
  call per H3 resolution 5 cell on the national reference (`cell_vs_nation`), field call
  inside it. Restore 91,076 fields in 52 restore areas; area declining 1,224,818 fields
  nationally and 338,554 (12.0 percent) in the seven Amazon frontier ecoregions, which get no
  restore. `decision_v1` keeps the old suggestion. The weather refit per ecoregion was tested
  and not adopted. The site has the national frontier change map (continuous ramp on 6 km
  cells), the Area decision view, the top-action decision summary, short legends with info
  tooltips, and calm intensify. Published 13 Nov: fields.pmtiles (6.40 GB, 1,422 s at 4.5
  MB/s), summary.pmtiles (92.4 MB), stats.json and the 54 GeoParquet files on S3, site at
  commit 8116abb and later on Pages, checked live.

## Current state, 14 November 2026, 04:45

- Sentinel-2 Mato Grosso analysis done (report pipeline/S2_MATO_GROSSO.md); nothing on the map
  changed. s2 metrics and relative tables for Mato Grosso are under `analysis\metrics\source=s2`
  and `analysis\relative\source=s2`; change classes, decisions and the comparison under
  `analysis\source=s2\`. Area call the same as MODIS on 93.3 percent of the state's 3,132
  resolution 5 cells; change class the same on 70.0 percent of comparable fields; decision the
  same on 58.7 percent; s2 calls 1.7 times as many fields declining or gaining as MODIS;
  682,147 of 684,199 MODIS low-confidence fields get an s2 change class. Validation against
  IBGE does not separate the sensors. Recommendation to the user: show both (s2 values as
  extra attributes on Mato Grosso fields), keep MODIS as the default and for the area calls,
  and test unthinned composites before any switch of the change view.
- The Sentinel-2 extraction (pid 36992) keeps running for the other tier 1 and tier 2 states.

## Current state, 14 November 2026, afternoon

- The user answered the seven decision questions and set the native vegetation and low
  confidence rules (Log, 14 Nov; METHODS.md 7.5; DECISIONS.md C7 to C16). The decisions round 2
  agent is implementing them: area call at H3 resolution 6 with resolution 5 fallback, restore
  in pasture-only area-declining cells, conversion to crops in the Amazon only for productive
  pasture, recently converted without a 2024 value as no data, the low confidence label,
  native vegetation share within 1 km and 250 m from MapBiomas 2024, and the Mato Grosso swap
  to Sentinel-2 with a per-field source attribute. Also patch-size weighting of nearby
  native vegetation, "Assisted natural regeneration" for fields with regrowth inside them,
  and a recommended treatment with alternatives per field (DECISIONS.md C17, C18, C20).
- A CAR agent computes per-field Forest Code deficit indicators (DECISIONS.md C19).
- Sentinel-2 extraction (pid 36992) runs at 41 tiles per hour (13:49); tiers 1 and 2 finish
  around 17 Nov. Tier 3 is not queued.
- MODIS agricultural years 2016 to 2019 and 2021 to 2023 download one file at a time (pid
  44620), about 100 GB, logs under `F:\relative-land-productivity-data\raw\modis\`.
- DECISIONS.md indexes every decision with who made it and its status.

## Current state, 14 November 2026, evening

- Decisions round 2 is built (commit e617096 and later; METHODS.md 7.6; DECISIONS.md C7 to C20,
  D12 to D14). Area call per 6 km cell with 15 km fallback; Mato Grosso on Sentinel-2 (change
  scale 1.2174); low-confidence fields show "too small to judge yet" (19,464,886 fields);
  native vegetation, patch size and regrowth split the fields below their neighbors into
  assisted natural regeneration, restore candidate and improve yields; each field shows one
  treatment plus options. `pipeline/s09_swap_state_to_s2.py --state <State>` switches the
  next state (AGENTS.md). Publication status: see the last log entry.
- Sentinel-2 extraction (pid 36992) and the MODIS long-series download (pid 44620) keep
  running and fill the network link: uploads ran at about 1 MB/s on 14 Nov afternoon.

## Open items

1. Swap each further state to Sentinel-2 with `pipeline/s09_swap_state_to_s2.py --state
   <State>` in run order (Pará next) as its extraction completes; each run rebuilds the field
   tiles (about 50 minutes) and uploads them. The GeoParquet upload of decisions round 2 may
   still be pending (last log entry).
2. Longer productivity time series: MODIS 2016 to 2019 and 2021 to 2023 downloading; then
   extract, reduce and use it in the improve yields or restore choice (METHODS.md 7.5 item 7).
3. Sentinel-2 timing: tell the user if the extraction approaches three weeks. A Sentinel-2
   record as long as the MODIS one (8 agricultural years) would take about 4 to 5 weeks for
   all of Brazil; the user has not decided. Whether to queue tier 3 (3,126 tiles, about 3
   more days) is also open.
4. Pasture vigor: user to decide whether to submit the MapBiomas platform jobs.
5. Closed: conversion to crops inside the Amazon was answered 14 Nov (DECISIONS.md C9) and is implemented.
6. Sentinel-2 composites from every clear day instead of the three least cloudy: test not
   run. It may explain why the s2 peer score is less persistent between years than MODIS
   (0.25 against 0.40 over 100 ha).
7. A slimmer resolution 7 summary layer could fit the 150 MB budget if the user wants it.
8. Answered: the user said on 14 Nov "We can just publish this to the github pages map, I
   don't care", so CAR-derived indicators for MT, MA, TO and GO are not held local.
9. Regrowth confirmation with MapBiomas 2023: fetch `mapbiomas_brazil_2023.tif` (1.18 GB,
   source.coop) into `raw\mapbiomas\` when the link allows, then rerun `s07_decisions.py
   native` (about 30 minutes) and the decisions and tiles.
10. (20 November 2026) Possible mis-detection is in the decision tables but not in the published
   tiles until the next tile build (the Maranhão swap). The thresholds (99th percentile, 50 ha,
   25 percent native inside) are agent choices awaiting the user's review (DECISIONS.md C22).

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
- 09:00 User: the zoomed-out map is still too coarse and sparse. Summary levels now H3
  resolution 5 (15 km) at zooms 3 to 4 and resolution 6 (6 km) at zooms 5 to 9; colored
  cells at full opacity, balanced cells 0.85. The 40 km and 100 km levels are rejected.
- 09:05 User asked why so much of the 2020 crop view is forest. Answer recorded: every view
  draws the 2024 outlines, and crop 2020 is the MapBiomas 2020 class inside them, so fields
  cleared after 2020 show forest or savanna (forest formation 2.7 percent, savanna formation
  3.0 percent of fields). The summary cell shows the modal 2020 class, so frontier cells read
  forest (1,427 of 23,878 resolution 5 cells). Proposed, not yet approved: summary cell shows
  the most common agricultural 2020 class plus a "share newly cropped since 2020" view.
- 09:10 User asked why the Amazon conversion frontier is mostly "no suggestion". Answer
  recorded: decision "none" is newly cropped plus no data. Pará 33.0 percent (12.3 newly
  cropped, 20.7 no data from wet-season cloud), Amazonas 32.7, Roraima 21.7, Maranhão 20.9,
  Acre 18.0, Mato Grosso 6.1.
- 09:15 Decision (user): newly cropped fields get their own suggestion category, "Recently
  converted land", in a green near but distinct from restore (restore #008300, recently
  converted #7cc24e). "No suggestion" now means no data only. Implemented in the site without
  a tile rebuild: config.js DECISIONS has the class with derivedFrom change_class ==
  newly_cropped; app.js draws it ahead of the decision match, names it in tooltip and card,
  and takes its legend count from change_class.newly_cropped, subtracting it from "none".
  The summary cells' dominant_decision still says "none" where newly cropped fields are the
  mode; fix when the summary is next rebuilt with the decision revamp. In the revamp,
  recently converted fields are split by their 2024 level against ecoregion peers.
- 09:25 User asked for an AGENTS.md with standing context and to keep documenting as we
  work. AGENTS.md at the repo root now holds the read order, the documentation duty (every
  user decision into this log in the same commit, method changes into METHODS.md, tile and
  site changes into DATA_CONTRACT.md and README.md), hard rules, writing rules, environment,
  published data, site workflow, the user's standing map preferences and the caveats.
  The "newly cropped" row of the METHODS.md decision table now reads "recently converted
  land" (5b5f7de).
- 07:15 to 08:00 Ecoregion exploration agent (s06_ecoregion_peers.py, report
  pipeline/EXPLORE_ECOREGIONS.md). Built: RESOLVE 2017 ecoregions downloaded to
  `raw\ecoregions\`, rasterized at 0.005 degree, every 2024 polygon assigned by centroid
  (24,553,822 direct, 657 filled from the nearest ecoregion, 3 unassigned); Scale B (field vs
  ecoregion-class peers) and its cell-within-ecoregion term; Scale C (ecoregion-class vs
  nation) and the plain weather-adjusted percent change; per-field tables
  `analysis\ecoregions\fields\<State>.parquet` (fid, eco_id, peer_cls_2020, peer_cls_2024,
  r_eco_2020, r_eco_2024, d_eco, cell_vs_eco_2020, cell_vs_eco_2024, eco_change_class,
  change_class_a), `data/summaries/ecoregions.csv`, `ecoregions_by_biome.csv`,
  `cell_vs_ecoregion.csv` (55,225 cell by ecoregion by class rows), five figures under
  docs/figures/ecoregions/. Headline numbers: 46 ecoregions and 20,113,253 fields with a
  Scale B change; Scale A and B classes agree exactly on 80.2 percent of 20,109,313 fields and
  in direction on 83.1 percent, opposite sign on 0.07 percent; national pasture -2.3 percent;
  Tapajós-Xingu pasture -9.7 percent and -0.35 national cell SD, Purus-Madeira -6.9,
  Southwest Amazon -5.9, Xingu-Tocantins-Araguaia -4.7, Madeira-Tapajós -2.1, Mato Grosso
  tropical dry forests -0.1, Cerrado pasture -1.0, Caatinga pasture -2.4. Answer: ecoregion
  peers do not change the field map and cannot judge a region either (the ecoregion mean is
  subtracted); the regional call comes from Scale C and the plain change, the area call from
  the cell-within-ecoregion term. Recommended: keep Scale A as the field term, add
  cell_vs_eco as the area term and Scale C per ecoregion and class as a region layer. Open:
  the weather fit should be refitted per ecoregion and class with the cell's mean
  precipitation as a regressor before the area term is acted on (its 2024 change forms
  weather-shaped blocks in the Caatinga); the decision revamp can start from the per-field and
  per-cell tables above. Run times: assign 18 s, score 124 to 148 s, figures 4 s.

- 10:00 to 12:00 Decision revamp agent (version 2 of the decisions; report
  pipeline/DECISIONS_V2.md; METHODS.md section 7 rewritten with the version 1 table kept
  under a dated superseded heading).
  Step 1, weather refit: `s07_weather_refit.py` fitted layer 2 per ecoregion and peer class
  with the field location's mean annual CHIRPS precipitation (2016 to 2024) as an extra
  regressor, same guards as s04_relative. Median R squared rose from 0.150 (134 state-class
  pairs) to 0.188 (146 ecoregion-class pairs), but the blocks in the 2024 change of the area
  term did not shrink (Moran's I 0.616 to 0.626; ring 8 neighbor correlation 0.23 to 0.35),
  so the existing state-class fit stays and nothing downstream was recomputed on the refit.
  Step 2 first build: area call per H3 resolution 5 cell against the ecoregion
  (cell_vs_eco), thresholds 0.5 and 0.3 ecoregion SD; superseded the same morning, see below.
- User direction, relayed by the coordinator: "lets do brazil as a whole then to get the
  true frontiers of productivity change". Done: `s07_decisions.py national` computes
  cell_vs_nation per H3 cell and class (cell median minus national class median, in 1.4826
  MAD of the national distribution of cell medians) for 2020 and 2024 at resolutions 5 and 6,
  and the plain percent change per cell and class (`data/summaries/cell_vs_nation.csv.gz`).
  The area call now uses it (below under -0.75, declining under -0.4 national SD; justified
  in METHODS.md 7.1); the ecoregion terms and Scale C stay as secondary context in the
  tooltip and cell card (user: keep the ecoregion scores). The zoomed-out change map is now
  the national frontier map: cells colored by the class-weighted cell_vs_nation change; the
  net share of declining minus gaining fields moved to the tooltip with the plain percent
  change. National SD change was chosen over the plain percent change because it removes
  each class's nationwide shift (pasture -2.3 percent, much of it the 2024 drought) and puts
  classes on one unit. Results: 52 restore-area cells (93,244 fields), good land underused
  1,675 (3,096,673), system misfit 356 (883,479), area declining 1,189 (1,224,818), area fine
  16,993 (19,072,057), no call 272 (184,211). Field calls: restore 91,076; recently converted
  below 418,860 and at or above 1,226,786; improve or convert pasture 633,043; switch paid off
  1,669,629; switch failed 671,801; improve yields 6,715,891; intensify 6,722,391; keep
  5,879,276; abandon 133,960; no data 391,769; abandoned since 2020 748,022. 97.2 percent of
  version 1 restore fields became improve yields. Amazon frontier (7 ecoregions, 2,814,635
  fields): no restore, 338,554 in area-declining cells.
- User feedback on the site, relayed by the coordinator: "put the explanatory text into a
  hoverable tooltip that appears on hover. make it clear there is text to read for the user,
  but this currently is way too long for a legend. also the main map is still too coarse and
  oversimplified! on the recommendations zoom out, the whole thing is orange!" Done: legend
  rows show swatch, label and count; a circled "i" beside the label opens the note on hover,
  keyboard focus or tap (every view). Summary cells are H3 resolution 6 (about 6 km) at every
  zoom from 3; resolution 7 at zooms 7 to 9 was built and measured 173.0 MB (214.7 MB joined),
  over the 150 MB budget, so it is not used (summary.pmtiles 92.2 MB). The change view uses a
  continuous diverging ramp (-1.0 to +1.0 national SD, gray at zero) with a gradient legend.
  The decision summary colors a cell by its top action: the actionable decision (not keep,
  intensify, no data) most over-represented against its national share, among those with at
  least 15 percent of the cell's fields and 1.5 times their national share; else gray "no
  action stands out". The plain most-common-action rule was measured first and would have
  colored 100,538 of 144,909 cells improve yields (27 percent of all fields); with the lift
  68,556 cells take a color across seven actions. Intensify is khaki #c4b38f instead of
  orange. Tooltips list each cell's top three decisions. Legend counts come from the rebuilt
  stats.json (decision, decision_v1, area_decision keys).
- User feedback, relayed by the coordinator: "i am seeing the latest update on the page, it
  looks very good. styling, clarity, relative differences across the country. this is in the
  right direction". Confirmed direction: the national reference, the finer 6 km cells, the
  continuous frontier ramp, the styling and the short legends with info tooltips. Keep that
  look. At the time of this remark the changes were on the local server
  (http://127.0.0.1:8810) with local summary tiles; nothing had been pushed yet.
- User feedback, relayed by the coordinator: "area decision as it currently looks on the page
  is too coarse and not as nice as the suggested decision." Done: the Area decision view now
  draws the 6 km summary cells by the same rule as the decision view (the most common area
  call other than area fine and no call, when it covers at least 15 percent of the cell's
  fields, else the background gray), with the same legend style and info tooltips; area fine
  takes the same gray as "no action stands out", and the area colors match the decision
  palette (restore green, good land underused teal like improve or convert pasture, system
  misfit violet like switch failed). The area call is still made per 15 km (H3 resolution 5)
  cell; every 6 km cell and every field inherits its parent's call, and at field zoom the
  fields draw their area call. Making the call itself at 6 km would need a method change and
  a field tile rebuild; offered to the user, not done.
- Publication of version 2. Field tiles rebuilt with `decision`, `area_decision` and `eco_id`
  (s05_tiles.py fields, 3,228 s; tile-join 436 s; fields.pmtiles 6,398,827,894 bytes) and
  uploaded in 1,422 s; summary.pmtiles (92,404,490 bytes) and stats.json uploaded; all three
  answer range requests with 206. The 54 GeoParquet files were uploaded; the first pass
  failed on Amapá after four dropped connections and a rerun completed (the second rerun
  skipped all 54 as same size). Site pushed as 8116abb; Pages built it. Checked live in
  Chrome: zoom 4 change view shows the continuous frontier ramp on 6 km cells with the
  gradient legend; zoom 4 decision view shows the top-action colors (amber, greens, blues,
  teal) with the gray background, not one color; zoom 4 area view shows teal, violet and
  orange areas on gray; at zoom 11 near Sorriso the 3,352 rendered fields have the new
  decision values, area_decision and eco_id, the field card shows the area call and the
  ecoregion line, and the legend counts are the version 2 ones (restore 91,076). Console:
  only errors from a browser extension.

### 2026-11-14

- 04:35 to 04:45 Sentinel-2 Mato Grosso agent (report pipeline/S2_MATO_GROSSO.md). Inputs
  checked: s2 2024 layer 1,151,506 fields, 2020 layer 978,055, both 1,011 of 1,013 tiles
  complete; 4,567 fields of the 2024 layer have no valid 2024 month. `s04_metrics.py` now takes
  area_ha and mbmode from the prepared fields when the NDVI table lacks them (the s2 tables
  hold fid and the series only). Metrics and relative ran for Mato Grosso on s2 (polys 2024
  for both years, polys 2020 for 2020) with `--no-summary-copy`, so the live weather_fit.csv
  is unchanged. Weather fit refitted on s2 (the code refits for polys 2024, and the fit is in
  the sensor's units); median R squared 0.054 against 0.074 for MODIS Mato Grosso; the MODIS
  fit applied instead changes the change class of 0.35 percent of fields. Border: with Mato
  Grosso alone, 112 fields lose their peer group, 1,145 move to a coarser H3 level and 26,103
  keep their group with fewer peers (27,360, 2.4 percent). New stage `s08_s2_compare.py`
  reproduces s04_change and s07_decisions in memory and writes under `analysis\source=s2\`,
  because those two scripts write fields_scored.parquet at a path with no source and would
  overwrite the live tables. Area tier: s2 calibrated to the MODIS national reference per
  class and year on fields over 25 ha with high MODIS confidence (median and robust SD
  matched; Pearson from 0.58 for soybean 2020 to 0.96 for forest plantation 2024). This was
  chosen over a within-state reference, which called 24 restore areas and 313 area-declining
  cells against MODIS's 0 and 40 and agreed on 80.9 percent of cells instead of 93.3.
  Comparison: change class exact on 70.0 percent of 1,021,906 comparable fields, same
  direction on 73.6, opposite on 0.46; 2024 integral correlation 0.67 (under 6.25 ha) to 0.87
  (25 to 100 ha); decisions 58.7 percent; area call per field 94.7 percent. The robust SD of
  the s2 change is 0.97 against 0.68 for MODIS, and the 2020 to 2024 correlation of the peer
  score is lower on s2 in every size band (0.25 against 0.40 over 100 ha); cause not
  determined. IBGE validation on the same municipalities: soybean and maize Spearman between
  -0.24 and +0.17 on both sensors. Recommendation: show both, MODIS default, no switch of the
  change view yet. No tiles, site or upload touched.

- Recorded 14 Nov by the documentation agent, for decisions of 12 Nov that were only in
  BRIEF.md or METHODS.md: NDVI comes from Planetary Computer Sentinel-2 COGs read locally,
  the way the agriculture-and-drought repo did it (user). S3 is storage only, through the
  profile `mfr-datalab` (user). The Sentinel-2 refinement runs tier 1 (MT, PA, AM, AC, RO,
  RR, AP) then tier 2 (MS, GO, TO, MA); the MODIS national release was the orchestrator's
  call and the user accepted it. Method: peers are the same MapBiomas class in the same H3
  resolution 5 cell, at least 30 fields, fallback to resolution 4 then 3; the weather layer
  is a regression per class by state on CHIRPS and TerraClimate anomalies with a nine-year
  baseline, agricultural years 2016 to 2024 (METHODS.md first wrote ten years, 2015 to
  2024); change classes are at plus or minus 1 and 2 peer SD. Every decision is now indexed
  in DECISIONS.md.
- User answers to the seven questions of the decision review (relayed by the
  coordinator):
  1. Declining fields in area-declining cells with pasture only become restore: yes.
  2. The user asked why "improve yields" replaced "switch crop" for fields below their
     same-crop neighbors. Answer given: same crop, same weather and similar land within 17
     km, so a persistent gap points to management, which a crop switch does not fix. A
     crop-to-land mismatch is the area tier's system misfit.
  3. The zoomed-out cell coloring rule (at least 15 percent of the cell's fields and 1.5
     times the national share): approved.
  4. "if they're productive at the frontier, convert to cropland maybe": inside the Amazon
     biome, pasture on good cropland gets "conversion to crops possible" only when the
     pasture itself is at or above its peers, and the note says already-cleared pasture, not
     new clearing. Otherwise the suggestion is improve pasture.
  5. "area map looks too homogenous": the area call moves to H3 resolution 6 (about 6 km)
     with resolution 5 fallback.
  6. Recently converted fields without a 2024 value move to no data: yes.
  7. "slowly work through state by state updating modis to sentinel": Mato Grosso switches to
     Sentinel-2 now with a per-field source attribute, then each state in run order as its
     extraction completes, through a swap script. This replaces the s2 Mato Grosso agent's
     recommendation (show both, MODIS default).
  Then the user said a field below its neighbors and declining could need improve yields or
  restore, and which one depends on a longer productivity time series and on how much native
  vegetation is nearby. Decided: a low-confidence MODIS field (small, likely mixing its
  neighbors' values) is labeled "Low confidence: too small to judge yet" until Sentinel-2
  arrives for its state; a below-neighbors field not near native vegetation gets improve
  yields (it spares land elsewhere); one next to remnant native vegetation is a restore
  candidate. Native vegetation share within 1 km and 250 m from MapBiomas 2024; the user on
  that source: "sounds like a decent candidate option". Implementation by the decisions
  round 2 agent.
- Longer productivity time series (user decision): MODIS agricultural years 2016 to 2019 and
  2021 to 2023 (2020 and 2024 exist) download now at reduced speed, one file at a time, so
  the Sentinel-2 extraction keeps priority. The user: "lean towards the first option at
  reduce download speed and prioritize the Sentinel 2 update but if the Sentinel 2
  extraction is gonna take like three weeks to do you should let me know and I can
  evaluate". Detached process pid 44620, `s03c_modis_fetch.py --years 2016 2017 2018 2019
  2021 2022 2023 --in-flight 1`, logs `F:\relative-land-productivity-data\raw\modis\fetch_long_stdout.log`
  and `fetch.log`. About 100 GB; F: had 476 GB free.
- Sentinel-2 timeline, measured 13:49: 41 tiles per hour. Tiers 1 and 2 (4,881 tiles) finish
  around 17 Nov. Tier 3 (3,126 tiles, not yet queued) would add about 3 days. A Sentinel-2
  record as long as the MODIS one (8 agricultural years instead of 2) would take roughly 4
  times as long, about 4 to 5 weeks for all of Brazil at this rate. Open question for the
  user.
- DECISIONS.md added at the repo root (commit b50335e): one row per decision, grouped as data
  and compute rules, method, decision rules, map and site design, and open questions, with
  date, who decided, reason, commit and status. Linked from AGENTS.md and README.md.
- Two more user decisions, implemented by the decisions round 2 agent. (1) Native vegetation
  near a field is weighted by patch size, so large patches count more than slivers ("make
  the larger patch more important than the small sliver vegetation"). (2) Secondary
  vegetation and regrowth enter the rules: a declining or below-peer field with native
  vegetation already returning inside it gets "Assisted natural regeneration" instead of
  active restoration ("if there is natural regeneration within a declining productivity
  field that could actually be assisted natural regeneration rather than active
  restoration"). Regrowth is derived from the MapBiomas annual maps 2019 to 2024 (an
  anthropic class earlier, native in 2023 and 2024), unless a public MapBiomas secondary
  vegetation product readable without Earth Engine is found. Recommended by the
  orchestrator, not yet decided by the user: use the CAR parcels (legal reserve and
  riverside protection deficits under the Forest Code) to strengthen restore candidates.
  DECISIONS.md C17, C18 and E7; METHODS.md 7.5 items 9 and 10.
- User approved the CAR parcel recommendation: "I think your recommendation with the car
  parcel data is a good one. Again like please document this really well and the decisions
  behind doing it". What it does: a restore candidate inside a property with a Forest Code
  legal reserve deficit (art. 12 of Law 12.651/2012: 80 percent of the property in forest,
  35 percent in Cerrado inside the Legal Amazon, 20 percent elsewhere) or a riverside
  protection deficit is a stronger restore case. Why: the owner already has a legal duty to
  restore on that property, so restoration there is more likely to happen and to find
  funding. The indicator is screening, not a legal finding, because CAR is self-declared.
  A CAR agent computes per-field indicators now. The property code `cod_imovel` is never
  published. CAR-derived indicators for MT, MA, TO and GO stay local until the user says
  whether the Restoration Explorer local-only rule applies here (open question).
- User: "I don't want to have a restoration plan done for the particular field site, just a
  recommendation for the field treatment: what should be done, what options are." Each
  field shows a recommended treatment plus alternative options, never a site plan. In force.
  DECISIONS.md C19, C20, E8; METHODS.md 7.5 items 11 and 12.
- Decisions round 2 agent, 14 Nov afternoon. Answers recorded here, numbers in the next entry.
  Question 2, the user asked why "improve yields" replaced "switch crop" for fields below
  their same-crop neighbors and stable. Answer given by the orchestrator, no change: a field
  compared with the same crop within about 17 km (the H3 resolution 5 peer cell), under the
  same weather, that stays behind points first to management (inputs, sowing date, variety,
  field condition), which a crop switch does not fix. A crop or system mismatch shows when
  the whole area's crop lags the national median, which is the area tier's "system misfit"
  call. Caveat: soils vary within a cell, and MODIS mixes small fields with their neighbors.
  Question 3, the user on the 15 percent plus 1.5 times national share rule for coloring the
  zoomed-out decision cells: "great". Kept as it is.
  Coordinator direction on colors: "Assisted Natural Regeneration should look different than
  restoration on the map because those are 2 different recommendations but they still
  should have some color similarity." Restore #008300, assisted natural regeneration
  #2e9e82, restore candidate #285c23, recently converted below peers #7cc24e, at or above
  #d7f28c: adjacent pairs of this green family separate by deltaE 12.1 or more under
  simulated protan, deutan and tritan vision (Machado 2009 matrices, CIEDE2000), found by a
  search around the suggested hexes. #2a9d8f and a mid green for the candidate failed the
  check under tritan vision (6.4), so the candidate is a dark forest green. Low confidence
  takes #cfd8e3, a cool light gray 11 deltaE from no data and from keep.
  User direction on CAR and on the map: "please don't make the legend or the map
  visualization super extra complicated ... I really don't want to see it on the main map
  layers for the main land use recommendations". Native vegetation, patch size and regrowth
  shares are in the field card details only; the legend keeps one swatch per recommendation.
  The treatment-with-options direction is implemented as `options` per class in config.js,
  listed in the field card under the recommended treatment.
- Decisions round 2, numbers (14 Nov, 13:40 to 15:30). Item 1, pasture-only restore: in an
  area-declining cell where pasture is the only use (crops absent, crop fields under 5 percent
  of the cell), a declining same-crop field is restore. 88,873 fields computed nationally,
  33,497 on the seven Amazon frontier ecoregions (0 before); after the low-confidence rule
  14,508 and 2,173 are shown. Item 4, Amazon biome (IBGE Biomas 1:250,000, downloaded to
  `raw\biomes\`): convert_cropland 5,556 computed (1,912 shown), improve_pasture
  3,035 (975); convert_pasture outside the Amazon 316,951 (50,599). Item 5, area
  call at 6 km: 100,122 of 144,909 resolution 6 cells make their own call (23,260,773
  fields), 44,787 take the 15 km parent's (1,293,709 fields); cells: restore the area
  184, good land underused 5,540, system misfit 1,712, area declining 9,301,
  area fine 118,675, no call 9,497. The categorical area colors on 6 km cells
  show real variation at zoom 4 (checked locally), so the continuous area score was added to
  the summary tiles (`area_score`) but not drawn. Item 6: 30,023 recently converted fields
  with no 2024 value moved to no data. Item 7: Mato Grosso is on Sentinel-2 (see the next
  entry). Low confidence ("too small to judge yet"): 19,464,886 fields, per state MG 3,348,634, BA 2,038,481, RS 2,033,570, PR 1,549,023, SP 1,374,435, SC 1,307,926, PA 895,663, PE 787,800, GO 780,769, CE 647,556, ES 552,145, RO 523,616, MA 490,577, PB 476,673, PI 474,802, TO 319,133, RN 290,285, AL 275,159, MS 257,557, RJ 224,053, MT 223,502, SE 209,557, AC 157,389, AM 139,517, RR 56,267, DF 29,305, AP 1,492.
  Native vegetation: large patch 50 ha (removes 20.2 percent of native pixels in the 1 km
  bands); restore candidate at 30 percent of the 1 km band in large patches (the 75th
  percentile, 0.300, of fields below peers and not gaining with high confidence); assisted
  natural regeneration at regrowth on 10 percent of the field (99th percentile of all fields
  0.114). Computed and shown: assisted natural regeneration 10,756 / 1,787, restore
  candidate 1,564,599 / 296,148, improve yields spares land 4,150,191 / 874,731, restore
  145,940 / 27,981; frontier 479 / 104, 144,774 / 44,406, 490,577 / 124,232, 33,497 / 2,173.
  Regrowth uses MapBiomas 2020 and 2024 only: the 2023 map download was corrupted by two
  curl runs writing into one file, and a retry measured 60 KB/s on the shared link, so 2023
  was dropped (METHODS.md section 9); the code uses it automatically once on disk. No public
  MapBiomas secondary vegetation GeoTIFF readable without Earth Engine was found.
- Mato Grosso switched to Sentinel-2 (user: "slowly work through state by state updating
  modis to sentinel"). Choice: normalize, not label only. k = 1.2174, the ratio of the robust
  SD of D on s2 (0.910) to MODIS (0.748) on 202,887 fields over 25 ha, high confidence on
  both sensors, same peer class in both years. Changing share on those fields 22.5 percent s2
  scaled, 22.8 MODIS, 30.0 s2 unscaled; on all 1,021,906 comparable fields 23.2, 17.0, 31.1;
  exact class agreement 76.1 percent scaled against 70.0 unscaled. The leftover gap is on
  small fields, where MODIS reads shared pixels (MODIS changing share 14.4 percent under
  6.25 ha and 28.9 over 100 ha; s2 scaled 24.2 and 25.9). The change view caveat says Mato
  Grosso uses Sentinel-2 and states the scale; every field has `source` (tooltip and card).
  Mato Grosso low confidence falls from 684,199 (MODIS) to 228,320 (s2). The swap runner is
  `pipeline/s09_swap_state_to_s2.py --state <State>` (AGENTS.md, "Switching a state to
  Sentinel-2"); its first run (assemble 177 s, metrics 71 s, relative 11 s, compare 45 s,
  swap 39 s) produced the live Mato Grosso tables; the MODIS tables are kept under
  `analysis\source=modis\`.
- 16 Nov, user: "Cut this from the readme: 'No Google Earth Engine is used anywhere. Every
  raster is downloaded or streamed and reduced to fields on one machine.'" Removed from
  README.md. The no-Earth-Engine rule itself stays in AGENTS.md.
- 16 Nov, user asked that pipeline jobs run with hidden windows. Long runs of this project go
  through `pipeline/launch_detached.py` (no console) started by WMI; the visible windows of
  16 Nov 14:26 came from two `s10_car_forest_code.py parcels` runs of the CAR agent.
- 14 to 16 Nov, CAR agent (Forest Code legal reserve per field; DECISIONS.md A11, A12, B17,
  B18, C21, E8; METHODS.md 7.5 items 13 to 15 and proposed section 7.7; report
  pipeline/CAR_FOREST_CODE.md; script pipeline/s10_car_forest_code.py). The user's words:
  "I think your recommendation with the car parcel data is a good one. Again like please
  document this really well and the decisions behind doing it, and I don't want to have a
  restoration plan done for the particular field site, just a recommendation for the field
  treatment: what should be done, what options are." Then: "I don't want the forest code
  policy and the CAR data to be super obviously incorporated onto the map ... but do let it
  inform how the restoration is recommended so it's grounded in Brazilian policy ... please
  don't make the legend or the map visualization super extra complicated. If you really want
  to do that we could make a separate toggle to view a different map and show that nuance".
  The preferred CAR dataset is the source.coop cadastral catalog (brazil-car-area-imovel,
  8,453,552 polygons, SICAR snapshot of 16 July 2026), downloaded to
  `F:\relative-land-productivity-data\raw\car\` and checked against its sha256. On
  publication: "We can just publish this to the github pages map, I don't care", so nothing
  is held from publication except `cod_imovel`, which never leaves `analysis\car\`.
  Why CAR and the legal reserve: a below-peer field near native vegetation could be restored
  or farmed better; if its property owes legal reserve under art. 12 of Law 12.651/2012, the
  owner has a legal duty to add native vegetation there, so restoration is more likely to
  happen and be funded. Simplifications: requirement by the IBGE biome under the property's
  interior point and the IBGE Legal Amazon limit (0.80, 0.35, 0.20); native share from
  MapBiomas 2024 on a 90 m grid of 3 by 3 blocks; no art. 67 small-property exemption,
  consolidation, compensation or state zoning (flagged, not modeled); riverside protection
  (APP) not done because no fine national stream map is usable locally. The proposal in
  METHODS.md 7.7 changes only which treatment a field gets (improve_spare to
  restore_candidate when the property over 4 fiscal modules has a deficit of 5 points or
  more and large native patches cover at least 15 percent within 1 km) and the order of the
  options; no class, color, legend row or tooltip row.
  Status at 16 Nov 14:50, stopped at the orchestrator's request: parcel indicators are
  written for 16 of 27 states under `analysis\car\parcels\` (AC AL AP BA DF MG MT PA PB PE
  RJ RO RR RS SE SP); Mato Grosso took 113 s once repeated vertices were removed
  (exactextract 0.3 hung on them). Remaining: the parcels step for CE ES GO MA MS PI PR RN
  SC TO AM, then `fields` for all 27 field states, then `summary`, then the numbers in
  CAR_FOREST_CODE.md. Before resuming, bound memory: a fields test on Mato Grosso and two
  parcel workers filled the machine on 16 Nov (one process at 92 GB virtual) and killed the
  round 2 tile join twice. The fields step now joins in longitude strips of 400,000 fields,
  but it was not seen finishing; check peak memory on one state and keep it under 8 GB, one
  worker at a time, launched only through `pipeline/launch_detached.py` via WMI.
- 16 Nov 15:05, the E: windows the user kept seeing came from the Sentinel-2 extraction:
  `s03g_s2_fetch_reduce.py` (pid 12272) starts `s03g_weights.py build <tile>` with the E:
  venv Python for every new tile, each in its own console window. Fixed in the code
  (`creationflags=CREATE_NO_WINDOW`); the running extraction keeps the old code until it is
  restarted, so the windows continue until then. The CAR jobs had also shown windows.
- 16 Nov, user directions on how agents work: "prioritize things that can be pushed ASAP and
  commited and made live on the github pages"; "i dont want my machine permanently occupied
  by this session"; "make sure agents commit and save work before autocompact and record
  things to be done"; "make sure the methodology md on the github stays up to date as things
  progress"; "keep going since we've already done 16/27 states" (the CAR parcels). Added to
  AGENTS.md.
- 16 Nov 15:10, publication of decisions round 2: summary.pmtiles (103,301,045 bytes) and
  stats.json uploaded and answer range requests with 206; the site pushed with them, so the
  zoomed-out views and legend counts are the new ones. fields.pmtiles (7,047,407,349 bytes,
  joined in WSL on 16 Nov after two joins were killed when the CAR job filled memory) is
  uploading in a hidden process; until it lands, field zoom shows the 13 Nov field tiles.
  GeoParquet upload (13 GB) still to do.
- 16 Nov, CAR agent, run completed after the user said "keep going since we've already done
  16/27 states". Parcels for the other 11 states, then fields for all 27 states, then the
  summary (`data/summaries/car_forest_code_by_state.csv`, no property codes; report
  pipeline/CAR_FOREST_CODE.md, section "Numbers"). One worker at a time, launched through
  `pipeline/launch_detached.py` via WMI with no window. Memory: the fields step now works in
  longitude zones of 800,000 fields with the zone's parcels loaded from disk, keeps
  geometries as Arrow binary, skips the intersection when a field lies inside its parcel,
  logs resident and peak memory on every line and stops above 10 GB; peak 8.75 GB on Minas
  Gerais, at most 6.95 GB elsewhere (parcels 2.98 GB).
  Numbers, Brazil, 24,554,482 fields: 86.1 percent in an active or pending CAR parcel, 1.3
  percent only in a canceled or suspended one, 12.7 percent in none; 16.9 percent have 2 or
  more registered parcels overlapping; 47.1 percent of all fields (54.7 percent of fields in
  a registered parcel) sit in a property with less native vegetation than the legal reserve
  screen requires, 14.8 percent in such a property over 4 fiscal modules. The 2,655,897
  deficit properties touched by fields owe 54.0 Mha by the screen, 26.8 Mha of it in
  properties over 4 fiscal modules. Amazon frontier (7 ecoregions, 2,814,635 fields): 85.7
  percent in a registered parcel, 29.4 percent with overlapping parcels, 79.8 percent of
  fields (93.1 percent of registered ones) in a deficit property, 28.4 percent in one over 4
  fiscal modules; 35.3 Mha of deficit, 65 percent of the national figure from 11.5 percent
  of the fields. Amapá against the earlier GeoPackage test: 83.2 against 79.8 percent in a
  registered parcel, 51.5 against 48.4 percent in a deficit property, 67,595 against 66,853
  ha of deficit. The test folders `analysis\car_test\` and `analysis\car\test\` are deleted.
  The Forest Code subsection is back in docs/methods.html (marked in preparation); nothing
  else in docs/ changed. Next for the orchestrator: apply METHODS.md 7.7 in
  `s07_decisions.py` and the option lists in config.js.

### 17 November 2026, 02:32

- The Pará, Rondônia and Acre swap chain launched at 01:31 through `cmd.exe /c "a && b"` failed at once with "'E:\Water\water' is not recognized". The venv Python path has a space, and the unquoted path broke the cmd.exe line. Nothing ran.
- Added `pipeline/run_chain.py`, which runs each script argument in turn with the same interpreter and stops at the first failure. Relaunched the chain at 02:31 with WMI, `launch_detached.py` and `run_chain.py`; Pará assemble started. Log: `F:\relative-land-productivity-data\analysis\source=s2\logs\swap_PA_RO_AC_2026-11-17.log`.
- Use `run_chain.py` for every multi-step run from now on. Do not chain through cmd.exe.

### 17 November 2026, 03:35

- The relaunched chain stopped at 02:34 in `s08_s2_compare.py border` for Pará with an AssertionError. `NEIGHBORS` was one fixed list, the neighbors of Mato Grosso, so Pará was loaded twice and Mato Grosso not at all. Replaced it with `NEIGHBORS_OF`, bordering states for each tier 1 and tier 2 state. Tested `border()` on Pará, Rondônia and Acre: Pará 119 fields lose their peer group without neighbors, Rondônia 59, Acre 26. Relaunched the chain at 03:32; Pará passed the border step.
- Open: `analysis/relative/source=s2/weather_fit.json` is rewritten by each state's relative step, so it now holds only the Pará rows; the Mato Grosso rows are gone. The Mato Grosso field tables already written are unaffected. A rerun of Mato Grosso relative would refit Mato Grosso. A per-state fit file would keep all of them; not changed yet.

### 17 November 2026, 06:40: Pará, Rondônia and Acre on Sentinel-2

- The chain finished at 05:58 (decisions 03:41, field tiles, summary tiles, upload of tiles and field GeoParquet). Live `stats.json` dated 2026-11-17 lists AC, MT, PA and RO as `s2`.
- Change threshold scale k (Sentinel-2 change SD over MODIS change SD, fields of 25 ha and more): Pará 1.1792 (24,416 fields), Rondônia 1.3233 (26,909), Acre 1.417 (4,219). Share of large fields changing class, MODIS against scaled Sentinel-2: Pará 19.91 and 19.9 percent, Rondônia 15.1 and 14.42, Acre 12.49 and 10.24. Exact agreement of the change class over all comparable fields, scaled: Pará 67.92, Rondônia 73.49, Acre 76.72 percent. Details in `data/summaries/s2_{pa,ro,ac}_noise.json`.
- National decisions after the swap (shown on the map), before in brackets: restore 52,253 (27,981), assisted natural regeneration 2,366 (1,787), restore candidate 384,872 (296,148), low confidence 18,562,422 (19,464,886), no suggestion 146,335 (425,978). Low-confidence flag: 18,705,778 fields, 76.2 percent (was 19,889,026, 81.0 percent).
- `docs/about.html` updated with these numbers. No cache buster change: the tiles and stats keep their S3 names.
- Next: Amazonas when its extraction completes, then Roraima and Amapá.

### 17 November 2026: live Chrome check (subagent a38aa9ca287550558)

- GeoParquet upload complete: 54 objects under `fields/` (run `upload_fields4.log` finished 19:32 on 16 November), refreshed by the swap upload on 17 November.
- Checked live: zoom 4 change view (dense 6 km cells on the ramp), zoom 4 decision view (several colors, not one), zoom 4 area view (area declining on the Amazon frontier and in Rio Grande do Sul, good land underused in the south, system misfit in São Paulo and Paraná), zoom 11 decision and area views near Sorriso, and the card of field 554556 (soybean, 252.7 ha, Keep, Area fine, Sentinel-2 30 m). Legend counts match `decisions_v2.json` after the Pará, Rondônia and Acre swap.
- Not checked: browser console, hover tooltip, the "Computed, not trusted" line of a low-confidence field, zoom 11 change view.
- 17 Nov, user, on the page layout: "Move the legend above the decision or the where on the
  right hand panel so that the legend is at the top of the page. On the page load ... please
  show the suggested decisions first ... so it goes Decisions productivity and then land use
  and then the more section. Change relative land productivity slash suggested decision on
  that top line to land use for more sustainable food production. And then ... suggested
  land use pathway instead of suggested decision." The decision question becomes "What would
  be a better land use decision for sustainable food?"; cut the zoom note ("Zoom 3.5: summary
  cells zoom past nine for fields"); the Where card shows only the field count and hectares
  ("I do not need to see the source imagery ... I don't need to see the low confidence I
  don't need to see the number of abandoned fields"); "Where" becomes "Select a state", with
  "Select a state" as the drop-down's first entry and no "State" label; cut "These are
  screening results from satellite greenness. They are not agronomic advice ..." from the
  decision view. Done in docs/index.html, docs/config.js and docs/app.js (cache busters v=11).
  The low-confidence control is hidden, so fields draw as usual. Default view is now the
  decision view (supersedes the 13 Nov default of the change view, DECISIONS.md D1).
- 17 Nov, user: "I don't want fields to be dropped at any zoom level once the fields do show".
  First tried: draw fields from zoom 12 and overzoom the summary cells to 11. The user rejected
  it: "I do not want hex grids this far zoomed in ... instead of dropping the fields keep all of
  the fields the browser can handle it". Done instead: fields show from zoom 9 again, and the
  zoom 9 to 11 field tiles are rebuilt with -pk -pf --no-tiny-polygon-reduction (no size limit,
  no dropping) in pipeline/s05_tiles.py. Rebuild, join and upload run hidden; until they land,
  zoom 9 to 11 still drops the smallest fields in dense tiles.
- 17 Nov, user: combine "Improve yields: spares land elsewhere" and "Improve yields" "into just
  'improve yields' with a + button that adds the sparing distinction to the map when clicked
  on", then "i dont understand the difference between intensify and improve yields. fold that
  in". The legend shows one row "Improve yields" (amber #eda100, count of the three classes);
  + splits it into improve yields that spares land, improve yields and intensify with their
  own colors on the map; minus combines them. `CLASS_GROUPS` in docs/config.js. Checked
  locally in Chrome at zoom 12 near Sorriso.
- 17 Nov, user: "turn off area decision from the page for now. Make Suggested land use
  mapthway bold." The Area decision view is hidden (`hidden: true` in config.js VIEWS; a link
  with ?view=area_decision opens the decision view), and the area call rows are gone from the
  tooltips; the field card still lists the area call. The nav link "Suggested land use
  pathway" is bold. The area call data and tiles are unchanged.
- 17 Nov, user: under "Select a state", show the distribution of the recommended land uses for
  the selected state. Done: bars of each recommendation's share of the state's fields with a
  trusted call (the Improve yields group as one bar unless split with +), and a line with the
  fields too small to judge and without data. Also: "'Action that stands out per cell' change
  to: 'Possible Sustainable Land Use Future'" (the decision view's zoomed-out legend title).
- 17 Nov, user asked why so many Amazon frontier cells, along rivers and in Amazonas, are gray
  ("no action stands out") although much of that pasture is unproductive ("don't force that
  ... I want you to investigate why they are Gray"). Investigation, `pipeline/s11_gray_cells.py`
  over the per-field decision tables (6 km cells; a cell takes a color when one actionable
  call has at least 15 percent of its trusted fields and 1.5 times its national share, with at
  least 10 trusted fields):
  1. In the states still on MODIS the cause is field size. Amazonas: 5,225 of 5,581 cells have
     under 10 fields with a trusted call; 97.3 percent of the fields in gray cells are low
     confidence (under 6.25 ha), so they show "too small to judge yet" and do not count.
     Roraima 1,354 of 1,705 cells, Maranhão 4,273 of 6,975, Tocantins 1,522 of 5,725 are gray
     for the same reason. Amapá: 59.5 percent of its fields have no data (cloud).
  2. If the computed (untrusted) calls counted, 4,718 of Amazonas's 5,486 gray cells would take
     a color: recently converted at or above peers 2,566, below peers 1,135, restore candidate
     593, restore 169. Over the Amazon biome, 13,315 of 26,050 gray cells would: recently
     converted 8,375, restore candidate 2,348, improve yields 1,842, restore 379.
  3. In the states on Sentinel-2 (Pará, Acre, Rondônia, Mato Grosso) most gray cells have
     enough trusted fields, and their pasture is not weak by this measure: the computed calls
     in gray cells are intensify (32 to 36 percent), keep (29 to 32), improve yields that spares
     land (15 to 18); 86 to 97 percent of their fields lie in cells whose area call is "area
     fine", that is, their pasture greenness is not below pasture across Brazil.
  4. The method measures greenness, not productivity. Humid Amazon pasture stays green through
     the season, so a lightly stocked or degraded pasture there can read as at or above the
     national pasture median. The relative measure compares a pasture with nearby pastures,
     so a whole region of weak pasture is not flagged at field level, and the area call sees
     Amazon pasture as fine. Pasture vigor (MapBiomas), which would address this, is not
     implemented (open item 4).
  Options for the user, none applied: (a) let summary cells count the computed calls of
  low-confidence fields, since a cell aggregates many small fields (colors about half of the
  gray Amazon cells, mostly recently converted land); (b) wait for Sentinel-2 in Amazonas,
  Roraima, Amapá, Maranhão and Tocantins, which removes most of the size problem; (c) add a
  pasture measure that is not greenness (MapBiomas pasture vigor or degradation).
- 17 Nov, user: "In the Amazon for those cells that no action stands out i'm surprised that more
  of them are not Restore candidate: next to native vegetation." Measured on the 1,764,017
  Amazon-biome fields with the same crop in both years and high confidence: 29.7 percent have
  at least 30 percent of their 1 km band in native patches of 50 ha or more; 31.1 percent are
  below their nearby same-crop peers; 8.3 percent meet both and are not gaining, which is the
  restore candidate rule. Of the native-rich fields, 36.5 percent are intensify, 29.1 keep and
  26.1 restore candidate: half of them are as green as or greener than nearby pasture (median
  r_adj_2024 0.01). Large native patches are no more common next to Amazon fields than
  elsewhere (median share of the 1 km band 0.154 against 0.148), because Amazon pasture lies in
  cleared blocks and the band reaches only 1 km past the field's bounding box. So few cells
  reach the 15 percent share and 1.5 times lift that color a cell. Not changed; options for the
  user: drop the "below peers" condition for native-rich pasture in the Amazon, widen the band,
  or lower the cell coloring rule for restore candidates.
- 17 Nov, user: "add a toggle that turns on the satellite imagery basemap under 'select a state'
  when its turned on, it adds an alpha of 0.25 to fields". Done: a "Satellite imagery" checkbox
  under the state drop-down shows Esri World Imagery tiles (no key, attribution in the map
  corner) below the data layers, and fields then draw at fill opacity 0.25
  (`CONFIG.SATELLITE_FIELD_OPACITY`). Summary cells keep their opacity. Checked locally in
  Chrome near Sorriso at zoom 12.5.
- 17 Nov, user: "design a walkthrough that takes someone high-level through the methodology,
  fields, years, productivity, productivity across years, native vegetation, land use, and how
  all of this led to the suggested land use pathways", and "use the stories:
  https://github.com/wri/organizational-scorecard-js to inform zoom methodology". Done: a "Take
  the tour" button at the top of the left nav opens a caption card over the top left of the map
  (bottom of the map on a phone) with nine steps, Back, Next (Finish on the last), a dot per step,
  Close, the arrow keys and Escape. Steps and cameras are `WALKTHROUGH` in docs/config.js; the
  logic is the walkthrough section of docs/app.js; `?tour=N` opens step N. The steps: (1) the
  decision view of Brazil; (2) fields over satellite imagery near Sorriso, Mato Grosso, zoom 13;
  (3) crop type 2020 at the same place; (4) relative productivity 2024 there; (5) the national
  frontier change map at zoom 4; (6) the decision view at zoom 9.4 on the Araguaia river, where
  Pará (Sentinel-2) shows trusted calls and Tocantins (MODIS) mostly "too small to judge yet";
  (7) native vegetation along the Cuiabá river, Mato Grosso, zoom 12 with satellite imagery;
  (8) restore cells near Porto Velho, Rondônia, zoom 8, to explain the area call; (9) the
  decision view of Brazil with Mato Grosso selected, so the state mix shows under "Select a
  state". Places were chosen by querying the tiles for restore, restore candidate and low
  confidence fields. What was taken from the scorecard stories (wt-stories, stories/index.html):
  a camera per step, few camera chapters with the zoom moving one way inside a chapter, a held
  camera that does not move, flight time scaled by zoom change and distance (there 4 to 7 s for
  scroll-driven stories, here 1.6 to 4.5 s because a click drives each step), the new layer
  arriving while the flight lands (there at 55 percent of the flight, here the view switch at the
  same point), padding so the target sits beside the text card, numbered stops to jump between
  steps (here the dots), and Escape to leave. Not taken: scroll-driven motion, autoplay and the
  disabled zoom; here the map stays free to pan and zoom during the tour. Closing puts back the
  reader's view, imagery, state and camera; Finish leaves the map at the last step. Captions
  take numbers only from METHODS.md, this log and stats.json. Tested locally in Chrome at 1381
  px (every step, keys, dots, Escape, Finish, no page errors in the console) and at 390 px by
  layout measurement in an iframe (no horizontal scroll, Back and Next inside the card).
- 17 Nov, user: "LAND USE FOR MORE SUSTAINABLE FOOD PRODUCTION / SUGGESTED LAND USE PATHWAY /
  DEMO <---- add the text 'DEMO' in bold after these". Added to the page header (bold, after
  the view name).
- 17 Nov 11:32, the zoom 9 to 11 rebuild moved into the repo as `pipeline/s05c_rebuild_lowzoom.py`
  (with `pipeline/s05c_join.sh`, the tile-join script it runs inside WSL as ~/join.sh). The first
  run died at 11:18 after the GeoJSON step on a log() keyword clash; fixed, and relaunched
  hidden through WMI and pipeline/launch_detached.py at 11:32 (python pid 46772). It reused the
  27 per-state GeoJSON files and is building the zoom 9 to 11 state tiles. Log:
  F:\relative-land-productivity-data\analysis\decisions\logs\rebuild_lowzoom.log.
- 17 Nov, user: simplify and shorten the public prose without changing titles or headings.
  Revised the GitHub Pages copy and the repository README. The map still uses the same
  data and methods (DECISIONS.md D20).
- 17 Nov, user: "the alpha is too high, make the fields stand out more on the map when satellite
  view is turned on". Fields over the imagery now draw at fill opacity 0.65 (was 0.25) with white
  outlines (opacity 0.85), and the usual outlines come back when the imagery is off
  (`CONFIG.SATELLITE_FIELD_OPACITY`, `CONFIG.SATELLITE_LINE`). Checked locally that the toggle
  runs without console errors; a screenshot could not be taken because the tile build was
  using the machine.

### 17 November 2026, 12:35: zoom 9 to 11 rebuild stuck at the join

- `s05c_rebuild_lowzoom.py` finished tippecanoe for all 27 states at 11:51, then waited 40 minutes for a join that never ran. Two bugs: the join was started with `setsid nohup ... &` inside a short `wsl.exe` call, and `~/join.sh` did not run (its log was still from 16 November); the wait loop polled `\wsl.localhost\...` with one leading backslash, a path that never exists.
- Fixed: `join()` now runs `wsl -d Ubuntu-22.04 -- bash /home/tristangrupp/join.sh` blocking (the script itself runs detached) and reads `\wsl.localhost\...`. Added `--from-join` to rerun only the join, copy and upload. Stopped pid 46772 and relaunched with `--from-join` at 12:32; tile-join is running in WSL.

### 17 November 2026, 13:35: zoom 9 to 11 rebuild, join done, copy and upload running

- The relaunched `--from-join` run joined the tiles at 12:49 (tile-join rc 0, `fields.pmtiles` 9,027,039,966 bytes, up from 7,060,673,632 with dropping), then the Python process vanished before logging the join, with nothing in its stderr. Cause not found.
- Added `--from-copy` (skip the join, copy the joined file to F:, upload). Launched at 13:31 hidden; the copy is running. Log: `analysis\decisions\logs\rebuild_lowzoom.log`, output `rebuild_copy.stdout` and `.err`.

### 17 November 2026, 14:32: zoom 9 to 11 no-drop tiles live

- Copy to F: done 13:32; upload done (rc 0, three 206 checks). S3 `tiles/fields.pmtiles` is 9,027,039,966 bytes, last modified 18:32 UTC. `stats.json` and `summary.pmtiles` were skipped as same size.
- Still to check: map speed at zoom 9 to 10 over São Paulo and Paraná with the larger tiles.
- Next: switch Amazonas to Sentinel-2 when its extraction is complete.
- 17 Nov 14:08, the zoom 9 to 11 no-drop field tiles are live. pipeline/s05c_rebuild_lowzoom.py
  rebuilt all 27 states' zoom 9 to 11 tiles (by 11:51), the WSL join finished at 13:31, and
  fields.pmtiles (9,027,039,966 bytes, up from 7,060,673,632) uploaded in 2,161 s at 4.18 MB/s;
  all three tile objects answer range requests with 206. Live check in Chrome at zoom 9.5 over
  Campinas, São Paulo: every field draws, the view filled in within about 10 seconds.

### 18 November 2026, 01:30: Amazonas on Sentinel-2

- Amazonas extraction reached 771 of 771 tiles by 22:32 on 17 November. The swap chain (`s09_swap_state_to_s2.py --state Amazonas`, hidden through WMI, `launch_detached.py` and `run_chain.py`) started at 22:32 and ended at 01:16 with exit 0: decisions 22:40, field tiles 23:53, tile upload 00:29, field GeoParquet upload 01:16.
- Change threshold scale k = 1.1637 (Sentinel-2 change SD 0.8696 over MODIS 0.7473, 986 fields of 25 ha and more). Share of large fields changing class: MODIS 20.69, Sentinel-2 unscaled 26.27, scaled 20.18 percent. Exact agreement of the change class over 102,164 comparable fields: 64.73 percent unscaled, 69.46 scaled. Details in `data/summaries/s2_am_noise.json`.
- National decisions after the swap, before in brackets: restore 56,381 (52,253), assisted natural regeneration 2,499 (2,366), restore candidate 396,903 (384,872), low confidence 18,468,381 (18,562,422), no suggestion 138,936 (146,335). Low-confidence flag: 18,468,381 fields, 75.2 percent (was 18,705,778, 76.2 percent). Fields on Sentinel-2: 3,332,019.
- Checked live: `stats.json` dated 2026-11-17 lists AC, AM, MT, PA and RO as Sentinel-2; `fields.pmtiles` is 9,027,681,355 bytes, Last-Modified 04:55 UTC on 18 November, so the zoom 9 to 11 no-drop rule held through the rebuild. Map not looked at in a browser.
- `docs/about.html` updated with these numbers.
- Next: Roraima (extraction 11 of 155 tiles at 22:32), then Amapá.

### 18 November 2026, 05:30: Roraima on Sentinel-2

- Roraima extraction finished (155 of 155 tiles) by 02:31. The hidden swap chain ran 02:31 to 04:47 with exit 0.
- k = 1.2656 (Sentinel-2 change SD 0.803 over MODIS 0.6345, 1,731 fields of 25 ha and more). Large fields changing class: MODIS 16.29, Sentinel-2 unscaled 23.28, scaled 14.85 percent. Exact agreement over 50,358 comparable fields: 65.13 percent unscaled, 72.9 scaled. Details in `data/summaries/s2_rr_noise.json`.
- National decisions after the swap, before in brackets: restore 57,204 (56,381), assisted natural regeneration 2,522 (2,499), restore candidate 403,924 (396,903), low confidence 18,429,853 (18,468,381), no suggestion 137,095 (138,936). Low-confidence flag 75.1 percent. Fields on Sentinel-2: 3,398,203.
- `docs/about.html` updated. Amapá extraction finished (69 of 69) and its swap started at 05:31.

### 18 November 2026, 06:35: Amapá swap failed, fixed, relaunched

- The Amapá swap (started 05:31) stopped at 05:32 in `s08_s2_compare.py` calibrate with `KeyError: 'slope'`. No peer class in Amapá has 100 fields over 25 ha with high MODIS confidence, so no row was fitted and the table had no slope column. The noise step then found 0 large fields on both sensors, so k was NaN, and validation found no municipality with yields on both sensors.
- Fixes in `pipeline/s08_s2_compare.py`: the calibration table keeps fixed columns (`CAL_COLS`); a state with under 100 large fields takes the median k of the states already on Sentinel-2, recorded as `change_scale_from` (Amapá: 1.2415, median of 6 states); validation logs and returns when it has no rows. Recorded as DECISIONS.md B19.
- Tested `all` on Amapá by hand through noise and validate: 546 comparable fields of 8,420; changing share over all comparable fields MODIS 39.38, Sentinel-2 scaled 25.09 percent; exact agreement 58.79 percent scaled.
- Relaunched the swap hidden at 06:33 (pid 12080, log `swap_amapa2.log`).

### 18 November 2026, 08:35: Amapá on Sentinel-2

- The relaunched swap (06:33) ran decisions, field and summary tiles and the tile upload (08:16, all three objects answer 206). Live `stats.json` lists AC, AM, AP, MT, PA, RO and RR as Sentinel-2.
- The field GeoParquet upload failed at 08:19 on Amapá's `fields_scored.parquet`: "Connection was closed before we received a valid response", four attempts. Network error, not data. Relaunched `s05_upload.py --fields` hidden at 08:33 (log `upload_fields_amapa.log`); files already on S3 at the same size are skipped.
- Amapá: k = 1.2415 (pooled, DECISIONS.md B19). Exact agreement over 546 comparable fields 58.79 percent scaled. No-data change class 98 of 8,420 fields (1.2 percent), against 59.6 percent on MODIS.
- National decisions after the swap, before in brackets: restore 57,228 (57,204), assisted natural regeneration 2,528 (2,522), restore candidate 404,703 (403,924), low confidence 18,430,125 (18,429,853), no suggestion 133,044 (137,095). Fields on Sentinel-2: 3,406,623.
- `docs/about.html` updated. All tier 1 Amazon states are now on Sentinel-2. Next: Mato Grosso do Sul, Goiás, Tocantins, Maranhão as extraction finishes.
- 09:35: the 08:33 retry failed the same way, so not a network blip. `fields_scored.parquet` for Amapá is 8,028,195 bytes, under the 8 MiB multipart threshold, so `aws s3 cp` sends one PUT. With `--acl public-read` on a single PUT the bucket closes the connection instead of answering AccessControlListNotSupported, and `s05_upload.py` only fell back to no ACL on that message. A manual `aws s3 cp` without the ACL succeeded (rc 0). `s05_upload.py` now falls back on "Connection was closed" too. Relaunched `s05_upload.py --fields` hidden at 09:34 (log `upload_fields_amapa2.log`) for the remaining states.

### 19 November 2026, 01:30: Mato Grosso do Sul on Sentinel-2

- Extraction reached 429 of 433 tiles (99.1 percent) at 22:31 on 18 November. The hidden swap chain ran 22:31 to 01:05 with exit 0 (decisions 22:38, field tiles 23:38, tile upload 00:15, field GeoParquet 01:05).
- k = 1.1586 (Sentinel-2 change SD 0.8525 over MODIS 0.7358, 162,021 fields of 25 ha and more). Large fields changing class: MODIS 23.21, Sentinel-2 unscaled 28.06, scaled 22.64 percent. Exact agreement over 496,691 comparable fields: 71.98 percent unscaled, 75.57 scaled.
- National decisions after the swap, before in brackets: restore 58,542 (57,228), assisted natural regeneration 2,547 (2,528), restore candidate 412,591 (404,703), low confidence 18,280,899 (18,430,125), no suggestion 133,246 (133,044). Low-confidence flag 74.5 percent. Fields on Sentinel-2: 3,996,796. Live `stats.json` lists AC, AM, AP, MS, MT, PA, RO and RR.
- Memory: during the tile build vmmemWSL reached 18.8 GB, not the 10 GB planned. With the water session's prediction job (7.5 GB) and ArcGIS Pro (6.5 GB) also running, commit reached the 119.8 GB limit at about 23:20 and the Fields of the Land 1990 run was killed (about 2.5 hours of reads lost, 52 finished tiles safe). The sharing terms in AGENTS.md now cover the whole build window and all three projects.
- `docs/about.html` updated. Next: Goiás, Tocantins, Maranhão.

### 20 November 2026, 02:00: Goiás on Sentinel-2

- Extraction reached 402 of 402 tiles during 19 November; the hourly check had stopped with a session restart, so the swap started late, at 23:13. The hidden chain ran 23:13 to 01:50 with exit 0 (decisions 23:27, field tiles 00:28, tile upload 01:03, field GeoParquet 01:50).
- k = 1.1611 (Sentinel-2 change SD 0.739 over MODIS 0.6364, 158,332 fields of 25 ha and more). Large fields changing class: MODIS 18.72, Sentinel-2 unscaled 23.55, scaled 18.67 percent. Exact agreement over 1,033,443 comparable fields: 75.47 percent unscaled, 79.34 scaled. Scaled changing share is flat across size bands (17.96 to 18.81 percent), while MODIS rises from 13.36 under 6.25 ha to 20.04 over 100 ha.
- National decisions after the swap, before in brackets: restore 59,897 (58,542), assisted natural regeneration 2,709 (2,547), restore candidate 442,839 (412,591), low confidence 17,811,023 (18,280,899), no suggestion 133,719 (133,246). Low-confidence flag 72.5 percent. Fields on Sentinel-2: 5,250,284. Live `stats.json` (generated 20 November) lists AC, AM, AP, GO, MS, MT, PA, RO and RR.
- Memory: before the build the water session stopped its prediction job and both Sentinel-1 fetchers (suspending them does not free commit), and commit stayed near 80 GB through the tile build. Even so, the harness of the Fields of the Land session killed its 1990 run for memory pressure during the build (84 of 379 tiles safe). For the next builds, ask Fields of the Land to pause its run for the tile build (its 3 workers peak near 10 GB, so 2 workers would free little), and watch free physical memory as well as commit.
- `docs/about.html` updated. Next: Tocantins (111 of 288 tiles at 23:12 on 19 November), then Maranhão.

### 20 November 2026, 09:40: Tocantins on Sentinel-2

- Extraction reached 287 of 288 tiles at 06:46. The hidden swap chain ran 06:47 to 09:30 with exit 0 (decisions 06:53, field tiles 07:49, tile upload 08:28, field GeoParquet 09:30; the field upload shared the link with the restarted Fields of the Land run).
- k = 1.1729 (Sentinel-2 change SD 0.7015 over MODIS 0.5981, 55,863 fields of 25 ha and more). Large fields changing class: MODIS 16.14, Sentinel-2 unscaled 20.81, scaled 15.77 percent. Exact agreement over 407,468 comparable fields: 76.12 percent unscaled, 80.57 scaled.
- National decisions after the swap, before in brackets: restore 60,778 (59,897), assisted natural regeneration 2,852 (2,709), restore candidate 464,972 (442,839), low confidence 17,599,388 (17,811,023), no suggestion 134,036 (133,719). Low-confidence flag 71.7 percent. Fields on Sentinel-2: 5,731,191. Live `stats.json` lists AC, AM, AP, GO, MS, MT, PA, RO, RR and TO.
- Why low confidence stays high (user question, 20 November): by state, the ten Sentinel-2 states are at 18 to 38 percent low confidence (25.4 percent of their 5.9 million rows), and the 17 MODIS units at 71 to 93 percent (82.9 percent of 19.4 million rows). Under MODIS a field under 6.25 ha (one pixel) is low confidence, which is most fields outside the frontier states. Only switching the remaining states to Sentinel-2 lowers the national share much further.
- Memory: at 07:3x free physical memory fell to 1.2 GB with commit at 87 GB. vmmemWSL held 29.6 GB, 25 GB of it page cache from the tippecanoe temp files. Dropping the WSL cache freed it at once. `s05_tiles.py` now drops the WSL page cache every 2 minutes while tippecanoe or the copy runs (73b0ee4). This also explains the Fields of the Land kill during the Goiás build.
- `docs/about.html` updated. Next: Maranhão (extraction started); the 15 remaining states and the Federal District wait for the user's go.

### 20 November 2026, 10:55: tier 3 queued (user decision A13)

- The user approved moving every remaining state and the Federal District to Sentinel-2: "yes queue those 16 to follow. 3 days isnt bad".
- `s03g_weights.TIER_STATES[3]` lists them by 2024 field count: Minas Gerais, Bahia, Rio Grande do Sul, São Paulo, Paraná, Santa Catarina, Pernambuco, Ceará, Paraíba, Espírito Santo, Piauí, Rio Grande do Norte, Alagoas, Rio de Janeiro, Sergipe, Distrito Federal. 3,276 tiles, 3,126 not already in tier 1 or 2.
- Launched hidden at 10:52 (log `F:\relative-land-productivity-data\extracted\s2\run_tier3.log`): `run_chain.py` runs `pipeline/wait_pid.py 38160`, then `s03g_s2_fetch_reduce.py run --tier 3 --workers 4 --threads 2 --min-days 2`, so tier 3 starts only when the tier 1 and 2 run (now on Maranhão, 86 of 352 tiles at 10:31) exits. At 41 tiles per hour that is about 76 hours.
- Plan for the swaps: run each state with `s09_swap_state_to_s2.py --no-tiles --no-upload` as it completes, then one field tile rebuild and one upload for the batch, so there are not 16 separate 9 GB rebuilds. The machine-sharing terms in AGENTS.md apply to that build.
- Why: under MODIS 82.9 percent of these states' fields are low confidence, against 25.4 percent in the ten states on Sentinel-2.

### 20 November 2026, 12:10: possible mis-detection of recently converted land (agent, at the user's request)

- User: "Field 612719 in Mato Grosso might be recent conversion, but given its huge size and geometry, it looks a bit like a misdetection/mis-segmentation by the Trazo4 model. Design a check on these and create a category of recent conversion called 'possible mis-detection'."
- Field 612719 (Mato Grosso, centroid -54.354, -13.323, municipality 5106307): 10,909 ha, the largest 2024 field in the state; perimeter 179.5 km; Polsby-Popper 0.043 (Mato Grosso pasture 1st percentile 0.056); solidity 0.735; 10,209 vertices; 88 holes (99th percentile 11). MapBiomas mode forest (3) in 2020 and pasture (15) in 2024. Inside the outline, native vegetation is 94.5 percent of the pixels in 2020 and 33.0 percent in 2024; pasture covers 67.0 percent. Native within 1 km 44.5 percent. Sentinel-2, 10 and 11 clear months, high confidence, `r_eco_2024` 0.33, so it was converted at or above peers. Now `converted_misdetect`, `decision_computed` `converted_ok`.
- New step `s07_decisions.py shape` writes `analysis\decisions\shape\<State>.parquet` (outline shape of all 24,554,482 2024 fields, MapBiomas shares inside the newly cropped outlines). It ran 11:17 to 11:55, hidden, under 1.3 GB.
- Rule (METHODS.md 7.8, DECISIONS.md C22): a computed converted call, area at or above the 99th percentile of its MapBiomas class in its state and at least 50 ha, and 25 percent or more of the pixels inside the outline native vegetation in 2024. It wins over low confidence. Thresholds: native inside large same-crop fields (200,109 fields at or above their class and state 99th percentile) has a 95th percentile of 21.8 percent; the 50 ha floor keeps mixed edge pixels on small irregular outlines from triggering it (without it, 3,855 flags, mostly 10 to 40 ha in the south).
- Result: 2,512 of 1,635,769 computed converted fields (0.154 percent); 415 of them were low confidence. Before this change 384,710 fields showed a converted class, so 2,097 (0.55 percent) of those move. By state: BA 409, RS 346, MG 305, MT 215, PI 207, CE 189, MA 180, PA 110, PE 107, TO 86, GO 71, MS 70, RO 41, SE 40, PB 27, RN 21, AL 20, RR 19, AM 15, ES 9, SP 9, SC 5, RJ 4, DF 3, PR 3, AC 1, AP 0.
- Flagged fields against large converted fields not flagged: median Polsby-Popper 0.087 against 0.148; own 2024 class inside 53 against 92 percent; 67 percent at or below the 5th percentile of compactness of their class and state.
- Flagged samples (fid, state, lon, lat): 612719 MT -54.352 -13.323 (10,909 ha, native 33.0 percent); 287555 PI -42.852 -6.948 (3,514 ha, 43.1); 168151 BA -40.524 -9.650 (2,716 ha, 45.5); 100258 RO -64.982 -9.598 (1,992 ha, 49.8); 2202 MS -55.829 -17.433 (424 ha, 45.9). Borderline, not flagged: 436338 MT -54.889 -11.154 (2,518 ha, Polsby-Popper 0.045, 64 holes, native 16.7 percent); 979231 PA -55.988 -4.778 (193 ha, native 21.7); 101001 GO -48.697 -13.602 (112 ha, native 36.6, under the Goiás pasture 99th percentile of 120.6 ha).
- Site: `converted_misdetect` in `docs/config.js`, "Possible mis-detection", #364036 (dark green-gray, full opacity). Under simulated protan, deutan and tritan vision (Machado 2009, CIEDE2000, raw hexes as for D12) it is 13.8 or more from every class; no yellow-green or olive passed 12 against the green family, because those collide with restore under protan and deutan vision. At half opacity it would fall to 5.3 from assisted natural regeneration, so it draws at full opacity. The field card shows its converted call as "Computed, not trusted" (`showComputed`, shared with low confidence). Cache busters `app.js?v=21`, `config.js?v=21`.
- Ran `s07_decisions.py fields` and `report` (12:00 to 12:05) after checking that no swap chain was running. Tiles and uploads were not run: the published tiles show the class from the next state swap (Maranhão), which rebuilds them. Until then the legend row reads 0.


### 20 November 2026, 14:05: header label DATA POC (user decision D21)

- The user asked to rename "DEMO" in the main page header to "DATA POC", with an info marker next to it whose hover text reads "This is a Data Lab prototype and an experimental application; Data Proof of Concept."
- docs/index.html: the label and a button .crumb-info holding the tooltip #pocTip; it opens on hover and keyboard focus. Cache buster style.css v=20.
- docs/style.css: the header crumbs are now a flex row. The title and view name shrink with an ellipsis on narrow screens, so DATA POC and its marker stay visible; before, a 1,148 px wide window cut the DEMO label off.
- Checked on the local server in Chrome at 1,148 px: label, marker and tooltip show.

### 21 November 2026, 13:45: Maranhão extraction slowdown explained

- Maranhão gained 4 or 5 tiles per hour from about 19:00 on 20 November to 10:00 on 21 November, against about 12 before. Fields of the Land found the cause: at 18:14 on 20 November the Wi-Fi moved from 5 GHz 802.11ax (480 Mbps) to 2.4 GHz 802.11n (72.2 Mbps). It returned to 5 GHz about 10:40 on 21 November, and Maranhão has gained 16 to 20 tiles per hour since. `netsh wlan show interfaces` at 13:45 shows 5 GHz, 802.11ax, receive 721 Mbps, transmit 480 Mbps.
- Fields of the Land was warned at 13:30 that the Maranhão build starts near 15:30, and confirmed it pauses for the whole build and upload, now through its PAUSE file. Recorded in AGENTS.md.

### 21 November 2026, 18:40: Maranhão on Sentinel-2

- The first swap launch at 15:43 stopped with exit 1: "Maranhao 2020: 404 of 410 tiles complete, under 0.99; wait for s03g". The s03g status counts 352 Maranhão tiles, but the assemble check in `s03h_s2_assemble.py` counts the 410 tiles that touch the state and needs 99 percent of them (406) with all 24 months. So "350 of 352" in the status was not enough. Relaunched hidden at 15:55 once 407 tiles were complete.
- The chain ran 15:55 to 18:30 with exit 0: decisions 305 s, field tiles 16:02 to 17:03 (3,698 s), tile upload 17:05 to 17:39 (2,021 s), field GeoParquet upload 17:39 to 18:30 (3,110 s).
- k = 1.1859 (Sentinel-2 change SD 0.8322 over MODIS 0.7018, 15,505 fields of 25 ha and more). Large fields changing class: MODIS 20.90, Sentinel-2 unscaled 26.19, scaled 19.84 percent. Exact agreement over 427,524 comparable fields: 64.98 percent unscaled, 69.97 scaled. Agreement is lower than in Tocantins (80.57 scaled); 275,038 of the comparable Maranhão fields are under 6.25 ha, where MODIS reads mostly neighboring land.
- National decisions after the swap, before in brackets: restore 63,273 (60,778), assisted natural regeneration 3,134 (2,852), restore candidate 493,703 (464,972), low confidence 17,302,378 (17,599,388), no suggestion 112,636 (134,036). Low-confidence flag 70.5 percent. Fields on Sentinel-2: 6,298,316. Live `stats.json` lists AC, AM, AP, GO, MA, MS, MT, PA, RO, RR and TO.
- The rebuilt tiles publish `converted_misdetect` (Possible mis-detection, C22) for the first time.
- `fields.pmtiles` is now 9,029,658,874 bytes. The About page said 6.4 GB; it now says 9.0 GB.
- Memory: free physical memory bottomed at 5.2 GB during the copy of the tiles from WSL to F:. vmmemWSL kept 20 to 27 GB of Windows memory while WSL used under 1 GB inside; dropping caches and compacting did not return it. Only `wsl --shutdown` or a `.wslconfig` cap does, and that waits for the user.
- The Fields of the Land run was reaped for memory between 15:55 and 16:02, about 85 tile-minutes lost. The most likely cause is this swap's steps before the tile build (assemble, metrics, relative, compare, decisions), whose memory peak was never measured. Before tier 3: record the minimum free physical memory per step, and treat the whole swap, not only the tile build, as the window in which Fields of the Land pauses.
- `docs/about.html` updated. Next: the 15 remaining states and the Federal District (tier 3 extraction running since 16:04).

### 21 November 2026, 19:25: paused for a shutdown

- The user is shutting the computer down for about 20 minutes. Tier 3 extraction (run_chain 26740, s03g 12984) was stopped at 19:24 with `taskkill /T`. 109 of 3,276 tier 3 tiles had finished (TILE_DONE count in `run_tier3.log`).
- Nothing is lost beyond the months in flight: s03g resumes at tile-month granularity and writes each tile parquet through a temporary file and `os.replace`, so an interrupted write leaves the previous file intact.
- Nothing else of this project was running. The Maranhão swap had finished at 18:30 and is committed (76a434a).
- Resume, hidden, with the WMI pattern in AGENTS.md: `run_chain.py "pipeline/s03g_s2_fetch_reduce.py run --tier 3 --workers 4 --threads 2 --min-days 2"`, log `F:\relative-land-productivity-data\extracted\s2\run_tier3.log`, err `run_tier3.err`. No `wait_pid` step is needed now.
- The hourly check cron lives in the Claude session and ends with it; recreate it after the restart.

### 22 November 2026, 10:36: tier 3 extraction resumed after the shutdown

- The computer rebooted at 10:31. Wi-Fi is on 5 GHz 802.11ax.
- The first relaunch at 10:34 used the resume command from the 19:25 entry, which runs s03g through `run_chain.py` under the wci_tools venv. It stopped in 5 s with "ModuleNotFoundError: No module named 'odc'". s03g needs the ftwtools Python (`C:\Users\grupp\miniconda3\envs\ftwtools\python.exe`), as its docstring states; the 19:25 entry left that out.
- Relaunched hidden at 10:35: `launch_detached.py run_tier3.log run_tier3.err -- <ftwtools python> pipeline/s03g_s2_fetch_reduce.py run --tier 3 --workers 4 --threads 2 --min-days 2`. It skipped the finished tiles and is fetching again.
- The hourly check cron was recreated in the new Claude session (grupp-f5). Water infrastructure is grupp-a2, running 15_point_requests.py (up to about 34 GB) and the viewer on 8830.
