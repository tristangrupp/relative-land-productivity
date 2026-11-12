# NDVI extraction probe on the Planetary Computer

Written 2026-11-12 by the probe agent. NDVI is the normalized difference vegetation index,
(B08 - B04) / (B08 + B04) from Sentinel-2. All numbers below come from
`pipeline/s03_ndvi_tiles.py` reading Sentinel-2 L2A cloud-optimized GeoTIFFs from the
Planetary Computer with odc.stac, and from `pipeline/s03_probe_reduce.py` reducing the
result to fields with exactextract. No Earth Engine is used anywhere under `pipeline/`.

History: a first version of this probe ran on Earth Engine between 12:10 and 12:24 and was
stopped when the user forbade that project. It made 18 computePixels calls (16 completed)
and 19 getInfo calls. Its code and tiles were deleted. Its one clean number, 39 s and
3.58 MB per 30 m monthly tile, is kept here only as a comparison point.

## Environments

`C:\Users\grupp\miniconda3\envs\ftwtools\python.exe` runs the download (odc.stac 0.5.3,
dask, pystac_client, planetary_computer, rasterio 1.5.1, psutil).
`E:\Water\water intelligence\wci_tools\.venv\Scripts\python.exe` runs the reduction
(exactextract 0.3.0, geopandas 1.2, duckdb, scipy) and the weather stage (netCDF4,
rasterio). Nothing was installed into either environment.

## What one tile load does

Tile: 1024 x 1024 pixels on the MapBiomas EPSG:4326 grid as the fields agent defined it in
`F:\relative-land-productivity-data\grid\grid.json` (pixel 0.000269494585236 degrees,
origin -74.000248665368, 5.500114990081524, tile ids `r<row>_c<col>`). The 20 m grid shares
the origin with pixel 2/3 of the 30 m one and its own tile indexing.

Per tile and period: one STAC search on `sentinel-2-l2a` over the tile bbox, then
`odc.stac.load` of B04, B08 and SCL (the scene classification layer) at the tile geobox with `resampling` average for the
bands and nearest for SCL, `groupby="solar_day"`, dask chunks of one solar day, computed
with the threaded scheduler. SCL classes 0, 1, 3, 8, 9, 10, 11 are masked. Pixel values
from processing baseline 04.00 onward (all 2024 scenes) have 1000 subtracted before NDVI,
because Sentinel-2 L2A stores reflectance with a +1000 offset since 25 January 2022 and the
Planetary Computer assets keep it. Without this correction January soybean NDVI near
Sorriso came out at 0.37 instead of 0.68 (pixel median over the tile). The 2020 window has
no offset; the code decides per solar day from `s2:processing_baseline`.

Output per tile and period: `raw\s2\<tile_id>\<period>.tif` (int16, bands ndvi_med and
ndvi_max as NDVI x 10000, nodata -32768) and `raw\s2\<tile_id>\<period>_count.tif` (uint8,
clear observations per pixel). METHODS.md fixes monthly maximum NDVI, which is the second
band.

## Raw measurements

Period "monthly" is 2024-01-01 to 2024-02-01, "16-day" is 2024-01-01 to 2024-01-17. All
loads ran while other Sentinel-2 and DEM downloads from unrelated projects were running on
this machine (visible in Get-CimInstance as `37_fetch_s2_ftwbands.py`, `22_fetch_dem.py`,
`25_tile_inputs.py`), and during the parallel batches the CHIRPS download of this project
was also running. The machine-wide bytes received during a load (psutil) were 0.6 to 9 GB
per load, far above what one tile needs, so they measure the other downloads, not this one.
Bytes read per tile are therefore an estimate: solar days x 3 bands x (1024 x 1.5)^2 pixels
at the 20 m overview x 2 bytes x 0.5 for deflate, which is 7.1 MB per solar day at 30 m and
3.1 MB at 20 m.

Serial loads, 8 dask threads per tile:

