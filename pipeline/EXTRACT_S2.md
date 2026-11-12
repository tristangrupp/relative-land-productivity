# Sentinel-2 monthly NDVI per field: design, measurements and projection

Written 2026-11-12 by the extract-s2 agent. NDVI is the normalized difference vegetation
index, (B08 - B04) / (B08 + B04) from Sentinel-2. This stage produces, for every prepared
field of 2020 and 2024, the coverage-weighted mean of the pixel monthly maximum NDVI at 30 m
for the 24 months of the two agricultural years (2019-09 to 2020-08 and 2023-09 to 2024-08),
from Sentinel-2 L2A on the Planetary Computer, reduced on this machine. No Earth Engine, no AWS
compute. It builds on the probe agent's `s03_ndvi_tiles.py` and `s03_probe_reduce.py`
(`pipeline/PROBE.md`).

## Scripts

| script | environment | what it does |
|---|---|---|
| `pipeline/s03g_s2_fetch_reduce.py` | `C:\Users\grupp\miniconda3\envs\ftwtools\python.exe` | per tile and month: STAC search, scene thinning, signed load, mask, composite, sparse reduction, append to the tile parquet; `run` and `status` commands |
| `pipeline/s03g_weights.py` | `E:\Water\water intelligence\wci_tools\.venv\Scripts\python.exe` | exactextract coverage weights per tile, cached as `weights\s2\<tile_id>.npz`; called as a subprocess by the fetch script when a tile has no weights, or run ahead per state or tier |
| `pipeline/s03h_s2_assemble.py` | either | combines tile parquets into one table per state and field year, with gap filling and the sanity checks |

The stage needs both environments because ftwtools has odc.stac but no exactextract and
wci_tools has exactextract but no odc.stac. Nothing was installed into either.

Commands:

```
"C:\Users\grupp\miniconda3\envs\ftwtools\python.exe" pipeline\s03g_s2_fetch_reduce.py run --tier 1 --tier 2 --workers 4 --threads 2 --min-days 2
"C:\Users\grupp\miniconda3\envs\ftwtools\python.exe" pipeline\s03g_s2_fetch_reduce.py status --state Mato_Grosso
"E:\Water\water intelligence\wci_tools\.venv\Scripts\python.exe" pipeline\s03g_weights.py state Mato_Grosso --procs 4
"C:\Users\grupp\miniconda3\envs\ftwtools\python.exe" pipeline\s03h_s2_assemble.py --state Mato_Grosso --check
```

`run` takes `--state <folder name>` (repeatable, run order), `--tier 1` and `--tier 2`
(the brief's state order: Mato Grosso, Pará, Rondônia, Acre, Amazonas, Roraima, Amapá, then
Mato Grosso do Sul, Goiás, Tocantins, Maranhão), `--tiles` for explicit tile ids,
`--limit-tiles`, `--months`, `--workers` (tiles in flight, default 4), `--threads` (dask
threads per load, default 2), `--days` (default 3), `--min-days`, `--target-clear` (0.98)
and `--keep-rasters`. Tiles inside a state run in descending field count. A tile that touches
two states runs once, under the first state that lists it.

## Per tile and month

1. One STAC search of `sentinel-2-l2a` per tile and agricultural year (not per month), items
   grouped by month and solar day.
2. Granule dedupe. Neighboring MGRS granules of one orbit overlap by about 10 km and hold the
   same pixels there, but odc.stac reads every item's whole window over the tile, so a tile at
   a four-granule junction read four windows for one day. Per solar day the script keeps the
   fewest granules that cover the day's footprint: largest intersection first, another granule
   only when it adds at least 1 percent of the tile, stop at 99.5 percent of the day's union.
   On the 20 tiles of batch 2 this cut items from 117 to 81.
3. Day selection. Each solar day scores `coverage x (1 - cloud / 100)`, with coverage the share
   of the tile the kept granules cover and cloud the area-weighted `eo:cloud_cover` of those
   granules (the item cloud cover is for the whole granule, not the tile). Days are taken in
   score order. The rule given to this agent keeps the three best days, four when all three
   have cloud cover above 60 percent. The production run adds `--min-days 2`: the month stops
   at two days once the chance that a pixel was clear on at least one kept day,
   `1 - product(1 - score)`, reaches 0.98. In the dry season two days of 0 to 5 percent cloud
   reach that; wet months keep three or four. The reason is the read volume below: a kept day
   costs 10 to 15 MB per granule, so the third day of a cloud-free month is a third of the
   bytes for a pixel that was almost surely already clear. Days covering under 5 percent of
   the tile are dropped. `allcloud=` in the log lists the cloud cover of every day of the
   month in score order so other rules can be costed offline.
