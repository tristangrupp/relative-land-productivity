# Pipeline

Numbered stages, one script each. Every stage runs per state and resumes: an output that
exists is skipped unless `--force` is passed. Run every script with the wci_tools Python:

```
"E:\Water\water intelligence\wci_tools\.venv\Scripts\python.exe" pipeline\<script>.py
```

Data lives under `F:\relative-land-productivity-data`. Nothing bulky goes in this repo.

## s01_prepare_fields.py: the field boundaries

Reads the seamfix Trazo4 copy at `E:\trazo4_master_parquet_seamfix` for every Brazil state
and the years 2020 and 2024. For each state and year it keeps the rows whose modal MapBiomas
class is agricultural (codes 39, 15, 19, 41, 20, 40, 62, 21, 18, 46, 47, 48, 35, 9), repairs
the geometries (`shapely.make_valid` on the invalid ones, polygonal part of any
GeometryCollection, Polygon promoted to MultiPolygon, empties dropped), assigns the IBGE
municipality geocode (the seven digit code the Brazilian statistics institute gives each
municipality) from the centroid, and writes
`fields\year=<YYYY>\state=<State>\fields.parquet` as GeoParquet 1.1 with a bbox covering
column named `bbox`.

Columns: `fid`, `layer`, `area_ha`, `mbmode`, `crop_group`, `hansen_loss_year`,
`hansen_loss_frac`, `muni_code`, `state_uf`, `centroid_lon`, `centroid_lat`, `bbox`,
`geometry`. `crop_group` is one of soybean, pasture, temporary_crop, sugarcane, rice, cotton,
mosaic, forest_plantation, agriculture, coffee, citrus, perennial, oil_palm.

Municipalities come from GADM 4.1 level 2, `D:\WRI\LATAM admin units\gadm41_BRA_shp\gadm41_BRA_2.shp`,
whose `CC_2` column is the seven digit IBGE geocode. A centroid outside every municipality of
its state takes the nearest one, and the log counts those rows.

Logs: `fields\logs\<YYYY>_<State>.json` per task (rows in, agricultural, invalid before
make_valid, dropped empty, nearest municipality fallback, rows out, seconds) and
`fields\logs\summary.csv` rebuilt at the end of every run.

Runtime, measured on 2026-11-12 with 4 workers on the 20-core machine: 1 h 19 min wall clock
for all 54 state-year files (55,473,548 source rows, 46,187,299 rows written), 18,926 worker
seconds in total. Throughput depends on polygon size: about 1,600 rows per second per worker on
the large-field states (Mato Grosso 2024 took 818 s for 1.30 million rows, Pará 2024 860 s for
1.55 million) and 4,000 to 7,000 rows per second on the small-field southern states (Rio Grande
do Sul 2024 took 562 s for 3.37 million rows). The slowest file was Minas Gerais 2020, 1,571 s
for 4.00 million rows. Peak memory per worker was 4.4 GB (Minas Gerais), because each
100,000-row row group is processed on its own and only the finished WKB is held.

Resume: rerun the same command. Finished state-year files are skipped. To redo one state:

```
python pipeline\s01_prepare_fields.py --state Para --year 2024 --force
```

## s02_grid.py: the extraction grid and tile index

Defines the extraction grid and lists the tiles that hold fields. The grid is the pixel grid
of the MapBiomas Collection 10 coverage GeoTIFFs the project reads locally,
`s3://wri-datalab-sandbox/trazofields/brazil_coverage_<YYYY>.tif`: EPSG:4326, 154,470 by
146,483 pixels of 0.0002694945852358564 degrees (30 m at the equator), upper left origin
(-74.02099974839176, 5.435705784207225). The constants in `s02_grid.py` are copied from that
header, read with rasterio on 2026-11-12; the 2020 and 2024 files share the grid. Tiles are
1024 by 1024 pixels anchored at that origin and named `r<row>_c<col>`, row 0 at the north edge
and col 0 at the west edge, 151 tile columns by 144 tile rows over the whole raster.

Outputs under `grid\`:

- `grid.json`: crs, pixel size, origin, raster size, tile size, and the tile counts.
- `tiles.parquet`: one row per tile that touches at least one prepared 2020 or 2024 field:
  `tile_id`, `row`, `col`, `bounds`, `states`, `n_fields_2020`, `n_fields_2024`, `tier`,
  `geometry`. Tier is the lowest tier of any state in the tile. Tier 1 is Mato Grosso, Pará,
  Amazonas, Acre, Rondônia, Roraima and Amapá. Tier 2 is Mato Grosso do Sul, Goiás, Tocantins
  and Maranhão. Tier 3 is every other state.
- `field_tiles\year=<YYYY>\<State>.parquet`: `fid`, `tile_id`, `row`, `col` for every tile the
  field's bbox touches. A field on a tile edge appears once per tile.

Runtime, measured on 2026-11-12: 17 s for all 54 state-year files with 4 workers, 47,014,021
field-tile pairs, 8,007 tiles.

Resume: rerun the same command. The script reads back `field_tiles` files that exist instead
of rebuilding them, and rewrites `tiles.parquet` and `grid.json` every time from the
`field_tiles` files present.