| site | tile | res | period | seconds | search s | load s | scenes | solar days | est. MB read | disk MB | zero clear obs share | mean clear obs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Sorriso | r64_c66 | 30 m | monthly | 198.5 | 20.5 | 177.1 | 7 | 7 | 49.5 | 3.26 | 0.0113 | 2.14 |
| Sorriso | r64_c66 | 30 m | monthly | 77.0 | 17.1 | 58.8 | 7 | 7 | 49.5 | 3.32 | 0.0113 | 2.14 |
| Sorriso | r65_c66 | 30 m | monthly | 195.5 | 29.2 | 165.5 | 14 | 7 | 49.5 | 3.31 | 0.0054 | 2.30 |
| Sorriso | r65_c66 | 30 m | 16-day | 103.6 | 11.1 | 91.6 | 8 | 4 | 28.3 | 2.54 | 0.0390 | 1.20 |
| Paragominas | r30_c96 | 30 m | monthly | 219.7 | 19.9 | 198.0 | 56 | 13 | 92.0 | 2.49 | 0.2842 | 1.15 |
| Paragominas | r30_c96 | 30 m | 16-day | 126.8 | 2.3 | 122.7 | 28 | 7 | 49.5 | 2.20 | 0.3481 | 0.95 |
| Humaitá | r47_c39 | 30 m | monthly | 60.1 | 15.1 | 43.9 | 10 | 5 | 35.4 | 2.83 | 0.1248 | 1.40 |
| Humaitá | r47_c39 | 30 m | 16-day | 512.7 | 14.0 | 497.1 | 4 | 2 | 14.2 | 0.50 | 0.8447 | 0.16 |
| Sorriso | r97_c99 | 20 m | monthly | 75.0 | 6.5 | 67.5 | 7 | 7 | 22.0 | 3.27 | 0.0081 | 2.45 |

The two Sorriso r64_c66 rows are the same request: the first ran alone before the probe,
the second ran after the probe had finished and the CHIRPS download was the only other
transfer of this project. The spread (58.8 s against 177.1 s load for the same 49.5 MB)
is the shared network, not the server. The Humaitá 16-day load of 14 MB taking 497 s is
the same effect at its worst. Scenes exceed solar days where two to four MGRS granules
overlap the tile; odc.stac fuses them per day, and a granule is read only where it covers
the tile.

Parallel tiles, 30 m monthly, fresh neighbor tiles, 2 dask threads per tile:

| batch | tiles in flight | tiles | ok | wall seconds | tiles per minute | mean seconds per tile |
|---|---|---|---|---|---|---|
| parallel 4 | 4 | 4 | 4 | 688.6 | 0.35 | 489.8 |
| parallel 8 | 8 | 8 | 5 | 805.7 | 0.37 | 347.2 |

Serial throughput from the monthly rows above is 0.27 to 1.0 tiles per minute (60 to 220 s
per tile), so running 4 or 8 tiles at once bought nothing: the link, not the request rate,
is the limit. Three of the eight parallel tiles failed with "Aborting load due to failure
while reading": their SAS tokens, signed at 17:45Z when the probe started, expired at
18:30Z while the loads were still running. A tile load has to finish inside the token
lifetime; sign immediately before each load and keep loads short.