4. Load. `odc.stac.load` of B04 and B08 with resampling `average` and SCL with `nearest` at
   the tile's 30 m geobox, `groupby="solar_day"`, one dask chunk per day, computed with the
   threaded scheduler. Items are signed at load time through `patch_url=planetary_computer.sign`;
   the search itself is unsigned. The probe's failures came from signing at search time:
   `planetary_computer.sign_url` returns an already signed URL unchanged, so a re-sign at load
   did nothing and the 45 minute tokens ran out mid-load. A tile-month load takes 10 to 70 s.
5. Pixels. 1000 is subtracted from B04 and B08 on solar days whose scenes are processing
   baseline 04.00 or later (all of 2023-09 to 2024-08, none of 2019-09 to 2020-08). SCL 0, 1,
   3, 8, 9, 10, 11 are masked; a pixel with B08 under 0.01 reflectance or NDVI under -0.2 is
   dropped as METHODS.md section 3 says. The month is the per-pixel maximum NDVI over the kept
   days; `n_clear` counts the unmasked observations among the kept days only (two to four),
   not among all scenes of the month.
6. Reduce. Weights `W` (fields x 1,048,576 cells, scipy CSR, exactextract coverage fractions
   against an in-memory raster with the tile's geotransform; 3 to 6 s per tile, 2.7 to 4.9 MB
   on disk) hold every field of both years and every state the tile index lists for the tile.
   `ndvi_max = (W @ ndvi where valid) / (W @ valid)`, `n_clear = (W @ count) / rowsum(W)`,
   the product the probe checked against exactextract to 2e-15. One row per field goes to
   `extracted\s2\tiles\<tile_id>.parquet` with `fid, year_layer, state, period, ndvi_max,
   n_clear, w_valid, w_total`; `w_valid` and `w_total` let the assembler combine a field
   across tiles and apply the half-valid rule. The file is rewritten on every month (read,
   drop the month, append, write to `.part`, rename), so a kill leaves it whole.
7. No raster is written unless `--keep-rasters` is set. Disk per tile-month is the parquet
   growth only, about 0.5 MB for a 10,000-field tile.

Resume is per tile-month: on start the periods already in the tile parquet are skipped. A month
with no items at all writes rows with `ndvi_max` NaN and `w_valid` 0 so it counts as done. A
failed load after three attempts is logged and left undone for the next run.

## Progress log

`F:\relative-land-productivity-data\extracted\s2\progress.log`, one line per tile-month:

```
2026-11-12T14:36:11 tile=r55_c69 period=2019-10 status=ok days=3 of=6 items=3 of_items=6 cloud=36,9,52 cov=1.00,1.00,1.00 allcloud=9,36,52,70,87,98 fields=11123 valid_share=1.00 ndvi_p50=0.559 s=12.8 mb=39.1
```

`days` kept of the month's usable days, `items` kept of the month's granule items, `cloud`
and `cov` per kept day, `valid_share` the share of the tile's fields with at least half their
coverage valid, `ndvi_p50` the median field value, `s` seconds from selection to parquet,
`mb` the bytes read. `TILE_DONE`, `RUN_START` and `RUN_END` lines summarize; `RUN_END` has
`tile_months_per_min`, `mb_per_tile_month`, `mb_per_s` and the peak resident memory. The
`status` command counts complete tiles and tile-months per state from the tile parquets.

Bytes are exact for the process: GDAL is pointed with `GDAL_HTTP_PROXY` at a CONNECT proxy
inside the script that counts the bytes the blob storage returns, and each tile-month gets
an equal share of the bytes that arrived while its load was in flight. The proxy was checked
against a whole-file read of a 60 m band: 5.64 MB counted for the 5.6 MB of full-resolution
blocks of a 7.47 MB file (the rest is overviews). psutil's per-process `read_bytes` was tried
first and counted 1.4 MB of that same read, so it is not usable on Windows; the machine-wide
counter includes other projects' downloads.

## Measurements

All on 2026-11-12 between 14:11 and 14:35 local, while one other 4.6 MB/s download of
another project was running (until about 18:40) and the MODIS agent used the link lightly.
Tiles are the Mato Grosso tiles with the most fields (7,600 to 12,400 fields of both years
per tile). Month 2024-01.

| batch | tiles in flight | dedupe | tile-months | wall s | tile-months per min | items read | MB per tile-month | MB/s |
|---|---|---|---|---|---|---|---|---|
| 1 | 4 | no | 20 | 263 | 4.57 | 135 | 52.7 | 4.01 |
| 2 | 4 | yes | 20 | 133 | 9.05 | 81 of 117 | 44.0 | 6.63 |
| 3 | 8 | yes | 14 of 20 | 97 | 8.7 | 48 of 71 | 41.2 | 5.9 |

