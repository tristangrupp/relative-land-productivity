"""Stage 3f: MapBiomas land cover class per field from the 2020 and 2024 coverage rasters.

Step "download": fetch the MapBiomas Collection 10 coverage GeoTIFFs the project treats as
its extraction grid, `https://wri-datalab-sandbox.s3.amazonaws.com/trazofields/brazil_coverage_2020.tif`
and `brazil_coverage_2024.tif` (public read, about 790 MB each, EPSG:4326, uint8, tiled
256 x 256, LZW, no overviews), to F:\\relative-land-productivity-data\\raw\\mapbiomas\\, with
resume and a size check against Content-Length.

Step "classes": for every prepared field of both years, the modal class inside the polygon
from the 2020 raster (mb_2020) and from the 2024 raster (mb_2024). For a 2024 field mb_2020 is
its crop in agricultural year 2020 (crop switching) and mb_2024 is a check against the
Trazo4 `mbmode` column. For a 2020 field mb_2024 flags abandonment: a 2020 field whose 2024
class is not agricultural. Method: per field, the pixels whose centers fall inside the
polygon are rasterized in the field's own bbox window of the 30 m grid (rasterio.features
.rasterize), and the class counts in that window give the mode. A field that holds no pixel
center is retried with all_touched=True, and a field that still holds none takes the class
of the pixel under its centroid (column `px_source`: center, touched, centroid). Raster
windows are read per 1024 x 1024 extraction tile and cached per worker, so each field costs
one small array slice; a field whose bbox crosses a tile edge reads its window directly.
exactextract's coverage-weighted mode was timed against this on the same fields (see
--measure and EXTRACT.md) and the rasterize path was kept.

Output: F:\\relative-land-productivity-data\\extracted\\mapbiomas\\year=<YYYY>\\state=<State>\\classes.parquet
with fid, mbmode (from the prepared fields), mb_2020, mb_2024, n_px (pixels counted),
px_source, agree_mbmode (mb_<year> == mbmode), ag_2020 and ag_2024 (the modal class is one of
the agricultural classes 39, 15, 19, 41, 20, 40, 62, 21, 18, 46, 47, 48, 35, 9; a 2020 field
with ag_2024 false is a candidate abandonment), vigor_2020, vigor_2024. The vigor columns are
null unless --vigor-2020 and --vigor-2024 name local MapBiomas pasture vigor GeoTIFFs; the
MapBiomas download platform did not offer them without a login on 2026-11-12 (EXTRACT.md).

Tasks are (state, year), parallel with --workers (default 6), each reading its fields parquet
in 50,000-row batches. A state-year whose output exists is skipped unless --force.

Environment: E:\\Water\\water intelligence\\wci_tools\\.venv. No Earth Engine.

Usage:
  python s03f_mapbiomas_fields.py download [--years 2024 2020]
  python s03f_mapbiomas_fields.py classes [--workers 6] [--states ...] [--years ...]
  python s03f_mapbiomas_fields.py measure --state Mato_Grosso --year 2024 [--n 20000]
"""
import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime

import numpy as np

DATA = r"F:\relative-land-productivity-data"
RAW = os.path.join(DATA, "raw", "mapbiomas")
FIELDS = os.path.join(DATA, "fields")
GRID_JSON = os.path.join(DATA, "grid", "grid.json")
OUT = os.path.join(DATA, "extracted", "mapbiomas")
LOG = os.path.join(RAW, "download.log")
URL = "https://wri-datalab-sandbox.s3.amazonaws.com/trazofields/brazil_coverage_{year}.tif"
RASTER_YEARS = [2020, 2024]
TILE = 1024
BATCH = 50_000
AG = {39, 15, 19, 41, 20, 40, 62, 21, 18, 46, 47, 48, 35, 9}
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s03c_modis_fetch import download  # noqa: E402


def raster_path(year):
    return os.path.join(RAW, f"brazil_coverage_{year}.tif")