Files: `F:\relative-land-productivity-data\raw\s2\<tile_id>\2024-01m.tif` and
`2024-01a.tif` with their `_count.tif` pairs for r64_c66, r65_c66, r30_c96, r47_c39, the
20 m pair under `raw\s2_20m\r97_c99`, the parallel-batch tiles r65_c67, r66_c66, r65_c65,
r48_c39, r47_c40, r47_c38 and two more, the log `probe\probe_pc.log`, the records
`probe\measurements_pc.json`. The pre-correction Sorriso pair is kept in
`probe\uncorrected_offset\`. Every tile under `raw\s2` except the re-fetched r64_c66
monthly pair was written before the offset correction and must be re-pulled before use.

## Reduction on the Sorriso tile

`pipeline/s03_probe_reduce.py` on `raw\s2\r64_c66\2024-01m.tif` (the corrected pair).
Fields from the fields agent's layer
`F:\relative-land-productivity-data\fields\year=2024\state=Mato_Grosso\fields.parquet`
through geopandas' GeoParquet bbox filter, agricultural classes only, `shapely.make_valid`.

| step | value |
|---|---|
| fields touching the tile | 1,231 |
| load fields (bbox filter on 1,151,506 rows) | 3.3 s |
| exactextract coverage weights, 1024 x 1024 cells | 6.0 s |
| nonzeros in the weights matrix | 634,817 |
| sparse reduction of 3 bands to per-field means | 0.10 s |
| fields with no valid NDVI pixel in January | 0 |
| per-field median NDVI, soybean (class 39, 655 fields) | 0.568 |
| per-field median NDVI, pasture (class 15, 278 fields) | 0.610 |
| mean clear observations per field | 2.07 |
| max abs difference against exactextract `mean`, 20 random fields, ndvi_med | 1.0e-15 |
| same, ndvi_max | 2.0e-15 |
| same, n_clear | 0.0 |

The sparse product and exactextract agree to machine precision, inside the 1e-6 asked.
Per-field mean = (W @ value where valid) / (W @ valid), so masked pixels drop out of both
numerator and denominator. The weights are
`F:\relative-land-productivity-data\probe\weights_r64_c66.npz` (scipy CSR, fields x cells,
row order in `weights_r64_c66_fields.parquet`), the reduced table
`reduced_r64_c66_2024-01m.parquet`, the numbers `reduce_summary_r64_c66.json`. At 6 s per
1,231 fields the weights for all 46 million field-years are about 60 hours of one CPU core,
once per grid; the reduction itself is negligible against the download.

## Tiles touching agricultural fields

From the seamfix `geom_bbox` of agricultural fields (classes 39, 15, 19, 41, 20, 40, 62, 21,
18, 46, 47, 48, 35, 9) in 2020 and 2024 together, counting every 1024-px tile that a bbox
corner falls in (`F:\relative-land-productivity-data\probe\tile_counts.csv`, per state).
Counted on the asset-origin grid before grid.json existed; the two grids differ by a whole
number of pixels (76 columns, 350 rows), so the counts shift by at most one tile per
state edge.

| region | fields 2020 + 2024 | 30 m tiles | 20 m tiles |
|---|---|---|---|
| Mato Grosso | 2,129,561 | 1,008 | 2,160 |
| Pará | 1,934,257 | 988 | 1,961 |
| Amazonas | 249,395 | 847 | 1,386 |
| Acre | 305,327 | 179 | 343 |
| Rondônia | 1,136,974 | 271 | 543 |
| Roraima | 109,653 | 167 | 297 |
| Amapá | 13,320 | 76 | 129 |
| tier 1 | 5,878,487 | 3,536 | 6,819 |
| tier 2 (MS, GO, TO, MA) | 5,395,024 | 1,664 | 3,524 |
| all Brazil | 46,187,299 | 8,925 | 18,205 |

## Cost projection

Inputs, each from the tables above:

- Throughput: 0.37 tiles per minute measured with 8 tiles in flight (22 tiles per hour),
  and 0.78 tiles per minute for the best single load seen (77 s, 47 tiles per hour). Both
  were measured on a link shared with other downloads; a dedicated link was not available.
- 16-day loads took 0.53 to 0.58 of the monthly time on the same tile (Sorriso,
  Paragominas), so a 16-day composite costs 0.55 of a monthly one and there are 46 of them
  in two 12-month windows against 24 monthly.
- A 20 m tile took the same time as a 30 m tile (75 s against 77 s, same 7 solar days) and
  there are 1.93 to 2.04 times as many of them.
- Disk: 3.0 MB per 30 m monthly tile pair, 2.0 MB per 16-day pair, 3.3 and 2.2 MB at 20 m.

| region | res | cadence | tile loads | hours at 22 per hour (measured) | hours at 47 per hour (best seen) | disk GB |
|---|---|---|---|---|---|---|
| tier 1 | 30 m | monthly | 84,864 | 3,820 | 1,810 | 255 |
| tier 1 | 30 m | 16-day | 162,656 | 4,070 | 1,910 | 325 |
| tier 1 | 20 m | monthly | 163,656 | 7,370 | 3,500 | 540 |
| tier 1 | 20 m | 16-day | 313,674 | 7,770 | 3,690 | 690 |
| all Brazil | 30 m | monthly | 214,200 | 9,650 | 4,580 | 643 |
| all Brazil | 30 m | 16-day | 410,550 | 10,170 | 4,830 | 821 |
| all Brazil | 20 m | monthly | 436,920 | 19,680 | 9,340 | 1,442 |
| all Brazil | 20 m | 16-day | 837,430 | 20,750 | 9,840 | 1,842 |

Forty-eight hours at the measured rate is about 1,070 tile loads, at the best seen rate
about 2,250: 44 to 94 tiles over 24 monthly composites, roughly one municipality. Tier 1 at
30 m monthly is 38 to 80 times that budget on this path. The 20 m and 16-day options double
the cost again and buy nothing the methods need (median field 2.1 ha is 23 pixels at 30 m).

What would change the arithmetic, none of it measured here: a link not shared with the
other projects' downloads (the one quiet load ran 3 times faster than the loaded ones);
loading only the three or four least cloudy scenes per month instead of every scene
(Paragominas reads 13 solar days for 1.15 clear observations per pixel); and reading at
the 60 m overview for a first pass. The disk column fits F: for tier 1 at either cadence
at 30 m only if tiles are reduced to fields and deleted as they land, which the 0.1 s
reduction makes cheap.

## Weather

`pipeline/s03b_weather.py`, wci_tools venv. Finished 2026-11-12 14:15 after two concurrent
instances (years 2015 to 2024 and 2021 to 2024; the script skips files that exist and writes
atomically). All 360 files are on disk, 371 MB in total, no failed month.

| variable | files | grid | pixels | bounds | units | MB |
|---|---|---|---|---|---|---|
| `weather\chirps\YYYY-MM.tif` | 120 | 0.05 degree | 800 x 790 | -74.0, -34.0, -34.0, 5.5 | mm per month | 201 |
| `weather\tmax\YYYY-MM.tif` | 120 | 1/24 degree | 964 x 952 | -74.083, -34.083, -33.917, 5.583 | degrees C | 87 |
| `weather\tmin\YYYY-MM.tif` | 120 | 1/24 degree | 964 x 952 | same | degrees C | 83 |

Precipitation: CHIRPS v2.0 monthly from
`https://data.chc.ucsb.edu/products/CHIRPS/v2.0/global_monthly/tifs/chirps-v2.0.YYYY.MM.tif.gz`
(the path is `CHIRPS/v2.0`; `CHIRPS-2.0` returns 404), one file at a time with backoff
because the server answers 429 to bursts, clipped on write to the Brazil bbox snapped to the
grid, float32, nodata -9999. 120 months took 2,044 s in the 2021 to 2024 instance (about
50 s per 20 MB global file on the shared link). The 5.35 GB
`D:\moisture-tracking\reference\chirps\chirps-v2.0.monthly.nc` on disk does not open
(NetCDF: HDF error), so it was not used.