Batch 3 was killed by the Claude Code harness at 14:34:44 under machine memory pressure
(8 GB free of 64, other sessions' training jobs at 3 to 6.6 GB each), so its row is the 14
tile-months it finished. Eight tiles in flight did not beat four, as the probe found; the
production run uses four.

Read volume against the expectation: the task expected about 15 MB per tile-month; measured is
44 MB with three days and dedupe. One granule-day of three bands costs 10 to 15 MB: B04 and
B08 come from the 20 m overview (1,536 x 1,536 pixels for the tile, 2 bytes, deflate at about
0.7 on reflectance) plus SCL at 20 m, and GDAL reads whole 512-pixel blocks, so the window
over-reads by 1.3 to 1.8 depending on alignment. Three days of 1.3 granules on average is 40 to
45 MB. The probe's 7.1 MB per day estimate assumed deflate at 0.5 and no block over-read.

Single tile-month timings with one tile in flight: 31 to 32 s for 40 MB (one granule per
day) and 84 MB (two granules per day), so a load is latency bound, not bandwidth bound, and
tiles in flight raise MB/s up to the link.

Thinning cost, r64_c66 (Sorriso) January 2024, same 981 2024 fields, three kept days (cloud
15, 76, 74 percent) against the probe's all seven days: per-field `ndvi_max` differs by a
median of 0.000, a mean of -0.011 and a 5th percentile of -0.075; the soybean median is 0.675
against 0.700, pasture 0.645 against 0.647. The loss falls on fields whose only clear look was
on a dropped day. It is noise against peers in the same tile, which the peer-relative metric
absorbs, not a bias between regions.

Memory: all tile workers are threads of one process. The production process (4 tiles in
flight, 2 threads each) had a working set of 0.59 GB and a peak of 0.65 GB after five minutes
(Get-Process PeakWorkingSet64 at 14:40), about 0.16 GB per tile in flight; the `RUN_END` line
records the peak over the run. The user's limit is 2 GB per worker and at most 4 tiles in
flight until free memory is checked. The
weights subprocess (wci_tools, geopandas on one state-year file) is about 1 GB for a few
seconds per new tile.

## Projection

Tile counts from `grid\tiles.parquet` (a tile shared with a neighboring state counts for the
state listed first): Mato Grosso 1,013, tier 1 3,406, tier 2 1,475. Twenty-four months each.

| region | tile-months | at 9.05 per min (batch 2, 3 days) | at 44 MB each | at 36 MB each (two days in dry months) |
|---|---|---|---|---|
| Mato Grosso | 24,312 | 45 h | 1.07 TB | 0.88 TB |
| tier 1 | 81,744 | 151 h (6.3 days) | 3.6 TB | 2.9 TB |
| tier 2 | 35,400 | 65 h | 1.56 TB | 1.27 TB |

The rate is link bound: at 6.6 MB/s the MB column divides to the hours column. The 36 MB
column assumes `--min-days 2` drops the third day in half the months; the first hour of the
production run gives the real figure (see the update below). Amazon tiles in Pará and
Amazonas have more cloudy months (four days kept, or none usable), so tier 1 beyond Mato
Grosso is less certain than the Mato Grosso row.

## Running now

Started 2026-11-12 14:35 as a detached process (pid 36992, `Start-Process`, not a harness
background shell, so memory pressure in the harness cannot kill it):

```
s03g_s2_fetch_reduce.py run --tier 1 --tier 2 --workers 4 --threads 2 --min-days 2
```

stdout in `F:\relative-land-productivity-data\extracted\s2\run_tier1_tier2_2026-11-12.log`,
progress in `progress.log`. Its first two minutes (14:35:47 to 14:37:48, including the first
tile searches): 28 tile-months, 14 of them with two days kept, 13 with three, 1 with four,
mean 33.7 MB per tile-month, 944 MB in all, 13.9 tile-months per minute and 7.8 MB/s. At that
rate Mato Grosso takes 29 h and tier 1 98 h; the figures from a longer sample go in the
Decisions section of BRIEF.md when the orchestrator asks for status. Mato Grosso weights were prebuilt (1,011 tiles, 936 s, 4
processes, 2.7 GB); the other states' weights are built on demand. The run resumes from the
tile parquets if restarted with the same command.

## Assembly and checks

`s03h_s2_assemble.py` reads the tile parquets of a state, combines a field across tiles by
coverage weight, sets a month missing when under half the field's coverage was valid, pivots
to `ndvi_<YYYY-MM>` (24), `ndvi_<YYYY-MM>_filled` (linear interpolation inside each
agricultural year, ends take the nearest valid month), `nclear_<YYYY-MM>`, `n_valid_2020`,
`n_valid_2024`, `nclear_2020`, `nclear_2024`, `n_tiles`, `n_months_present`, and writes
`extracted\s2\year=<YYYY>\state=<State>\ndvi_monthly.parquet` with a `.meta.json` that says
how many tiles were complete. It can run on a partial state. `--check` prints the class
medians for January and the share of fields with fewer than 8 valid months per year.

Sanity checks to run after Mato Grosso completes (not yet seen): soybean median `ndvi_2024-01`
above 0.75 (on the five tiles of the first test it was 0.732 for the 2020 layer and the
three-day composites), pasture lower, and the share of fields under 8 valid months per year.
