"""Stage 2: the extraction grid and the tile index.

The extraction grid is the pixel grid of the MapBiomas Collection 10 coverage GeoTIFFs this
project reads locally, s3://wri-datalab-sandbox/trazofields/brazil_coverage_<YYYY>.tif
(public read). Their header, read with rasterio on 2026-11-12 for both 2020 and 2024:
EPSG:4326, 154,470 columns by 146,483 rows, square pixels of 0.0002694945852358564 degrees
(30 m at the equator), upper left origin at longitude -74.02099974839176 and latitude
5.435705784207225, uint8, no overviews. The constants below are copied from that header.

Tiles are 1024 by 1024 pixels anchored at that origin. Tile (row, col) covers raster columns
col*1024 to (col+1)*1024 and raster rows row*1024 to (row+1)*1024, row 0 at the north edge and
col 0 at the west edge, so 151 tile columns by 144 tile rows cover the whole raster. Only tiles
that touch at least one prepared field are listed.

Outputs under F:\\relative-land-productivity-data\\grid\\:
  grid.json                            crs, pixel size, origin, raster size, tile size, tile counts
  tiles.parquet                        one row per tile with a field: tile_id, row, col,
                                       bounds, geometry, states, n_fields_2020, n_fields_2024,
                                       tier (GeoParquet 1.1, bbox covering on "bounds")
  field_tiles\\year=<YYYY>\\<State>.parquet   fid, tile_id, row, col for every tile the
                                       field bbox touches

Inputs are the stage 1 files F:\\relative-land-productivity-data\\fields\\year=<YYYY>\\state=<State>\\fields.parquet.

Usage:
  python pipeline/s02_grid.py                 all prepared states and years, 4 workers
  python pipeline/s02_grid.py --force         rewrite the field_tiles files

field_tiles files that exist are read back rather than rebuilt, so a rerun only costs the
aggregation. tiles.parquet and grid.json are always rewritten from whatever field_tiles exist.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s01_prepare_fields import FIELDS_ROOT, DATA_ROOT, STATES, TIER, YEARS  # noqa: E402

GRID_ROOT = DATA_ROOT / "grid"
FIELD_TILES_ROOT = GRID_ROOT / "field_tiles"

SOURCE_RASTER = "s3://wri-datalab-sandbox/trazofields/brazil_coverage_<YYYY>.tif"
CRS = "EPSG:4326"
PIXEL = 0.0002694945852358564
ORIGIN_X = -74.02099974839176
ORIGIN_Y = 5.435705784207225
RASTER_WIDTH = 154470
RASTER_HEIGHT = 146483
TILE = 1024
TILE_DEG = PIXEL * TILE
N_TILE_COLS = -(-RASTER_WIDTH // TILE)
N_TILE_ROWS = -(-RASTER_HEIGHT // TILE)
KEY_STRIDE = 1_000_000  # row * KEY_STRIDE + col keys a tile; cols never reach this


def tile_id(row: np.ndarray, col: np.ndarray) -> list[str]:
    return [f"r{r}_c{c}" for r, c in zip(row.tolist(), col.tolist())]


def tile_bounds(row: np.ndarray, col: np.ndarray) -> np.ndarray:
    xmin = ORIGIN_X + col * TILE_DEG
    xmax = ORIGIN_X + (col + 1) * TILE_DEG
    ymax = ORIGIN_Y - row * TILE_DEG
    ymin = ORIGIN_Y - (row + 1) * TILE_DEG
    return np.column_stack([xmin, ymin, xmax, ymax])


def fields_path(state: str, year: int) -> Path:
    return FIELDS_ROOT / f"year={year}" / f"state={state}" / "fields.parquet"


def field_tiles_path(state: str, year: int) -> Path:
    return FIELD_TILES_ROOT / f"year={year}" / f"{state}.parquet"


def build_field_tiles(state: str, year: int, force: bool) -> dict:
    """Write the fid to tile mapping for one state and year; return per-tile field counts."""
    t0 = time.time()
    dst = field_tiles_path(state, year)
    if dst.exists() and not force:
        t = pq.ParquetFile(dst).read(columns=["fid", "row", "col"])
        row = t.column("row").to_numpy()
        col = t.column("col").to_numpy()
        n_fields = len(pa.compute.unique(t.column("fid")))
        rebuilt = False
    else:
        t = pq.ParquetFile(fields_path(state, year)).read(columns=["fid", "bbox"])
        fid = t.column("fid").to_numpy()
        b = t.column("bbox").combine_chunks()
        xmin = b.field("xmin").to_numpy()
        ymin = b.field("ymin").to_numpy()
        xmax = b.field("xmax").to_numpy()
        ymax = b.field("ymax").to_numpy()
        c0 = np.floor((xmin - ORIGIN_X) / TILE_DEG).astype(np.int32)
        c1 = np.floor((xmax - ORIGIN_X) / TILE_DEG).astype(np.int32)
        r0 = np.floor((ORIGIN_Y - ymax) / TILE_DEG).astype(np.int32)
        r1 = np.floor((ORIGIN_Y - ymin) / TILE_DEG).astype(np.int32)
        ncols = c1 - c0 + 1
        nrows = r1 - r0 + 1
        n = ncols * nrows
        rep = np.repeat(np.arange(len(fid)), n)
        starts = np.repeat(np.cumsum(n) - n, n)
        k = np.arange(len(rep)) - starts
        nc = ncols[rep]
        row = r0[rep] + k // nc
        col = c0[rep] + k % nc
        n_fields = len(fid)
        out = pa.table({
            "fid": pa.array(fid[rep], pa.int64()),
            "tile_id": pa.array(tile_id(row, col), pa.string()),
            "row": pa.array(row, pa.int32()),
            "col": pa.array(col, pa.int32()),
        })
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(".parquet.tmp")
        pq.write_table(out, tmp, compression="zstd")
        tmp.replace(dst)
        rebuilt = True
    key = row.astype(np.int64) * KEY_STRIDE + col.astype(np.int64)
    uniq, counts = np.unique(key, return_counts=True)
    outside = int(((row < 0) | (col < 0) | (row >= N_TILE_ROWS) | (col >= N_TILE_COLS)).sum())
    return {
        "state": state, "year": year, "n_fields": int(n_fields), "n_pairs": int(len(row)),
        "tile_keys": uniq, "tile_counts": counts, "outside_raster": outside,
        "rebuilt": rebuilt, "seconds": round(time.time() - t0, 1),
    }


def geo_metadata(bbox: list[float]) -> bytes:
    from pyproj import CRS as PCRS

    meta = {
        "version": "1.1.0",
        "primary_column": "geometry",
        "columns": {"geometry": {
            "encoding": "WKB",
            "geometry_types": ["Polygon"],
            "crs": PCRS.from_epsg(4326).to_json_dict(),
            "bbox": bbox,
            "covering": {"bbox": {
                "xmin": ["bounds", "xmin"], "ymin": ["bounds", "ymin"],
                "xmax": ["bounds", "xmax"], "ymax": ["bounds", "ymax"],
            }},
        }},
        "creator": {"library": "relative-land-productivity/pipeline/s02_grid.py"},
    }
    return json.dumps(meta).encode()


def write_tiles(results: list[dict]) -> dict:
    per_tile: dict[int, dict] = {}
    for r in results:
        for key, cnt in zip(r["tile_keys"].tolist(), r["tile_counts"].tolist()):
            d = per_tile.setdefault(key, {"states": set(), 2020: 0, 2024: 0})
            d["states"].add(r["state"])
            d[r["year"]] += cnt
    keys = np.array(sorted(per_tile), dtype=np.int64)
    row = (keys // KEY_STRIDE).astype(np.int32)
    col = (keys % KEY_STRIDE).astype(np.int32)
    bounds = tile_bounds(row, col)
    states = [sorted(per_tile[k]["states"]) for k in keys.tolist()]
    tier = np.array([min(TIER.get(s, 3) for s in ss) for ss in states], dtype=np.int8)
    n2020 = np.array([per_tile[k][2020] for k in keys.tolist()], dtype=np.int64)
    n2024 = np.array([per_tile[k][2024] for k in keys.tolist()], dtype=np.int64)
    geoms = shapely.box(bounds[:, 0], bounds[:, 1], bounds[:, 2], bounds[:, 3])
    table = pa.table({
        "tile_id": pa.array(tile_id(row, col), pa.string()),
        "row": pa.array(row, pa.int32()),
        "col": pa.array(col, pa.int32()),
        "bounds": pa.StructArray.from_arrays(
            [pa.array(bounds[:, i], pa.float64()) for i in range(4)], names=["xmin", "ymin", "xmax", "ymax"]),
        "states": pa.array(states, pa.list_(pa.string())),
        "n_fields_2020": pa.array(n2020, pa.int64()),
        "n_fields_2024": pa.array(n2024, pa.int64()),
        "tier": pa.array(tier, pa.int8()),
        "geometry": pa.array(shapely.to_wkb(geoms), pa.binary()),
    })
    bbox = [float(bounds[:, 0].min()), float(bounds[:, 1].min()), float(bounds[:, 2].max()), float(bounds[:, 3].max())]
    table = table.replace_schema_metadata({b"geo": geo_metadata(bbox)})
    pq.write_table(table, GRID_ROOT / "tiles.parquet", compression="zstd")
    counts = {int(t): int((tier == t).sum()) for t in (1, 2, 3)}
    return {"tiles_total": int(len(keys)), "tiles_per_tier": counts, "bbox": bbox,
            "tile_rows": [int(row.min()), int(row.max())], "tile_cols": [int(col.min()), int(col.max())]}


def write_grid_json(summary: dict) -> None:
    grid = {
        "crs": CRS,
        "pixel_size_deg": PIXEL,
        "origin": [ORIGIN_X, ORIGIN_Y],
        "origin_corner": "upper left",
        "transform": [PIXEL, 0, ORIGIN_X, 0, -PIXEL, ORIGIN_Y],
        "raster_width_px": RASTER_WIDTH,
        "raster_height_px": RASTER_HEIGHT,
        "tile_size_px": TILE,
        "tile_size_deg": TILE_DEG,
        "n_tile_cols": N_TILE_COLS,
        "n_tile_rows": N_TILE_ROWS,
        "tile_id_format": "r<row>_c<col>, row 0 at the north edge, col 0 at the west edge",
        "tile_bounds_formula": {
            "xmin": "origin_x + col * tile_size_deg", "xmax": "origin_x + (col + 1) * tile_size_deg",
            "ymax": "origin_y - row * tile_size_deg", "ymin": "origin_y - (row + 1) * tile_size_deg",
        },
        "source": SOURCE_RASTER,
        "source_note": "MapBiomas Collection 10 coverage GeoTIFF header, read with rasterio on 2026-11-12; "
                       "2020 and 2024 share this grid",
        "tiles_with_fields": summary,
    }
    (GRID_ROOT / "grid.json").write_text(json.dumps(grid, indent=1))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int, action="append", choices=YEARS)
    ap.add_argument("--state", action="append", choices=sorted(STATES))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--force", action="store_true", help="rewrite field_tiles files that exist")
    args = ap.parse_args(argv)

    years = args.year or list(YEARS)
    states = args.state or sorted(STATES)
    tasks = [(s, y) for s in states for y in years if fields_path(s, y).exists()]
    missing = [(s, y) for s in states for y in years if not fields_path(s, y).exists()]
    if missing:
        print(f"no stage 1 output for {len(missing)} tasks, skipped: {missing}", flush=True)
    print(f"{len(tasks)} tasks, {args.workers} workers", flush=True)
    print(f"grid: pixel {PIXEL!r} deg, origin ({ORIGIN_X!r}, {ORIGIN_Y!r}), tile {TILE} px", flush=True)
    GRID_ROOT.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(build_field_tiles, s, y, args.force): (s, y) for s, y in tasks}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            print(f"{r['state']} {r['year']}: {r['n_fields']:,} fields, {r['n_pairs']:,} field-tile pairs, "
                  f"{len(r['tile_keys'])} tiles, outside raster {r['outside_raster']}, "
                  f"{'built' if r['rebuilt'] else 'read'} in {r['seconds']} s", flush=True)
    summary = write_tiles(results)
    summary["n_states_years"] = len(results)
    summary["field_tile_pairs"] = int(sum(r["n_pairs"] for r in results))
    write_grid_json(summary)
    print(json.dumps(summary, indent=1))
    print(f"done in {time.time() - t0:.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