def grid():
    with open(GRID_JSON) as fh:
        g = json.load(fh)
    return g["pixel_size_deg"], g["origin"][0], g["origin"][1], g["raster_width_px"], g["raster_height_px"]


def step_download(years):
    import requests
    os.makedirs(RAW, exist_ok=True)
    for y in years:
        url = URL.format(year=y)
        dest = raster_path(y)
        total = int(requests.head(url, timeout=60).headers["Content-Length"])
        if os.path.exists(dest) and os.path.getsize(dest) == total:
            print(f"{dest} complete ({total} bytes)", flush=True)
            continue
        t0 = time.time()
        got, secs, size = download(url, dest, sign=False)
        line = f"{datetime.now().isoformat(timespec='seconds')} {os.path.basename(dest)} {size} bytes, {got} received in {secs:.0f} s ({got / max(secs, 1e-6) / 1e6:.2f} MB/s)"
        print(line, flush=True)
        with open(LOG, "a") as fh:
            fh.write(line + "\n")


class TileCache:
    """Windows of one raster per 1024 x 1024 extraction tile, most recent 48 kept."""

    def __init__(self, path, keep=48):
        import rasterio
        self.ds = rasterio.open(path)
        self.cache = {}
        self.order = []
        self.keep = keep
        self.h, self.w = self.ds.height, self.ds.width

    def tile(self, tr, tc):
        from rasterio.windows import Window
        k = (tr, tc)
        a = self.cache.get(k)
        if a is None:
            r0, c0 = tr * TILE, tc * TILE
            win = Window(c0, r0, min(TILE, self.w - c0), min(TILE, self.h - r0))
            a = self.ds.read(1, window=win)
            self.cache[k] = a
            self.order.append(k)
            if len(self.order) > self.keep:
                self.cache.pop(self.order.pop(0), None)
        return a

    def window(self, r0, r1, c0, c1):
        tr0, tr1, tc0, tc1 = r0 // TILE, (r1 - 1) // TILE, c0 // TILE, (c1 - 1) // TILE
        if tr0 == tr1 and tc0 == tc1:
            a = self.tile(tr0, tc0)
            return a[r0 - tr0 * TILE:r1 - tr0 * TILE, c0 - tc0 * TILE:c1 - tc0 * TILE]
        from rasterio.windows import Window
        return self.ds.read(1, window=Window(c0, r0, c1 - c0, r1 - r0))


def mode_counts(classes):
    if classes.size == 0:
        return -1, 0
    b = np.bincount(classes, minlength=256)
    return int(b.argmax()), int(classes.size)


