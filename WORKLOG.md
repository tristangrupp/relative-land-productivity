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

Reports: pipeline/PROBE.md, EXTRACT.md, EXTRACT_S2.md, ANALYZE.md, EXPLORE_ECOREGIONS.md,
DECISIONS_V2.md. Methods: methods/METHODS.md. Site contract: docs/DATA_CONTRACT.md.

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

## Open items

1. Decisions version 2 is built (see the log). Questions for the user, from DECISIONS_V2.md:
   restore is rare (91,076 fields, none on the Amazon frontier); should area declining with
   pasture alone lead to restore for its declining fields? Is "improve yields" right for
   below-and-stable fields that version 1 called switch crop? Is the 1.5 lift in the
   zoomed-out top-action rule acceptable?
2. Resolution 7 summary cells (about 2.5 km) at zooms 7 to 9 measured 173.0 MB, over the
   150 MB budget; resolution 6 is used at every zoom. A slimmer resolution 7 layer (fewer
   attributes) could fit if the user wants it.
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
