"""Stage 3e: reduce MODIS 16-day NDVI to a coverage-weighted mean per field.

Two steps, both resumable.

Step "reduce": for each agricultural year, MODIS tile and composite whose three raw GeoTIFFs
(s03c_modis_fetch.py) and whose weights (s03d_modis_weights.py) exist, read NDVI, VI_Quality
and pixel_reliability, build the valid-pixel mask, and compute with the sparse weights W
(fields x cells, coverage fractions)

  num = W @ (NDVI x 0.0001 where valid, else 0)        den = W @ (1 where valid, else 0)

written as float32 arrays to extracted\\modis\\partial\\year=<YYYY>\\<h##v##>\\<YYYYDDD>.npz.
The raster header is checked against the tile transform the weights were built on.

Valid pixel: NDVI is not the fill value -3000 and lies in the valid range -2000 to 10000;
pixel_reliability is 0 (good) or 1 (marginal), so 2 (snow/ice), 3 (cloudy) and 255 (fill)
are masked; and the MODLAND QA in VI_Quality bits 0 to 1 is 0 (good) or 1 (check other QA),
so 2 (snow/ice) and 3 (cloudy) are masked. Reliability and the QA bits mostly agree; both are
applied. If a composite has no pixel_reliability asset, VI_Quality alone is used.

Step "assemble": for each year and state, gather the partial arrays of every tile that
touches the state, sum num and den per field across tiles (a field on a tile edge has a row in
two tiles), and write one row per field to

  extracted\\modis\\year=<YYYY>\\state=<State>\\ndvi_16day.parquet

with columns fid, area_ha, mbmode, crop_group, n_cells (MODIS cells with nonzero coverage,
all tiles), w_sum (covered cells, in cell units), dominant_share (share of the field in its
largest cell), small_field (area_ha < 6.25, one MODIS pixel; low confidence), n_valid (number
of composites with a valid value), ndvi_<YYYYDDD> (23 raw columns; NaN where less than half
the field's covered area had a valid pixel, the rule METHODS.md section 3 sets), and
ndvi_fill_<YYYYDDD> (23 columns: the raw series with gaps filled by linear interpolation in
time between the nearest valid composites; a gap at either end takes the nearest valid value;
a field with no valid composite stays NaN). The series is not smoothed. A composite missing
from the Planetary Computer for every tile (A2024225) is a NaN column in the raw table and is
filled like any other gap.

Usage:
  python s03e_modis_reduce.py reduce [--workers 4]           reduce whatever raw files exist
  python s03e_modis_reduce.py assemble [--workers 3] [--states ...] [--partial]
  python s03e_modis_reduce.py watch [--workers 4]            loop: reduce as files land, then assemble
                                                             once every expected partial exists
  python s03e_modis_reduce.py check                          median NDVI for the sanity checks
"""
import argparse
import glob
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime

import numpy as np

DATA = r"F:\relative-land-productivity-data"
RAW = os.path.join(DATA, "raw", "modis")
WEIGHTS = os.path.join(DATA, "weights", "modis")
FIELDS = os.path.join(DATA, "fields")
OUT = os.path.join(DATA, "extracted", "modis")
PARTIAL = os.path.join(OUT, "partial")
TILES_NEEDED = os.path.join(RAW, "tiles_needed.json")
MISSING = os.path.join(RAW, "missing.json")
N = 4800
FILL = -3000
VALID_MIN, VALID_MAX = -2000, 10000
SMALL_HA = 6.25
VALID_AREA_SHARE = 0.5
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s03c_modis_fetch import composites_for_year, doy_to_date, tile_transform  # noqa: E402

YEARS = [2024, 2020]


def raw_paths(comp, hv):
    d = os.path.join(RAW, comp)
    return (os.path.join(d, f"{hv}_250m_16_days_NDVI.tif"),
            os.path.join(d, f"{hv}_250m_16_days_VI_Quality.tif"),
            os.path.join(d, f"{hv}_250m_16_days_pixel_reliability.tif"))


def partial_path(year, hv, comp):
    return os.path.join(PARTIAL, f"year={year}", hv, f"{comp}.npz")


def load_missing():
    if os.path.exists(MISSING):
        with open(MISSING) as fh:
            return json.load(fh)
    return {}


def valid_mask(ndvi, qa, rel):
    ok = (ndvi != FILL) & (ndvi >= VALID_MIN) & (ndvi <= VALID_MAX)
    ok &= (qa & 0b11) < 2
    if rel is not None:
        ok &= rel < 2
    return ok


