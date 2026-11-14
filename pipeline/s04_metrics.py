"""Stage 4a: per-field productivity metrics and weather anomalies for one agricultural year.

Implements METHODS.md sections 2, 4 and the weather inputs of section 5 for one NDVI source,
one polygon year and one agricultural year, per state:

  python s04_metrics.py --source modis --polys 2024 --ay 2024 [--states ...] [--workers 2]
  python s04_metrics.py --source modis --polys 2024 --ay 2020        (tables from s04_xyear_reduce.py)
  python s04_metrics.py --source modis --polys 2020 --ay 2020
  python s04_metrics.py --source s2    --polys 2024 --ay 2024        (Sentinel-2 monthly tables)

Input series. `--source modis` reads the extract tables (23 composites per agricultural
year, columns ndvi_<YYYYDDD> raw and ndvi_fill_<YYYYDDD> interpolated); a composite is dated
by its mid point (start day plus 8) and weighs 16 / 30.4375 months in the integrals, so the
integrals are in NDVI-months whatever the cadence. `--source s2` reads the Sentinel-2 monthly
tables (ndvi_<YYYY-MM> and ndvi_<YYYY-MM>_filled, the 12 months of the agricultural year,
each one month). `--ndvi-root` points at another folder with the same layout, for tests on
partial tables.

Class of the field for the year: the Trazo4 `mbmode` when the polygon year is the
agricultural year, and the MapBiomas 2020 modal class `mb_2020` (s03f_mapbiomas_fields.py)
for the 2020 year on the 2024 polygons. The calendar window is the state x class row of
data/calendars/class_window_lookup.csv, with classes 9 and 18 taking the full year. A window
is a contiguous run of months in the September to August order, so a window such as October
to April wraps the calendar year inside one agricultural year.

Metrics per field (METHODS.md section 4), from the interpolated series:
  baseline  the field's own minimum over the whole year; for the perennial classes (20, 46,
            47, 48, 35, 15 and 9) the 5th percentile of the interpolated values of that class
            in the state and year
  integral  sum over the window of max(ndvi - baseline, 0) times the step in months
  peak      maximum ndvi in the window
  tpeak     months from the window start to the peak composite
  annual    the same sum over the whole year
  n_window  composites (or months) in the window, n_valid_window of them with a raw value
Fields with no valid composite at all have NaN metrics.

Weather per field, read at the centroid: CHIRPS monthly precipitation summed over the window
months and the TerraClimate (tmax + tmin) / 2 mean over the same months, for the target
year and for every agricultural year the rasters cover in full, 2016 to 2024 (the rasters
start in January 2015, so agricultural year 2015 lacks September to December 2014; METHODS.md
names ten baseline years, nine are available). p_anom and t_anom are the target year's values
minus the baseline mean, divided by the baseline standard deviation. Centroids are converted
to raster row and column once per grid; a centroid on a nodata cell gets NaN anomalies, which
the relative stage treats as zero adjustment.

Output: analysis\\metrics\\source=<src>\\polys=<polys>\\ay=<ay>\\<State>.parquet with fid,
area_ha, cls, peer_cls, ag, muni_code, state_uf, lon, lat, h3_6, h3_5, h3_4, h3_3,
small_field, n_cells, dominant_share, window_start, window_end, n_window, n_valid_window,
n_valid_year, baseline, integral, peak, tpeak, annual, p_sum, t_mean, p_anom, t_anom.
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s04_common as C  # noqa: E402

DAYS_PER_MONTH = 30.4375
BASELINE_AYS = list(range(2016, 2025))
WEATHER_MONTHS = [(y, m) for y in range(2015, 2025) for m in range(1, 13)]
_WEATHER = {}


def series_spec(source, ay, columns):
    """List of (raw column, filled column, mid date, step in months) for the year, in time order."""
    out = []
    if source == "modis":
        from s03c_modis_fetch import composites_for_year, doy_to_date
        for c in composites_for_year(ay):
            mid = doy_to_date(c).replace(tzinfo=None) + timedelta(days=8)
            out.append((f"ndvi_{c}", f"ndvi_fill_{c}", mid, 16.0 / DAYS_PER_MONTH))
    else:
        for i in range(12):
            y, m = (ay - 1, 9 + i) if i < 4 else (ay, i - 3)
            out.append((f"ndvi_{y}-{m:02d}", f"ndvi_{y}-{m:02d}_filled", datetime(y, m, 15), 1.0))
    for raw, fill, _, _ in out:
        if fill not in columns:
            raise KeyError(f"column {fill} not in the NDVI table")
    return out


def window_months(start, end):
    """Calendar months of the window in agricultural-year order."""
    a, b = C.month_pos(start), C.month_pos(end)
    assert a <= b, (start, end)
    return [((p + 8) % 12) + 1 for p in range(a, b + 1)]


def window_start_date(start, ay):
    return datetime(ay - 1 if start >= 9 else ay, start, 1)


def ay_month_year(m, ay):
    return ay - 1 if m >= 9 else ay


# ---------------------------------------------------------------- weather

def load_weather():
    """All monthly rasters 2015-01 to 2024-12 in memory: chirps [120,H,W], tmean [120,H,W], and the grids."""
    import rasterio
    if _WEATHER:
        return _WEATHER
    for var in ("chirps", "tmean"):
        arrs = []
        for y, m in WEATHER_MONTHS:
            if var == "chirps":
                with rasterio.open(os.path.join(C.WEATHER, "chirps", f"{y}-{m:02d}.tif")) as src:
                    a = src.read(1).astype(np.float32)
                    a[a == src.nodata] = np.nan
                    tr = src.transform
            else:
                with rasterio.open(os.path.join(C.WEATHER, "tmax", f"{y}-{m:02d}.tif")) as src:
                    a1 = src.read(1).astype(np.float32)
                    a1[a1 == src.nodata] = np.nan
                    tr = src.transform
                with rasterio.open(os.path.join(C.WEATHER, "tmin", f"{y}-{m:02d}.tif")) as src:
                    a2 = src.read(1).astype(np.float32)
                    a2[a2 == src.nodata] = np.nan
                a = (a1 + a2) / 2.0
            arrs.append(a)
        _WEATHER[var] = np.stack(arrs)
        _WEATHER[var + "_transform"] = tr
    return _WEATHER


def month_index(y, m):
    return (y - 2015) * 12 + (m - 1)


def window_weather(var, months, ay):
    """Per raster cell: the window aggregate for the target year, the baseline mean and sd."""
    W = load_weather()
    stack = W[var]
    agg = np.nansum if var == "chirps" else np.nanmean

    def one(year):
        idx = [month_index(ay_month_year(m, year), m) for m in months]
        with np.errstate(all="ignore"):
            return agg(stack[idx], axis=0)

    base = np.stack([one(y) for y in BASELINE_AYS])
    mean = base.mean(axis=0)
    sd = base.std(axis=0, ddof=1)
    target = one(ay) if ay in BASELINE_AYS else one(ay)
    # nansum returns 0 where every month is nodata; restore NaN from the mean raster
    target = np.where(np.isnan(mean), np.nan, target)
    return target, mean, sd


def rowcol(transform, lon, lat, shape):
    col = np.floor((lon - transform.c) / transform.a).astype(np.int64)
    row = np.floor((lat - transform.f) / transform.e).astype(np.int64)
    inside = (row >= 0) & (row < shape[0]) & (col >= 0) & (col < shape[1])
    return np.clip(row, 0, shape[0] - 1), np.clip(col, 0, shape[1] - 1), inside


# ---------------------------------------------------------------- metrics

def compute_state(source, polys, ay, state, ndvi_root=None, force=False):
    t0 = time.time()
    out_path = C.metrics_path(source, polys, ay, state)
    if os.path.exists(out_path) and not force:
        return {"state": state, "status": "exists"}
    p_ndvi = C.ndvi_path(source, polys, ay, state, ndvi_root)
    if not os.path.exists(p_ndvi):
        return {"state": state, "status": "waiting", "note": p_ndvi}
    pf = pq.ParquetFile(p_ndvi)
    spec = series_spec(source, ay, set(pf.schema_arrow.names))
    raw_cols = [s[0] for s in spec]
    fill_cols = [s[1] for s in spec]
    mids = [s[2] for s in spec]
    dt = np.array([s[3] for s in spec], dtype=np.float64)
    # the Sentinel-2 tables hold fid and the series only; area_ha and mbmode then come from the prepared fields
    base_cols = ["fid"] + [c for c in ("area_ha", "mbmode") if c in pf.schema_arrow.names]
    extra = [c for c in ("n_cells", "dominant_share", "small_field") if c in pf.schema_arrow.names]
    nvy = [c for c in (f"n_valid_{ay}", "n_valid") if c in pf.schema_arrow.names][:1]
    tab = pf.read(columns=base_cols + extra + nvy + raw_cols + fill_cols)
    df = tab.select(base_cols + extra + nvy).to_pandas()
    R = np.column_stack([tab.column(c).to_numpy(zero_copy_only=False) for c in raw_cols]).astype(np.float32)
    F = np.column_stack([tab.column(c).to_numpy(zero_copy_only=False) for c in fill_cols]).astype(np.float32)
    del tab
    n = len(df)

    # attributes from the prepared fields
    fp = pq.ParquetFile(C.fields_path(polys, state))
    attrs = fp.read(columns=["fid", "muni_code", "state_uf", "centroid_lon", "centroid_lat", "area_ha", "mbmode"]).to_pandas()
    attrs = attrs.set_index("fid")
    df = df.join(attrs[["muni_code", "state_uf", "centroid_lon", "centroid_lat"]], on="fid")
    for c in ("area_ha", "mbmode"):
        if c not in df:
            df[c] = attrs[c].reindex(df["fid"].values).values
    uf = attrs["state_uf"].iloc[0]
    if "small_field" not in df:
        df["small_field"] = df["area_ha"].values < 6.25
    if "n_cells" not in df:
        df["n_cells"] = np.int32(-1)
    if "dominant_share" not in df:
        df["dominant_share"] = np.float32(np.nan)

    # class of the year
    if polys == ay:
        cls = df["mbmode"].values.astype(np.int16)
    else:
        cl = pq.read_table(C.classes_path(polys, state), columns=["fid", f"mb_{ay}"]).to_pandas().set_index("fid")
        cls = df.join(cl, on="fid")[f"mb_{ay}"].fillna(-1).values.astype(np.int16)
    ag = np.isin(cls, C.AG_CLASSES)
    windows = C.load_windows()
    starts = np.full(n, 9, np.int8)
    ends = np.full(n, 8, np.int8)
    for c in np.unique(cls):
        w = windows.get((uf, int(c)), (9, 8))
        sel = cls == c
        starts[sel], ends[sel] = w

    # baselines
    with np.errstate(all="ignore"):
        annual_min = np.nanmin(F, axis=1)
    baseline = annual_min.copy()
    for c in np.unique(cls[np.isin(cls, list(C.PERENNIAL))]):
        sel = cls == c
        vals = F[sel]
        vals = vals[~np.isnan(vals)]
        if vals.size:
            baseline[sel] = np.percentile(vals, 5)
    with np.errstate(all="ignore"):
        excess = np.maximum(F - baseline[:, None], 0.0)
        annual = np.nansum(excess * dt[None, :], axis=1)
    no_data = np.isnan(F).all(axis=1)
    annual[no_data] = np.nan

    integral = np.full(n, np.nan, np.float32)
    peak = np.full(n, np.nan, np.float32)
    tpeak = np.full(n, np.nan, np.float32)
    n_window = np.zeros(n, np.int8)
    n_valid_window = np.zeros(n, np.int8)
    mid_month = np.array([m.month for m in mids])
    p_sum = np.full(n, np.nan, np.float32)
    t_mean = np.full(n, np.nan, np.float32)
    p_anom = np.full(n, np.nan, np.float32)
    t_anom = np.full(n, np.nan, np.float32)
    W = load_weather()
    lon = df["centroid_lon"].values.astype(np.float64)
    lat = df["centroid_lat"].values.astype(np.float64)
    rc_p = rowcol(W["chirps_transform"], lon, lat, W["chirps"].shape[1:])
    rc_t = rowcol(W["tmean_transform"], lon, lat, W["tmean"].shape[1:])
    for (s, e) in {(int(a), int(b)) for a, b in zip(starts, ends)}:
        sel = (starts == s) & (ends == e)
        months = window_months(s, e)
        cols = np.isin(mid_month, months)
        Fw = F[sel][:, cols]
        with np.errstate(all="ignore"):
            integral[sel] = np.nansum(excess[sel][:, cols] * dt[None, cols], axis=1)
            peak[sel] = np.nanmax(Fw, axis=1)
            am = np.nanargmax(np.where(np.isnan(Fw), -np.inf, Fw), axis=1)
        wsd = window_start_date(s, ay)
        offs = np.array([(mids[j] - wsd).days / DAYS_PER_MONTH for j in np.flatnonzero(cols)], dtype=np.float32)
        tpeak[sel] = offs[am]
        n_window[sel] = int(cols.sum())
        n_valid_window[sel] = (~np.isnan(R[sel][:, cols])).sum(axis=1)
        # weather
        tgt, mean, sd = window_weather("chirps", months, ay)
        r, c_, inside = rc_p
        with np.errstate(all="ignore"):
            v = np.where(inside, tgt[r, c_], np.nan)
            a = (v - mean[r, c_]) / sd[r, c_]
        p_sum[sel] = v[sel]
        p_anom[sel] = np.where(np.isfinite(a), a, np.nan)[sel]
        tgt, mean, sd = window_weather("tmean", months, ay)
        r, c_, inside = rc_t
        with np.errstate(all="ignore"):
            v = np.where(inside, tgt[r, c_], np.nan)
            a = (v - mean[r, c_]) / sd[r, c_]
        t_mean[sel] = v[sel]
        t_anom[sel] = np.where(np.isfinite(a), a, np.nan)[sel]
    integral[no_data] = np.nan
    peak[no_data] = np.nan
    tpeak[no_data] = np.nan

    h6 = C.h3_cells(lat, lon, 6)
    out = pd.DataFrame({
        "fid": df["fid"].values.astype(np.int64),
        "area_ha": df["area_ha"].values.astype(np.float32),
        "cls": cls,
        "peer_cls": np.array([C.PEER_CLASS.get(int(c), -1) for c in cls], dtype=np.int16),
        "ag": ag,
        "muni_code": C.muni_to_int(df["muni_code"]),
        "state_uf": uf,
        "lon": lon.astype(np.float32),
        "lat": lat.astype(np.float32),
        "h3_6": h6,
        "h3_5": C.h3_parent(h6, 5),
        "h3_4": C.h3_parent(h6, 4),
        "h3_3": C.h3_parent(h6, 3),
        "small_field": df["small_field"].values.astype(bool),
        "n_cells": df["n_cells"].values.astype(np.int32),
        "dominant_share": df["dominant_share"].values.astype(np.float32),
        "window_start": starts,
        "window_end": ends,
        "n_window": n_window,
        "n_valid_window": n_valid_window,
        "n_valid_year": (df[nvy[0]].values if nvy else (~np.isnan(R)).sum(axis=1)).astype(np.int8),
        "baseline": baseline.astype(np.float32),
        "integral": integral,
        "peak": peak,
        "tpeak": tpeak,
        "annual": annual.astype(np.float32),
        "p_sum": p_sum,
        "t_mean": t_mean,
        "p_anom": p_anom,
        "t_anom": t_anom,
    })
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    table = pa.Table.from_pandas(out, preserve_index=False)
    meta = dict(table.schema.metadata or {})
    meta[b"s04_metrics"] = json.dumps({"source": source, "polys": polys, "ay": ay, "state": state, "ndvi_table": p_ndvi,
                                       "baseline_ays": BASELINE_AYS, "written": datetime.now().isoformat(timespec="seconds")}).encode()
    pq.write_table(table.replace_schema_metadata(meta), out_path + ".part", compression="zstd")
    os.replace(out_path + ".part", out_path)
    ok = ag & ~no_data
    return {"state": state, "status": "ok", "rows": int(n), "ag": int(ag.sum()), "no_data": int(no_data.sum()),
            "half_window_fail": int((n_valid_window[ok] < 0.5 * n_window[ok]).sum()),
            "weather_nan": int(np.isnan(p_anom).sum()),
            "median_integral": float(np.nanmedian(integral[ok])) if ok.any() else None,
            "seconds": round(time.time() - t0, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["modis", "s2"], default="modis")
    ap.add_argument("--polys", type=int, default=2024)
    ap.add_argument("--ay", type=int, default=2024)
    ap.add_argument("--states", nargs="*", default=None)
    ap.add_argument("--ndvi-root", default=None, help="alternative root holding year=<polys>\\state=<S> NDVI tables")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    states = args.states or C.state_dirs(args.polys)
    # largest states first so the pool stays busy
    sizes = {s: os.path.getsize(C.fields_path(args.polys, s)) for s in states}
    states = sorted(states, key=lambda s: -sizes[s])
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(compute_state, args.source, args.polys, args.ay, s, args.ndvi_root, args.force): s for s in states}
        for f in as_completed(futs):
            try:
                r = f.result()
            except Exception as e:  # noqa: BLE001
                r = {"state": futs[f], "status": "fail", "error": repr(e)[:400]}
            print(json.dumps(r), flush=True)
    print(f"done in {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
