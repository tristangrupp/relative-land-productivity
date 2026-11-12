"""Stage 3d: exactextract coverage weights of every prepared field on the MODIS 250 m grid.

For each MODIS sinusoidal tile that touches a prepared field (raw\\modis\\tiles_needed.json,
written by s03c_modis_fetch.py) and each agricultural year (2020, 2024), this stage reads the
prepared fields of every state whose bbox overlaps the tile footprint, reprojects them from
EPSG:4326 to the MODIS sinusoidal projection (sphere of radius 6371007.181 m,
"+proj=sinu +R=6371007.181"), and computes with exactextract the fraction of each 231.656 m
cell covered by each field. The cells are those of the 4800 x 4800 tile, numbered row-major
from the upper left corner, the same order rasterio returns when it reads a MODIS GeoTIFF of
that tile.

Outputs, under F:\\relative-land-productivity-data\\weights\\modis\\year=<YYYY>\\:

  <h##v##>.npz             scipy CSR matrix, fields x 23,040,000 cells, values are coverage
                           fractions (0 to 1 of the cell), float32
  <h##v##>_fields.parquet  one row per matrix row: fid, state, area_ha, mbmode, crop_group,
                           n_cells (cells with nonzero coverage in this tile), w_sum (sum of
                           coverage fractions in this tile, in cells), w_max (largest
                           coverage fraction), dominant_share (w_max / w_sum, the share of
                           the field's area in this tile that lies in its dominant cell),
                           area_ratio (w_sum x cell area / area_ha, which is 1 for a field
                           fully inside the tile because both projections are equal area)

A field that spans two MODIS tiles appears in both files with the part of its area that lies
in each; the reduce stage sums numerators and denominators across tiles. A field whose bbox
touches the footprint but whose polygon lies outside the tile gets no row.

The fields are read in batches of 50,000 rows through pyarrow with a filter on the GeoParquet
bbox column, so memory per worker stays near 1 to 2 GB. Tasks (tile, year) run in parallel
with --workers processes. A task whose two outputs exist is skipped. Timing per task goes to
weights\\modis\\timing.jsonl.

Environment: E:\\Water\\water intelligence\\wci_tools\\.venv (exactextract 0.3, geopandas, pyproj,
scipy). No Earth Engine.

Usage:
  python s03d_modis_weights.py [--workers 6] [--years 2024 2020] [--tiles h12v10 ...] [--force]
  python s03d_modis_weights.py --check h12v10 --year 2024     compare 25 fields against exactextract mean
"""
import argparse
import glob
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime

DATA = r"F:\relative-land-productivity-data"
RAW = os.path.join(DATA, "raw", "modis")
FIELDS = os.path.join(DATA, "fields")
WEIGHTS = os.path.join(DATA, "weights", "modis")
TEMPLATES = os.path.join(WEIGHTS, "templates")
TILES_NEEDED = os.path.join(RAW, "tiles_needed.json")
TIMING = os.path.join(WEIGHTS, "timing.jsonl")
N = 4800
BATCH = 50_000
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s03c_modis_fetch import PIX_M, SINU_PROJ, tile_transform  # noqa: E402

CELL_HA = PIX_M * PIX_M / 10_000.0          # 5.3665 ha


def template_path(hv):
    """A 4800 x 4800 uint8 GeoTIFF of zeros on the tile's grid, made once; exactextract reads its grid."""
    import numpy as np
    import rasterio
    from rasterio.crs import CRS
    os.makedirs(TEMPLATES, exist_ok=True)
    p = os.path.join(TEMPLATES, f"{hv}.tif")
    if os.path.exists(p):
        return p
    h, v = int(hv[1:3]), int(hv[4:6])
    tmp = p + ".part"
    with rasterio.open(tmp, "w", driver="GTiff", width=N, height=N, count=1, dtype="uint8",
                       crs=CRS.from_proj4(SINU_PROJ), transform=tile_transform(h, v),
                       compress="deflate", tiled=True, blockxsize=512, blockysize=512, sparse_ok=True) as dst:
        dst.write(np.zeros((N, N), dtype="uint8"), 1)
    os.replace(tmp, p)
    return p


def states_for(tile, year):
    return [s for s in tile["states"] if os.path.exists(os.path.join(FIELDS, f"year={year}", f"state={s}", "fields.parquet"))]


def iter_field_batches(path, bounds):
    """Batches of (fid, state_uf, area_ha, mbmode, crop_group, geometry WKB) whose bbox overlaps bounds."""
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    x0, y0, x1, y1 = bounds
    f = pc.field
    expr = (f(("bbox", "xmin")) < x1) & (f(("bbox", "xmax")) > x0) & (f(("bbox", "ymin")) < y1) & (f(("bbox", "ymax")) > y0)
    dset = ds.dataset(path, format="parquet")
    cols = ["fid", "area_ha", "mbmode", "crop_group", "geometry"]
    for b in dset.to_batches(columns=cols, filter=expr, batch_size=BATCH, batch_readahead=1, fragment_readahead=1):
        if b.num_rows:
            yield b