Temperature: TerraClimate tmax and tmin from the Idaho THREDDS NetCDF subset service
(`http://thredds.northwestknowledge.net:8080/thredds/ncss/TERRACLIMATE_ALL/data/TerraClimate_<var>_<year>.nc`
with the Brazil bbox and a one-year time range; about 22 MB of netCDF-3 per request, 6 to
20 s each), split into monthly GeoTIFFs. netCDF4 applies the packing (int16, scale_factor
0.01, add_offset -99) on read. Sources that do not work for 2024: the Planetary Computer
`terraclimate` collection ends 2021-12 and `era5-pds` has no items after 2020; the AWS
`era5-pds` bucket refuses anonymous reads (403); `climate.northwestknowledge.net` refuses
connections. NASA POWER was not needed.

Verification, June 2024:

| variable | reference | pixels | result |
|---|---|---|---|
| chirps | the global tif.gz fetched again, same pixel | 4 | all abs_diff 0.0 (values 3.33 to 6.66 mm) |
| tmax | full `TerraClimate_tmax_2024.nc` from the server's file service (97 MB) | 4 | all abs_diff 0.0 (24.8 to 34.2 C) |
| tmin | full `TerraClimate_tmin_2024.nc` (97 MB) | 4 | 3 land pixels abs_diff 0.0 (-1.9 to 22.4 C), 1 ocean pixel nodata on both sides |

The script's own `--verify` first compared tmax and tmin with the THREDDS point service and
saw 13500 against 36.0: that service returns the packed int16 (13500 x 0.01 - 99 = 36.0).
The verifier now unpacks it. Logs: `weather\download_pc.log`,
`weather\download_pc_2021_2024.log`, `weather\download_log.json`.
