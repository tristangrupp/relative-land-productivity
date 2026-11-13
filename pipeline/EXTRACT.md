# MODIS NDVI extraction to every prepared field

Written 2026-11-12 by the extract agent. This report follows the Decisions entry of the same
day that moved the national product to MODIS MOD13Q1 (Terra, 250 m, 16-day NDVI) from the
Planetary Computer. The stages are `pipeline/s03c_modis_fetch.py` (download),
`pipeline/s03d_modis_weights.py` (coverage weights), `pipeline/s03e_modis_reduce.py`
(per-field NDVI series) and `pipeline/s03f_mapbiomas_fields.py` (MapBiomas classes per
field). Every stage runs in the wci_tools venv
(`E:\Water\water intelligence\wci_tools\.venv\Scripts\python.exe`), which has pystac_client
0.9, planetary_computer 1.0, requests, rasterio 1.5.2, exactextract 0.3.0, geopandas 1.2,
scipy 1.18 and pyarrow. No Earth Engine is imported anywhere.

## What the Planetary Computer holds

Collection `modis-13Q1-061` holds both Terra (`MOD13Q1`) and Aqua (`MYD13Q1`) items, eight
days apart. The pipeline takes Terra only. A Terra composite starts on day of year 1 + 16k.
Agricultural year Y (1 September of Y-1 to 31 August of Y) is covered by the 23 composites
from day 241 of Y-1 (29 August, 28 August in a leap year) through day 225 of Y (12 to 27
August). Composite 241 of Y covers 28 August to 12 September and is left to the next year.

Twenty-two MODIS tiles fall in the Brazil bbox (-74, -34, -34, 5.5). Eighteen of them touch
an extraction tile with prepared fields (`raw\modis\tiles_needed.json`): h13v10, h13v09,
h13v11, h12v10, h12v09, h11v09, h14v10, h14v09, h11v10, h12v11, h13v12, h11v08, h10v09,
h12v08, h14v11, and three marginal tiles that touch one to three extraction tiles each
(h10v08 in Amazonas, h12v12 in Rio Grande do Sul, h13v08 in Amapá). h15v11, h11v12, h11v11
and h10v10 touch no field. The footprints come from the sinusoidal grid constants densified
and reprojected, intersected with `grid\tiles.parquet`.

The Terra composite `A2024225` (12 to 27 August 2024) is not in the collection for any Brazil
tile. The STAC search over that window returns only Aqua items (A2024217, A2024233) and the
Terra composites on either side (A2024209, A2024241). Agricultural year 2024 has 22
composites. The gap sits at the end of the dry season and is filled by linear interpolation
in the reduce stage. `raw\modis\missing.json` records it.

Asset sizes per tile and composite, measured by HEAD on A2024001: NDVI 13 to 50 MB on land
tiles (int16, 4800 x 4800, deflate), VI_Quality 2 to 14 MB (uint16), pixel_reliability 0.2 to
2 MB (uint8). The 18 needed tiles sum to about 750 MB per composite, 2,484 files over the 46
composites.