def build_tile(tile, year, force=False):
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import pyproj
    import scipy.sparse as sp
    import shapely
    from exactextract import exact_extract
    hv = tile["hv"]
    out_dir = os.path.join(WEIGHTS, f"year={year}")
    os.makedirs(out_dir, exist_ok=True)
    p_npz = os.path.join(out_dir, f"{hv}.npz")
    p_fields = os.path.join(out_dir, f"{hv}_fields.parquet")
    if os.path.exists(p_npz) and os.path.exists(p_fields) and not force:
        return {"hv": hv, "year": year, "status": "skip"}
    t0 = time.time()
    tmpl = template_path(hv)
    footprint = shapely.from_wkt(tile["footprint_4326_wkt"])
    bounds = tile["bounds_4326"]
    tr = pyproj.Transformer.from_crs("EPSG:4326", pyproj.CRS.from_proj4(SINU_PROJ), always_xy=True)

    def to_sinu(coords):
        x, y = tr.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([x, y])

    counts, cols, vals = [], [], []            # CSR pieces: nonzeros per row, then column ids and values
    meta = []
    n_rows = 0
    n_read = 0
    for state in states_for(tile, year):
        path = os.path.join(FIELDS, f"year={year}", f"state={state}", "fields.parquet")
        for b in iter_field_batches(path, bounds):
            n_read += b.num_rows
            geoms = shapely.from_wkb(b.column("geometry").to_numpy(zero_copy_only=False))
            # drop fields whose polygon misses the (densified) footprint
            keep = shapely.intersects(geoms, footprint)
            if not keep.any():
                continue
            geoms = geoms[keep]
            sub = b.filter(keep).to_pandas()
            geoms_s = shapely.transform(geoms, to_sinu)
            gdf = gpd.GeoDataFrame({"i": np.arange(len(geoms_s))}, geometry=geoms_s, crs=pyproj.CRS.from_proj4(SINU_PROJ))
            res = exact_extract(tmpl, gdf, ["cell_id", "coverage"], output="pandas", progress=False)
            cid_col = [c for c in res.columns if c.endswith("cell_id")][0]
            cov_col = [c for c in res.columns if c.endswith("coverage")][0]
            keep_i, n_c, w_s, w_m = [], [], [], []
            for i, (cid, cov) in enumerate(zip(res[cid_col], res[cov_col])):
                cid = np.asarray(cid, dtype=np.int64)
                cov = np.asarray(cov, dtype=np.float64)
                nz = cov > 0
                if not nz.any():
                    continue
                cid, cov = cid[nz], cov[nz]
                counts.append(cid.size)
                cols.append(cid.astype(np.int32))
                vals.append(cov.astype(np.float32))
                keep_i.append(i)
                n_c.append(cid.size)
                w_s.append(cov.sum())
                w_m.append(cov.max())
            if not keep_i:
                continue
            k = np.asarray(keep_i)
            part = sub.iloc[k][["fid", "area_ha", "mbmode", "crop_group"]].copy()
            part["state"] = state
            part["n_cells"] = np.asarray(n_c, dtype=np.int32)
            part["w_sum"] = np.asarray(w_s, dtype=np.float64)
            part["w_max"] = np.asarray(w_m, dtype=np.float64)
            meta.append(part)
            n_rows += len(k)
            del res, gdf, geoms_s
    if n_rows == 0:
        W = sp.csr_matrix((0, N * N), dtype=np.float32)
        fdf = pd.DataFrame(columns=["fid", "state", "area_ha", "mbmode", "crop_group", "n_cells", "w_sum", "w_max", "dominant_share", "area_ratio"])
    else:
        indptr = np.zeros(n_rows + 1, dtype=np.int64)
        np.cumsum(counts, out=indptr[1:])
        W = sp.csr_matrix((np.concatenate(vals), np.concatenate(cols), indptr), shape=(n_rows, N * N), dtype=np.float32)
        fdf = pd.concat(meta, ignore_index=True)
        fdf["dominant_share"] = fdf["w_max"] / fdf["w_sum"]
        with np.errstate(invalid="ignore", divide="ignore"):
            fdf["area_ratio"] = np.where(fdf["area_ha"] > 0, fdf["w_sum"] * CELL_HA / fdf["area_ha"], np.nan)
        fdf = fdf[["fid", "state", "area_ha", "mbmode", "crop_group", "n_cells", "w_sum", "w_max", "dominant_share", "area_ratio"]]
    tmp = p_npz + ".part.npz"
    sp.save_npz(tmp, W, compressed=False)
    os.replace(tmp, p_npz)
    fdf.to_parquet(p_fields + ".part", index=False)
    os.replace(p_fields + ".part", p_fields)
    secs = time.time() - t0
    inside = fdf["area_ratio"]
    rec = {"hv": hv, "year": year, "status": "ok", "fields_read": int(n_read), "rows": int(n_rows), "nnz": int(W.nnz),
           "seconds": round(secs, 1), "median_area_ratio": float(np.nanmedian(inside)) if n_rows else None,
           "share_single_cell": float((fdf["n_cells"] == 1).mean()) if n_rows else None,
           "when": datetime.now().isoformat(timespec="seconds")}
    with open(TIMING, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


def check(hv, year, k=25, seed=0):
    """Compare W @ raster against exactextract mean on k random fields of one downloaded NDVI tile."""
    import numpy as np
    import pandas as pd
    import pyproj
    import rasterio
    import scipy.sparse as sp
    import shapely
    import geopandas as gpd
    from exactextract import exact_extract
    tifs = sorted(glob.glob(os.path.join(RAW, "*", f"{hv}_250m_16_days_NDVI.tif")))
    assert tifs, "no NDVI tile downloaded yet for " + hv
    tif = tifs[0]
    W = sp.load_npz(os.path.join(WEIGHTS, f"year={year}", f"{hv}.npz"))
    fdf = pd.read_parquet(os.path.join(WEIGHTS, f"year={year}", f"{hv}_fields.parquet"))
    with rasterio.open(tif) as src:
        a = src.read(1).astype(np.float64).reshape(-1)
        assert src.width == N and src.height == N
        h, v = int(hv[1:3]), int(hv[4:6])
        t = tile_transform(h, v)
        assert all(abs(x - y) < 1e-3 for x, y in zip(src.transform[:6], t[:6])), (src.transform, t)
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(fdf), size=k, replace=False)
    num = W[idx] @ a
    den = np.asarray(W[idx].sum(axis=1)).ravel()
    mine = num / den
    # the same fields, from the prepared parquet, reprojected the same way
    sub = fdf.iloc[idx]
    geoms = []
    for st, grp in sub.groupby("state"):
        g = gpd.read_parquet(os.path.join(FIELDS, f"year={year}", f"state={st}", "fields.parquet"), columns=["fid", "geometry"],
                             filters=[("fid", "in", list(grp["fid"]))])
        geoms.append(g.set_index("fid").loc[grp["fid"].values])
    g = pd.concat(geoms)
    g = gpd.GeoDataFrame(g, geometry="geometry", crs="EPSG:4326").to_crs(pyproj.CRS.from_proj4(SINU_PROJ))
    g = g.loc[sub["fid"].values]                 # same order as the matrix rows picked above
    ref = exact_extract(tif, g, ["mean"], output="pandas", progress=False)["mean"].values
    with rasterio.open(tif) as src:
        ref = ref / src.scales[0]                # exactextract applies the GDAL scale tag (10000) as a multiplier
    d = np.abs(ref - mine)
    print(pd.DataFrame({"fid": sub["fid"].values, "mine": mine, "exactextract": ref, "diff": d, "n_cells": sub["n_cells"].values}))
    print("max abs diff", float(np.nanmax(d)), "raster", tif)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--years", type=int, nargs="*", default=[2024, 2020])
    ap.add_argument("--tiles", nargs="*", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check", default=None, help="tile id to check against exactextract mean")
    ap.add_argument("--year", type=int, default=2024)
    args = ap.parse_args()
    if args.check:
        check(args.check, args.year)
        return
    with open(TILES_NEEDED) as fh:
        tiles = json.load(fh)["tiles"]
    if args.tiles:
        tiles = [t for t in tiles if t["hv"] in args.tiles]
    os.makedirs(WEIGHTS, exist_ok=True)
    # largest tiles first so the pool stays busy to the end
    tasks = [(t, y) for t in sorted(tiles, key=lambda d: -(d["n_fields_2020"] + d["n_fields_2024"])) for y in args.years]
    for t in tiles:
        template_path(t["hv"])          # made here, once, so two workers never race on the same file
    t0 = time.time()
    print(f"{len(tasks)} tasks, {args.workers} workers", flush=True)
    if args.workers <= 1:
        for t, y in tasks:
            print(json.dumps(build_tile(t, y, args.force)), flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(build_tile, t, y, args.force): (t["hv"], y) for t, y in tasks}
            for f in as_completed(futs):
                try:
                    print(json.dumps(f.result()), flush=True)
                except Exception as e:  # noqa: BLE001
                    print(json.dumps({"task": futs[f], "status": "fail", "error": str(e)[:300]}), flush=True)
    print(f"done in {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