def reduce_tile_year(year, hv, comps):
    """All composites of one tile and year that have raw files and no partial yet."""
    import rasterio
    import scipy.sparse as sp
    todo = [c for c in comps if not os.path.exists(partial_path(year, hv, c))
            and os.path.exists(raw_paths(c, hv)[0]) and os.path.exists(raw_paths(c, hv)[1])]
    if not todo:
        return {"year": year, "hv": hv, "done": 0}
    p_w = os.path.join(WEIGHTS, f"year={year}", f"{hv}.npz")
    if not os.path.exists(p_w):
        return {"year": year, "hv": hv, "done": 0, "note": "no weights yet"}
    W = sp.load_npz(p_w).tocsr()
    W.data = W.data.astype(np.float64)
    h, v = int(hv[1:3]), int(hv[4:6])
    expect = tile_transform(h, v)
    t0 = time.time()
    n = 0
    for comp in todo:
        p_nd, p_qa, p_rel = raw_paths(comp, hv)
        with rasterio.open(p_nd) as src:
            assert src.width == N and src.height == N, (p_nd, src.width, src.height)
            assert all(abs(a - b) < 1e-3 for a, b in zip(src.transform[:6], expect[:6])), (p_nd, src.transform)
            ndvi = src.read(1)
        with rasterio.open(p_qa) as src:
            qa = src.read(1)
        rel = None
        if os.path.exists(p_rel):
            with rasterio.open(p_rel) as src:
                rel = src.read(1)
        ok = valid_mask(ndvi, qa, rel).reshape(-1)
        val = np.where(ok, ndvi.reshape(-1).astype(np.float64) * 1e-4, 0.0)
        num = W @ val
        den = W @ ok.astype(np.float64)
        out = partial_path(year, hv, comp)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        tmp = out + ".part.npz"
        np.savez(tmp, num=num.astype(np.float32), den=den.astype(np.float32),
                 share_valid_pixels=np.float32(ok.mean()), used_reliability=rel is not None)
        os.replace(tmp, out)
        n += 1
    return {"year": year, "hv": hv, "done": n, "seconds": round(time.time() - t0, 1), "rows": W.shape[0]}


def expected(years):
    with open(TILES_NEEDED) as fh:
        tiles = json.load(fh)["tiles"]
    missing = load_missing()
    exp = []
    for y in years:
        for c in composites_for_year(y):
            for t in tiles:
                if t["hv"] in missing.get(c, []):
                    continue
                exp.append((y, t["hv"], c))
    return tiles, exp


def run_reduce(years, workers):
    tiles, exp = expected(years)
    tasks = {}
    for y, hv, c in exp:
        if not os.path.exists(partial_path(y, hv, c)):
            tasks.setdefault((y, hv), []).append(c)
    if not tasks:
        return 0
    t0 = time.time()
    n = 0
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(reduce_tile_year, y, hv, comps) for (y, hv), comps in tasks.items()]
        for f in as_completed(futs):
            try:
                r = f.result()
                n += r["done"]
                if r["done"]:
                    print(json.dumps(r), flush=True)
            except Exception as e:  # noqa: BLE001
                print(json.dumps({"status": "fail", "error": str(e)[:300]}), flush=True)
    print(f"reduce pass: {n} partials in {time.time() - t0:.0f} s", flush=True)
    return n


def n_pending(years):
    _, exp = expected(years)
    return sum(1 for y, hv, c in exp if not os.path.exists(partial_path(y, hv, c)))


def interpolate_rows(vals, t):
    """Linear interpolation in time along axis 1; NaN gaps at the ends take the nearest valid value."""
    n = vals.shape[1]
    valid = ~np.isnan(vals)
    idx = np.arange(n)
    left = np.where(valid, idx, -1)
    left = np.maximum.accumulate(left, axis=1)
    right = np.where(valid, idx, n)
    right = np.minimum.accumulate(right[:, ::-1], axis=1)[:, ::-1]
    any_valid = valid.any(axis=1)
    out = vals.copy()
    li = np.clip(left, 0, n - 1)
    ri = np.clip(right, 0, n - 1)
    vl = np.take_along_axis(vals, li, axis=1)
    vr = np.take_along_axis(vals, ri, axis=1)
    tl = t[li]
    tr = t[ri]
    tj = np.broadcast_to(t, vals.shape)
    with np.errstate(invalid="ignore", divide="ignore"):
        w = np.where(tr > tl, (tj - tl) / (tr - tl), 0.0)
    interp = vl + w * (vr - vl)
    interp = np.where(left < 0, vr, interp)        # before the first valid
    interp = np.where(right >= n, vl, interp)      # after the last valid
    fill = ~valid & any_valid[:, None]
    out[fill] = interp[fill]
    return out