Mask rules used in the reduce stage: NDVI fill -3000 and values outside the valid range
-2000 to 10000 are masked. `pixel_reliability` 2 (snow/ice) and 3 (cloudy) are masked, and 255
(fill) is masked. `VI_Quality` bits 0 to 1 (MODLAND QA) equal to 2 (snow/ice) or 3 (cloudy)
are masked. Reliability 0 (good) and 1 (marginal) are kept, as is MODLAND QA 1 ("check other
QA"), because dropping marginal pixels leaves wet-season Amazon fields with no observation.

## Fetch: measured rate

The fetch started at 14:06 on 2026-11-12 with the other projects' downloads still running.
First ten files: 0.19 GB in 78 s of active transfer, 2.42 MB/s. The 40 MB NDVI files moved
at 3.0 MB/s, the small reliability files at 0.2 MB/s because each costs a signing call and a
connection. Projection at ten files: 40.7 GB remaining, finish about 18:48 the same day
(about 4.7 hours). At 20 files the rate was 2.27 MB/s and the projection 18:42. This is
faster than the 0.3 to 1 MB/s the brief expected. The shared pulls appeared to have eased at that moment.


## Weights on the MODIS grid

`s03d_modis_weights.py` reprojects each field to the MODIS sinusoidal projection
(`+proj=sinu +R=6371007.181`, the sphere the tiles declare) and runs exactextract against a
4800 x 4800 template GeoTIFF of the tile, so the cell ids match the row-major order rasterio
reads from a downloaded MOD13Q1 GeoTIFF. The weights are float32 coverage fractions in a
scipy CSR matrix of fields by 23,040,000 cells, one per tile and agricultural year, with a
parquet of the row order. Fields are read in 50,000-row batches through a pyarrow filter on
the GeoParquet bbox column.

Checks: the median ratio of covered cell area (coverage sum times 5.3665 ha) to the field's
`area_ha` is 1.003 on h14v11 2024 and 1.004 on h14v09 2020, as expected from two equal-area
projections. On 25 random h14v11 fields of 1 to 14 cells, the sparse product `W @ NDVI`
divided by the row sum matches exactextract's own `mean` on the downloaded 2023241 NDVI
tile to 0.005 raw units (5e-7 NDVI, the weights are float32). exactextract applies the
GeoTIFF `scale_factor` tag 10000 as a multiplier, so its means are raw values times 10,000.
The reduce stage reads raw int16 and multiplies by 0.0001 itself.

Timing: h14v11 2024 (Espírito Santo, Minas Gerais, Rio de Janeiro part) 635,361 rows,
2.33 M nonzeros, 187 s. h14v09 2020: 2,060,599 rows, 6.63 M nonzeros, 762 s. That is about 2,700
field rows per second per worker, with 30 to 32 percent of fields inside a single MODIS cell.
The first run with six workers reached 3 to 6.6 GB per worker on the largest tiles, 27 GB
in all, while other sessions' training held the rest of the machine, so it was stopped at
14:35 after five tile-years and restarted at 14:36 with four workers and three changes: int32
column ids and a CSR built from row counts instead of a COO triplet, per-batch frames instead
of a Python tuple per field, and pyarrow read-ahead limited to one batch. Three tasks of the
first run (h14v09, h13v11, h13v10 for 2024) had also failed when two workers renamed the
same template file at once. Templates are now made once in the parent before the pool
starts. The four-worker run took 109.1 minutes for the remaining 31 tile-years and still
peaked at 5.98 GB in one worker and 19.09 GB for the whole pipeline (fetch, four weights
workers, samplers) at 16:11, above the 16 GB the orchestrator asked for. The two h13v11
tile-years (8.77 and 8.78 million rows, 33.5 and 33.7 million nonzeros) took 5,690 s each.
The full timing per tile and year is in `weights\modis\timing.jsonl`, the memory samples in
`logs\mem.log`.

## Pasture vigor

No MapBiomas pasture vigor GeoTIFF was found at a public URL on 2026-11-12. What was tried:

- `https://storage.googleapis.com/mapbiomas-public/initiatives/brasil/collection_10/...`
  answers 403 for every path tried, including the coverage path the brief names and
  `pasture_quality` variants under collection_9 and collection_10.
- `https://brasil.mapbiomas.org/en/downloads/` says the map download function is
  temporarily suspended and points to Earth Engine assets, which this project cannot use.
- `s3://wri-datalab-sandbox/trazofields/mapbiomas/` holds state shapefiles, no vigor raster.
- The platform `https://plataforma.mapbiomas.org/projects/mapbiomas/brazil` has a
  Downloads button, "Download Maps (GeoTiffs)", "Generate custom map (GeoTiff)", then a
  four-step wizard: analysis type, territory (Brasil, IBGE 2025), theme of interest
  (Pasture col. 11, "Vigor condition", one year on a slider, default 2025) and a revision
  step with an optional "Notify me by email" box and a Finish button. It asked for no login
  up to Finish. It offers Collection 11, not the Collection 10 the methods name, one year per
  job, and warns that generating a custom map "can take minutes or hours". The job was not
  submitted and the delivery path was not tested. `vigor_2020` and `vigor_2024` are null in
  `classes.parquet`. `s03f_mapbiomas_fields.py classes --vigor-2020 <tif> --vigor-2024 <tif>`
  fills them from local 30 m GeoTIFFs (values 1 low, 2 medium, 3 high, 0 and 255 ignored)
  when someone obtains the files.

## MapBiomas classes per field

Both coverage rasters came from S3 with resume: `brazil_coverage_2024.tif` 802,022,037 bytes
in 152 s (5.27 MB/s) and `brazil_coverage_2020.tif` 786,924,975 bytes in 183 s (4.31 MB/s),
faster than the Planetary Computer link, and the MODIS fetch slowed to 0.1 MB/s while they
ran. Both are tiled 256 x 256, LZW, uint8, no overviews, on the grid of `grid\grid.json`.

Method comparison on the first 50,000 Mato Grosso 2024 fields (`--measure`): the rasterize
path (pixel centers inside the polygon in the field's own bbox window, all_touched fallback,
centroid pixel fallback, windows cached per 1024 x 1024 extraction tile) took 29.3 s for
both rasters, 0.586 ms per field. exactextract's coverage-weighted `mode` took 9.3 s for
20,000 fields on one raster, 0.463 ms per field, so about 0.93 ms for two. The two agree on
99.51 percent of fields and the rasterize mode agrees with Trazo4's `mbmode` on 99.63
percent. The rasterize path was kept. Projected cost: 7.5 CPU hours for the 46.2 M field-years.

## Fields under one MODIS pixel

A MODIS cell is 231.656 m on a side, 5.37 ha. The brief's 6.25 ha threshold (250 m square)
marks the low-confidence fields (`small_field` in the NDVI tables). The shares below come
from `area_ha` of the prepared fields. Nationally 16,843,366 of 21,632,817 2020 fields (77.9 percent) and 19,150,697 of 24,554,482 2024 fields (78.0 percent) are under 6.25 ha, so most fields read the NDVI of one or two cells that they share with their neighbors; the coverage weights still give each field the right mix of the cells it touches, but the field-to-field contrast inside a cell is not observable at 250 m.

| state | fields 2020 | under 6.25 ha 2020 | median ha 2020 | fields 2024 | under 6.25 ha 2024 | median ha 2024 |
|---|---|---|---|---|---|---|
| Acre | 132,699 | 67.6% | 2.50 | 172,628 | 70.0% | 2.11 |
| Alagoas | 272,256 | 83.6% | 0.85 | 299,345 | 84.4% | 0.92 |
| Amapa | 4,900 | 55.5% | 4.71 | 8,420 | 66.6% | 2.39 |
| Amazonas | 97,376 | 67.0% | 2.34 | 152,019 | 67.3% | 2.26 |
| Bahia | 1,944,836 | 82.7% | 0.86 | 2,342,495 | 83.5% | 0.86 |
| Ceara | 444,872 | 90.1% | 0.59 | 686,875 | 91.7% | 0.56 |
| Distrito Federal | 29,682 | 85.8% | 0.65 | 33,485 | 87.5% | 0.57 |
| Espirito Santo | 526,382 | 88.7% | 0.65 | 609,809 | 89.8% | 0.57 |
| Goias | 1,166,236 | 60.2% | 3.42 | 1,253,488 | 62.3% | 2.97 |
| Maranhao | 366,820 | 64.2% | 2.54 | 567,125 | 66.1% | 2.28 |
| Mato Grosso | 978,055 | 47.9% | 7.08 | 1,151,506 | 50.4% | 6.09 |
| Mato Grosso Do Sul | 570,226 | 45.2% | 8.81 | 590,173 | 43.6% | 9.63 |
| Minas Gerais | 3,585,336 | 80.5% | 0.97 | 4,078,771 | 81.6% | 0.90 |
| Para | 696,061 | 63.3% | 2.49 | 1,238,196 | 64.9% | 2.50 |
| Paraiba | 429,547 | 92.0% | 0.45 | 511,631 | 92.8% | 0.46 |
| Parana | 1,942,022 | 83.7% | 0.83 | 1,869,028 | 82.8% | 0.88 |
| Pernambuco | 756,224 | 91.2% | 0.55 | 853,306 | 91.4% | 0.58 |
| Piaui | 414,538 | 90.0% | 0.62 | 521,325 | 90.6% | 0.61 |
| Rio Grande Do Norte | 269,089 | 89.0% | 0.59 | 315,440 | 90.2% | 0.56 |
| Rio Grande do Sul | 2,254,809 | 87.1% | 0.57 | 2,345,289 | 86.7% | 0.60 |
| Rio de Janeiro | 239,119 | 82.9% | 0.95 | 269,184 | 83.3% | 0.90 |
| Rondonia | 519,304 | 60.9% | 3.52 | 617,670 | 62.0% | 3.36 |
| Roraima | 43,469 | 58.7% | 3.96 | 66,184 | 64.2% | 2.95 |
| Santa Catarina | 1,433,995 | 94.7% | 0.51 | 1,385,998 | 94.2% | 0.54 |
| Sao Paulo | 1,933,231 | 72.2% | 1.71 | 1,913,933 | 71.7% | 1.81 |
| Sergipe | 181,684 | 83.3% | 0.82 | 220,252 | 84.2% | 0.87 |
| Tocantins | 400,049 | 58.3% | 3.89 | 480,907 | 57.7% | 4.05 |

## Fetch: the shared link and the switch to three files in flight

The single-stream fetch fell from 2.4 MB/s in its first minutes to 0.14 to 0.44 MB/s per file
once another project's Sentinel-2 job took about 8 MB/s of the link, and its own projection
moved from 18:48 to 04:56 the next day. At 16:10 the fetch was stopped (330 files, 4.63 GB
done) and restarted with three files in flight (`--in-flight 3`, a bounded thread pool in
which each thread signs its asset right before the download. The `.part` resume and the
manifest are unchanged, and the stop lost nothing because a file is renamed only when
complete). Aggregate rate after the restart: 0.85 to 0.97 MB/s, each NDVI stream at 0.23 to
0.30 MB/s. At 18:20 it had 530 files and 7.55 GB since the restart, 20 of 46 composites on
disk, and a projected finish of 00:51 on 2026-11-13. A `.part` left by a stop resumes with an
HTTP Range request on the next run. The log of every file is `raw\modis\fetch.log` and the
manifest `raw\modis\manifest.jsonl`.

## Reduce

`s03e_modis_reduce.py watch --workers 2` runs beside the fetch. Every three minutes it
reduces the tile-composites whose raw files and weights exist and writes a partial
(`extracted\modis\partial\year=<YYYY>\<h##v##>\<YYYYDDD>.npz`, float32 `num` and `den`
per weights row), about 1 to 3 s per tile-composite for 0.6 to 2.2 million rows. When no
expected partial is pending it assembles every state and year, prints one JSON line per
state with the row count, and runs the check below. If the fetch dies, the watcher waits.
Rerunning both commands resumes. Partial assembly for a check is
`s03e_modis_reduce.py assemble --years 2024 --states Mato_Grosso Para --partial`, which
writes tables from whatever composites exist. Delete them before the final assembly, or
pass `--force` to it, because an existing table is otherwise skipped.

## NDVI sanity checks, 20 of 23 composites of 2024 on disk

Run at 18:25 on a partial assembly of Mato Grosso and Pará 2024 (both then removed).

- Mato Grosso soybean (class 39, 116,914 fields): median raw NDVI 0.740 at composite
  2024017 (1 to 16 January), 97.1 percent of fields valid. 0.800 at 2023353. Median season
  peak of the filled series 0.884. Median 19 valid composites of 20.
- Mato Grosso pasture (class 15, 948,056 fields): 0.740 at 2024017, 0.699 at 2023353, peak
  0.812. Temporary crop (41): 0.729 at 2024017, peak 0.813. Sugarcane (20): 0.787, peak 0.844.
- Pará pasture (class 15, 1,196,409 fields): median 0.768 at 2024017 but only 39.1 percent of
  fields had a valid value in that composite. 0.741 at 2023353 (39.0 percent valid), peak
  0.840, median 13 valid composites of 20. Pará soybean (14,596 fields): 0.805 at 2024017
  (31.4 percent valid), peak 0.843.
- The soybean check passes (0.740 is above 0.7). The "pasture in Pará lower" expectation
  does not hold for the January composite: the clear Pará pastures are as green as Mato
  Grosso soybean at that date, and the Pará values are a clear-sky subset. The season peak
  ranks soybean (0.884) above pasture (0.812) in Mato Grosso.
- Valid share per composite in Mato Grosso: 0.94 to 1.00 in the dry months, 0.69 to 0.80 from
  2023353 to 2024097. In Pará: 0.88 to 0.99 from 2023241 to 2023305, then 0.31 to 0.45 from
  2023337 to 2024097 (the Amazon wet season), back to 0.95 to 0.99 in May and June. This is
  the cloud problem METHODS.md section 3 anticipated. At 16 days the Pará wet-season series is
  more interpolation than observation, and `n_valid` has to gate the classes.
- Mato Grosso 2024: 1,151,506 rows, no field without weights, median 5 cells per field,
  median dominant-cell share 0.44. Pará 2024: 1,238,196 rows, 18 fields with no valid
  composite at all, median 4 cells, dominant share 0.57.

## MapBiomas classes: progress

`s03f_mapbiomas_fields.py classes --workers 3` started at 16:25 behind the weights. At
18:21 it had written 17 of 54 state-years. The largest files take 12 to 20 minutes each
(Paraná 2020, 1,942,022 rows, 1,158 s, and Goiás 2020, 1,166,236 rows, 739 s). Agreement of the
modal 2024 class with Trazo4's `mbmode` on 2024 fields: 0.967 (Paraná) to 0.982 (Tocantins).
Share of 2024 fields whose 2020 class is not agricultural: 0.109 in Tocantins. Share of 2020
fields whose 2024 class is not agricultural: 0.022 in Paraná, 0.030 in Goiás. The run log is
`extracted\mapbiomas\run_stdout.log` (UTF-16, as PowerShell wrote it), one JSON line per
state-year with rows, seconds and these shares. Expected to finish around 22:30.

## What is still running and how it ends

At the time of this report (2026-11-12 18:30) three processes run on their own:

1. `s03c_modis_fetch.py --in-flight 3`, projected to finish about 00:51 on 2026-11-13.
2. `s03e_modis_reduce.py watch --workers 2`, which assembles all 54 NDVI tables when the
   fetch is done and prints the per-state row counts and the check to
   `extracted\modis\watch_stdout.log`.
3. `s03f_mapbiomas_fields.py classes --workers 3`, about 22:30.

`logs\run_chain.ps1` started 2 and 3 and logs free memory per stage to `logs\chain.log`.
`logs\mem_sampler.ps1` samples the pipeline's memory every minute to `logs\mem.log` until
the chain ends. If anything dies, the same commands resume: finished files, partials and
state tables are skipped. The per-state row counts of the NDVI tables are not in this
report because the tables do not exist yet. The watcher prints them.

## What failed or was not done

- The Terra composite A2024225 is absent from the Planetary Computer (see above).
- Pasture vigor is null (see above).
- Memory peaked at 19.09 GB against the 16 GB asked for, during the weights stage.
- The fetch took the whole afternoon on the shared link instead of the 4.7 hours its first
  ten files projected.
- Not seen running to the end: the final assembly of the NDVI tables and the last 37
  MapBiomas state-years. Both are the unchanged, resumable commands above.

## MODIS fetch finished, 22:08 on 12 November

The fetch ended with 2,090 files downloaded, 340 skipped and 28.55 GB on disk after 5.97 h.
Composite 2024225 (12 to 27 August 2024) has no Terra item on Planetary Computer for any of
the 18 tiles, and `raw\modis\missing.json` records it. The watcher excluded it from the
pending count but the assembly step did not, so every 2024 state stayed at "waiting".
`assemble_state` now treats a composite recorded in missing.json as absent: its raw column is
NaN and the filled series interpolates across it. All 54 tables exist; the 2024 tables have
22 composites with data and 23 columns.