def classify_batch(b, caches, vig_caches, px, ox, oy, W, H):
    """Modal class per field for every raster in `caches`; returns dict of arrays."""
    import shapely
    from rasterio.features import rasterize
    from rasterio.transform import Affine
    bb = b.column("bbox").flatten()
    xmin, ymin, xmax, ymax = (bb[i].to_numpy() for i in range(4))
    geoms = shapely.from_wkb(b.column("geometry").to_numpy(zero_copy_only=False))
    n = len(geoms)
    c0 = np.clip(np.floor((xmin - ox) / px).astype(np.int64), 0, W - 1)
    c1 = np.clip(np.ceil((xmax - ox) / px).astype(np.int64), c0 + 1, W)
    r0 = np.clip(np.floor((oy - ymax) / px).astype(np.int64), 0, H - 1)
    r1 = np.clip(np.ceil((oy - ymin) / px).astype(np.int64), r0 + 1, H)
    keys = list(caches)
    out = {k: np.full(n, -1, np.int16) for k in keys}
    vout = {k: np.full(n, -1, np.int16) for k in vig_caches}
    n_px = np.zeros(n, np.int32)
    src = np.zeros(n, np.int8)        # 0 center, 1 touched, 2 centroid
    for i in range(n):
        shape = (int(r1[i] - r0[i]), int(c1[i] - c0[i]))
        tr = Affine(px, 0.0, ox + c0[i] * px, 0.0, -px, oy - r0[i] * px)
        mask = rasterize([(geoms[i], 1)], out_shape=shape, transform=tr, fill=0, dtype="uint8", all_touched=False).astype(bool)
        if not mask.any():
            mask = rasterize([(geoms[i], 1)], out_shape=shape, transform=tr, fill=0, dtype="uint8", all_touched=True).astype(bool)
            src[i] = 1
            if not mask.any():
                cen = shapely.centroid(geoms[i])
                cc = min(max(int((cen.x - ox) // px), 0), W - 1)
                rr = min(max(int((oy - cen.y) // px), 0), H - 1)
                r0[i], r1[i], c0[i], c1[i] = rr, rr + 1, cc, cc + 1
                mask = np.ones((1, 1), bool)
                src[i] = 2
        wins = {k: caches[k].window(int(r0[i]), int(r1[i]), int(c0[i]), int(c1[i])) for k in keys}
        for k in keys:
            m, cnt = mode_counts(wins[k][mask])
            out[k][i] = m
        n_px[i] = int(mask.sum())
        for k, vc in vig_caches.items():
            w = vc.window(int(r0[i]), int(r1[i]), int(c0[i]), int(c1[i]))
            cls = w[mask]
            cls = cls[(cls > 0) & (cls < 255)]
            vout[k][i] = mode_counts(cls)[0]
    return out, vout, n_px, src


def classify_state(state, year, vigor_paths, force=False, limit=0):
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
    out_dir = os.path.join(OUT, f"year={year}", f"state={state}")
    out_path = os.path.join(out_dir, "classes.parquet")
    if os.path.exists(out_path) and not force and not limit:
        return {"state": state, "year": year, "status": "skip"}
    t0 = time.time()
    px, ox, oy, W, H = grid()
    caches = {y: TileCache(raster_path(y)) for y in RASTER_YEARS}
    vig = {y: TileCache(p) for y, p in vigor_paths.items() if p and os.path.exists(p)}
    pf = pq.ParquetFile(os.path.join(FIELDS, f"year={year}", f"state={state}", "fields.parquet"))
    parts = []
    n = 0
    for b in pf.iter_batches(batch_size=BATCH, columns=["fid", "mbmode", "bbox", "geometry"]):
        out, vout, n_px, src = classify_batch(b, caches, vig, px, ox, oy, W, H)
        df = pd.DataFrame({"fid": b.column("fid").to_numpy(), "mbmode": b.column("mbmode").to_numpy()})
        for y in RASTER_YEARS:
            df[f"mb_{y}"] = out[y]
        df["n_px"] = n_px
        df["px_source"] = pd.Categorical.from_codes(src, ["center", "touched", "centroid"])
        for y in RASTER_YEARS:
            df[f"vigor_{y}"] = vout[y] if y in vout else pd.array([None] * len(df), dtype="Int16")
            if y in vout:
                df[f"vigor_{y}"] = df[f"vigor_{y}"].where(df[f"vigor_{y}"] >= 0).astype("Int16")
        df["agree_mbmode"] = df[f"mb_{year}"].values == df["mbmode"].values
        for y in RASTER_YEARS:
            df[f"ag_{y}"] = df[f"mb_{y}"].isin(list(AG)).values
        parts.append(df)
        n += len(df)
        if limit and n >= limit:
            break
    res = pd.concat(parts, ignore_index=True)
    if limit:
        return {"state": state, "year": year, "rows": int(len(res)), "seconds": round(time.time() - t0, 1),
                "agree": float(res["agree_mbmode"].mean()), "df": res}
    os.makedirs(out_dir, exist_ok=True)
    table = pa.Table.from_pandas(res, preserve_index=False)
    meta = dict(table.schema.metadata or {})
    meta[b"mapbiomas_classes"] = json.dumps({"state": state, "year": year, "rasters": {y: os.path.basename(raster_path(y)) for y in RASTER_YEARS},
                                            "vigor": {y: os.path.basename(p) for y, p in vigor_paths.items() if p},
                                            "written": datetime.now().isoformat(timespec="seconds")}).encode()
    pq.write_table(table.replace_schema_metadata(meta), out_path + ".part", compression="zstd")
    os.replace(out_path + ".part", out_path)
    other = 2024 if year == 2020 else 2020
    return {"state": state, "year": year, "status": "ok", "rows": int(len(res)), "seconds": round(time.time() - t0, 1),
            "agree_mbmode": round(float(res["agree_mbmode"].mean()), 4),
            "share_centroid": round(float((res["px_source"] == "centroid").mean()), 4),
            f"share_not_ag_{other}": round(float((~res[f"ag_{other}"]).mean()), 4)}


def measure(state, year, n):
    """Time the rasterize path and exactextract's coverage-weighted mode on the same fields."""
    import geopandas as gpd
    import pandas as pd
    import pyarrow.parquet as pq
    from exactextract import exact_extract
    r = classify_state(state, year, {}, limit=n)
    df = r["df"]
    print(f"rasterize path: {r['rows']} fields in {r['seconds']} s ({r['seconds'] / r['rows'] * 1e3:.3f} ms per field), agree {r['agree']:.4f}")
    pf = pq.ParquetFile(os.path.join(FIELDS, f"year={year}", f"state={state}", "fields.parquet"))
    tb = next(pf.iter_batches(batch_size=n, columns=["fid", "geometry"]))
    gdf = gpd.GeoDataFrame({"fid": tb.column("fid").to_numpy()}, geometry=gpd.GeoSeries.from_wkb(tb.column("geometry").to_numpy(zero_copy_only=False)), crs="EPSG:4326")
    t0 = time.time()
    ee = exact_extract(raster_path(year), gdf, ["mode"], output="pandas", progress=False)
    secs = time.time() - t0
    m = df.set_index("fid").loc[gdf["fid"].values, f"mb_{year}"].values
    same = (ee["mode"].values.astype(int) == m).mean()
    print(f"exactextract mode: {len(gdf)} fields in {secs:.1f} s ({secs / len(gdf) * 1e3:.3f} ms per field); agrees with rasterize path on {same:.4f} of fields")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["download", "classes", "measure"])
    ap.add_argument("--years", type=int, nargs="*", default=[2024, 2020])
    ap.add_argument("--states", nargs="*", default=None)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--vigor-2020", default=None)
    ap.add_argument("--vigor-2024", default=None)
    ap.add_argument("--state", default="Mato_Grosso")
    ap.add_argument("--year", type=int, default=2024)
    ap.add_argument("--n", type=int, default=20000)
    args = ap.parse_args()
    if args.step == "download":
        step_download(args.years)
        return
    if args.step == "measure":
        measure(args.state, args.year, args.n)
        return
    for y in RASTER_YEARS:
        assert os.path.exists(raster_path(y)), f"run download first: {raster_path(y)}"
    vig = {2020: args.vigor_2020, 2024: args.vigor_2024}
    states = sorted(d.split("state=")[1] for d in os.listdir(os.path.join(FIELDS, "year=2024")) if d.startswith("state="))
    tasks = [(s, y) for y in args.years for s in states if not args.states or s in args.states]
    # biggest files first
    tasks.sort(key=lambda t: -os.path.getsize(os.path.join(FIELDS, f"year={t[1]}", f"state={t[0]}", "fields.parquet")))
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(classify_state, s, y, vig, args.force) for s, y in tasks]
        for f in as_completed(futs):
            try:
                print(json.dumps(f.result()), flush=True)
            except Exception as e:  # noqa: BLE001
                print(json.dumps({"status": "fail", "error": str(e)[:300]}), flush=True)
    print(f"done in {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