def assemble_state(year, state, hvs, comps, partial_ok=False):
    import pandas as pd
    import pyarrow.parquet as pq
    out_dir = os.path.join(OUT, f"year={year}", f"state={state}")
    out_path = os.path.join(out_dir, "ndvi_16day.parquet")
    t0 = time.time()
    frames = []
    used = set()
    missing = load_missing()
    for hv in hvs:
        p_f = os.path.join(WEIGHTS, f"year={year}", f"{hv}_fields.parquet")
        if not os.path.exists(p_f):
            if partial_ok:
                continue
            return {"year": year, "state": state, "status": "waiting", "note": f"no weights for {hv}"}
        fdf = pd.read_parquet(p_f)
        sel = np.flatnonzero(fdf["state"].values == state)
        if sel.size == 0:
            continue
        cols = {"fid": fdf["fid"].values[sel], "n_cells": fdf["n_cells"].values[sel],
                "w_sum": fdf["w_sum"].values[sel], "w_max": fdf["w_max"].values[sel]}
        for c in comps:
            p = partial_path(year, hv, c)
            if not os.path.exists(p):
                # a composite the fetch recorded as absent from the archive stays NaN and is interpolated
                if partial_ok or hv in missing.get(c, []):
                    cols[f"num_{c}"] = np.full(sel.size, np.nan, np.float32)
                    cols[f"den_{c}"] = np.full(sel.size, np.nan, np.float32)
                    continue
                return {"year": year, "state": state, "status": "waiting", "note": f"no partial {hv} {c}"}
            z = np.load(p)
            cols[f"num_{c}"] = z["num"][sel]
            cols[f"den_{c}"] = z["den"][sel]
            used.add(c)
        frames.append(pd.DataFrame(cols))
    if not frames:
        return {"year": year, "state": state, "status": "empty"}
    df = pd.concat(frames, ignore_index=True)
    # a field that spans tiles: sum num, den, n_cells, w_sum; take the largest single cell weight
    agg = {c: "sum" for c in df.columns if c.startswith(("num_", "den_"))}
    agg.update({"n_cells": "sum", "w_sum": "sum", "w_max": "max"})
    g = df.groupby("fid", sort=True).agg(agg)
    fids = g.index.values
    wsum = g["w_sum"].values.astype(np.float64)
    raw = np.full((len(g), len(comps)), np.nan, dtype=np.float32)
    for j, c in enumerate(comps):
        num = g[f"num_{c}"].values.astype(np.float64)
        den = g[f"den_{c}"].values.astype(np.float64)
        with np.errstate(invalid="ignore", divide="ignore"):
            v = num / den
        ok = (den > 0) & (den / wsum >= VALID_AREA_SHARE)
        raw[:, j] = np.where(ok, v, np.nan).astype(np.float32)
    t = np.array([(doy_to_date(c) - doy_to_date(comps[0])).days for c in comps], dtype=np.float64)
    filled = interpolate_rows(raw.astype(np.float64), t).astype(np.float32)
    # attributes from the prepared fields, so every prepared field has a row even with no weights
    pf = pq.ParquetFile(os.path.join(FIELDS, f"year={year}", f"state={state}", "fields.parquet"))
    attrs = pf.read(columns=["fid", "area_ha", "mbmode", "crop_group"]).to_pandas().set_index("fid")
    res = pd.DataFrame({"fid": fids})
    res = res.join(attrs, on="fid")
    res["n_cells"] = g["n_cells"].values.astype(np.int32)
    res["w_sum"] = wsum.astype(np.float32)
    with np.errstate(invalid="ignore", divide="ignore"):
        res["dominant_share"] = (g["w_max"].values / wsum).astype(np.float32)
    res["small_field"] = res["area_ha"].values < SMALL_HA
    res["n_valid"] = (~np.isnan(raw)).sum(axis=1).astype(np.int8)
    for j, c in enumerate(comps):
        res[f"ndvi_{c}"] = raw[:, j]
    for j, c in enumerate(comps):
        res[f"ndvi_fill_{c}"] = filled[:, j]
    missing_fields = attrs.index.difference(res["fid"])
    if len(missing_fields):
        extra = attrs.loc[missing_fields].reset_index()
        res = pd.concat([res, extra], ignore_index=True)
        res["small_field"] = res["area_ha"].values < SMALL_HA
        res["n_valid"] = res["n_valid"].fillna(0).astype(np.int8)
    os.makedirs(out_dir, exist_ok=True)
    import pyarrow as pa
    table = pa.Table.from_pandas(res, preserve_index=False)
    meta = dict(table.schema.metadata or {})
    meta[b"modis_reduce"] = json.dumps({"year": year, "state": state, "tiles": hvs, "composites": comps,
                                        "composites_with_data": sorted(used), "written": datetime.now().isoformat(timespec="seconds"),
                                        "valid_area_share": VALID_AREA_SHARE, "small_field_ha": SMALL_HA}).encode()
    pq.write_table(table.replace_schema_metadata(meta), out_path + ".part", compression="zstd")
    os.replace(out_path + ".part", out_path)
    return {"year": year, "state": state, "status": "ok", "rows": int(len(res)), "prepared": int(len(attrs)),
            "fields_without_weights": int(len(missing_fields)), "composites_with_data": len(used),
            "seconds": round(time.time() - t0, 1),
            "median_n_valid": float(np.median(res["n_valid"])), "share_small": float(res["small_field"].mean())}


def state_tasks(years, states=None):
    with open(TILES_NEEDED) as fh:
        tiles = json.load(fh)["tiles"]
    tasks = []
    for y in years:
        all_states = sorted({s for t in tiles for s in t["states"]})
        for s in all_states:
            if states and s not in states:
                continue
            hvs = [t["hv"] for t in tiles if s in t["states"]]
            tasks.append((y, s, hvs, composites_for_year(y)))
    return tasks


def run_assemble(years, workers, states=None, partial_ok=False, force=False):
    tasks = state_tasks(years, states)
    todo = [t for t in tasks if force or not os.path.exists(os.path.join(OUT, f"year={t[0]}", f"state={t[1]}", "ndvi_16day.parquet"))]
    results = []
    if not todo:
        return results
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(assemble_state, y, s, hvs, comps, partial_ok) for y, s, hvs, comps in todo]
        for f in as_completed(futs):
            try:
                r = f.result()
            except Exception as e:  # noqa: BLE001
                r = {"status": "fail", "error": str(e)[:300]}
            print(json.dumps(r), flush=True)
            results.append(r)
    return results


def check():
    import pandas as pd
    for year, state, cls, comp in [(2024, "Mato_Grosso", 39, "2024017"), (2024, "Para", 15, "2024017"),
                                   (2020, "Mato_Grosso", 39, "2020017"), (2020, "Para", 15, "2020017")]:
        p = os.path.join(OUT, f"year={year}", f"state={state}", "ndvi_16day.parquet")
        if not os.path.exists(p):
            print(year, state, "not assembled yet")
            continue
        df = pd.read_parquet(p, columns=["mbmode", "area_ha", "n_valid", f"ndvi_{comp}", f"ndvi_fill_{comp}"])
        sub = df[df["mbmode"] == cls]
        print(f"{year} {state} class {cls}: {len(sub)} fields, median ndvi_{comp} raw {sub[f'ndvi_{comp}'].median():.3f} "
              f"(valid {sub[f'ndvi_{comp}'].notna().mean():.2%}), filled {sub[f'ndvi_fill_{comp}'].median():.3f}, "
              f"median n_valid {sub['n_valid'].median():.0f}, share under {SMALL_HA} ha {(sub['area_ha'] < SMALL_HA).mean():.2%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["reduce", "assemble", "watch", "check"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--years", type=int, nargs="*", default=YEARS)
    ap.add_argument("--states", nargs="*", default=None)
    ap.add_argument("--partial", action="store_true", help="assemble with whatever partials exist")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--poll", type=int, default=180, help="seconds between watch passes")
    args = ap.parse_args()
    if args.step == "check":
        check()
    elif args.step == "reduce":
        run_reduce(args.years, args.workers)
        print("pending partials:", n_pending(args.years))
    elif args.step == "assemble":
        run_assemble(args.years, min(args.workers, 3), args.states, args.partial, args.force)
    else:
        while True:
            run_reduce(args.years, args.workers)
            left = n_pending(args.years)
            print(f"{datetime.now().isoformat(timespec='seconds')} pending partials: {left}", flush=True)
            if left == 0:
                break
            time.sleep(args.poll)
        run_assemble(args.years, min(args.workers, 3), args.states)
        check()


if __name__ == "__main__":
    main()
