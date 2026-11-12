"""Stage 3h: assemble the per-tile Sentinel-2 rows into one table per state and field year.

Reads the per-tile parquets written by s03g_s2_fetch_reduce.py
(extracted\\s2\\tiles\\<tile_id>.parquet: fid, year_layer, state, period, ndvi_max, n_clear,
w_valid, w_total) for every tile the tile index lists for the state, and writes

  F:\\relative-land-productivity-data\\extracted\\s2\\year=<YYYY>\\state=<State>\\ndvi_monthly.parquet

with one row per field of that year's layer and the columns

  fid
  ndvi_<YYYY-MM>          24 columns, 2019-09 .. 2020-08 and 2023-09 .. 2024-08: the
                          coverage-weighted mean of the pixel monthly maximum NDVI over the
                          field's valid pixels. A field that spans tiles is combined across
                          tiles by its valid coverage weight. Missing (NaN) when under half
                          of the field's coverage weight had a valid composite that month.
  ndvi_<YYYY-MM>_filled   the same with missing months filled by linear interpolation in
                          time inside each agricultural year; a missing first or last month
                          takes the nearest valid value. All NaN when the year has no valid
                          month.
  nclear_<YYYY-MM>        coverage-weighted mean count of clear observations per pixel.
  n_valid_2020, n_valid_2024    valid months out of 12 per agricultural year.
  nclear_2020, nclear_2024      mean of nclear over the 12 months.
  n_tiles                 tiles the field's rows came from.
  n_months_present        tile-months found for the field (24 x n_tiles when complete).

A sidecar ndvi_monthly.meta.json records how many of the state's tiles were complete when
the file was written. Tiles still being fetched are included as they are, so the output of
a partial run is usable for checks; rerun after the fetch finishes.

Environment: either project Python works (pandas, pyarrow, numpy).

Usage:
  python s03h_s2_assemble.py --state Mato_Grosso [--year 2024] [--check]
  python s03h_s2_assemble.py --tier 1
"""
import argparse
import glob
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s03g_weights as wts  # noqa: E402

DATA = wts.DATA
TILES_OUT = os.path.join(DATA, "extracted", "s2", "tiles")
OUT_ROOT = os.path.join(DATA, "extracted", "s2")
AG_YEARS = {2020: ("2019-09-01", "2020-08-31"), 2024: ("2023-09-01", "2024-08-31")}


def periods_of(year):
    s, e = AG_YEARS[year]
    return pd.date_range(s, e, freq="MS").strftime("%Y-%m").tolist()


PERIODS = {y: periods_of(y) for y in AG_YEARS}
ALL_PERIODS = PERIODS[2020] + PERIODS[2024]


def read_state_rows(state, year_layer):
    tiles = wts.tiles_for_states([state])
    parts, complete = [], 0
    for tid in tiles:
        p = os.path.join(TILES_OUT, f"{tid}.parquet")
        if not os.path.exists(p):
            continue
        t = pq.read_table(p, filters=[("year_layer", "==", year_layer), ("state", "==", state)])
        if t.num_rows == 0:
            n_periods = len(pq.read_table(p, columns=["period"]).column("period").unique())
            complete += int(n_periods >= len(ALL_PERIODS))
            continue
        df = t.to_pandas()
        df["tile_id"] = tid
        complete += int(df["period"].nunique() >= len(ALL_PERIODS))
        parts.append(df[["fid", "period", "ndvi_max", "n_clear", "w_valid", "w_total", "tile_id"]])
    meta = {"state": state, "year_layer": year_layer, "tiles": len(tiles), "tiles_with_output": len(parts),
            "tiles_complete": complete}
    if not parts:
        return None, meta
    return pd.concat(parts, ignore_index=True), meta


def combine(rows):
    """One row per fid and period, combined across tiles by coverage weight."""
    rows = rows.copy()
    rows["wv_ndvi"] = rows["ndvi_max"].fillna(0).astype(np.float64) * rows["w_valid"]
    rows["wt_ncl"] = rows["n_clear"].fillna(0).astype(np.float64) * rows["w_total"]
    g = rows.groupby(["fid", "period"], sort=False).agg(
        wv_ndvi=("wv_ndvi", "sum"), w_valid=("w_valid", "sum"),
        wt_ncl=("wt_ncl", "sum"), w_total=("w_total", "sum"))
    with np.errstate(invalid="ignore", divide="ignore"):
        g["ndvi"] = np.where(g["w_valid"] > 0, g["wv_ndvi"] / g["w_valid"], np.nan)
        g["nclear"] = np.where(g["w_total"] > 0, g["wt_ncl"] / g["w_total"], np.nan)
        valid_frac = np.where(g["w_total"] > 0, g["w_valid"] / g["w_total"], 0.0)
    g.loc[valid_frac < 0.5, "ndvi"] = np.nan
    return g[["ndvi", "nclear"]].reset_index()


def fill_year(a):
    """Linear interpolation along axis 1 inside one year; ends take the nearest value."""
    out = a.copy()
    n = a.shape[1]
    x = np.arange(n)
    for i in np.where(np.isnan(a).any(axis=1) & ~np.isnan(a).all(axis=1))[0]:
        ok = ~np.isnan(a[i])
        out[i] = np.interp(x, x[ok], a[i, ok])
    return out


def assemble(state, year_layer):
    t0 = time.time()
    rows, meta = read_state_rows(state, year_layer)
    if rows is None:
        print(f"{state} {year_layer}: no tile output yet", flush=True)
        return None
    n_tiles = rows.groupby("fid")["tile_id"].nunique()
    n_present = rows.groupby("fid").size()
    g = combine(rows)
    del rows
    ndvi = g.pivot(index="fid", columns="period", values="ndvi").reindex(columns=ALL_PERIODS)
    ncl = g.pivot(index="fid", columns="period", values="nclear").reindex(columns=ALL_PERIODS)
    out = pd.DataFrame(index=ndvi.index)
    for p in ALL_PERIODS:
        out[f"ndvi_{p}"] = ndvi[p].astype(np.float32)
    for y in AG_YEARS:
        a = ndvi[PERIODS[y]].values.astype(np.float64)
        f = fill_year(a)
        for j, p in enumerate(PERIODS[y]):
            out[f"ndvi_{p}_filled"] = f[:, j].astype(np.float32)
    for p in ALL_PERIODS:
        out[f"nclear_{p}"] = ncl[p].astype(np.float32)
    for y in AG_YEARS:
        out[f"n_valid_{y}"] = ndvi[PERIODS[y]].notna().sum(axis=1).astype(np.int8)
        out[f"nclear_{y}"] = ncl[PERIODS[y]].mean(axis=1).astype(np.float32)
    out["n_tiles"] = n_tiles.reindex(out.index).astype(np.int8)
    out["n_months_present"] = n_present.reindex(out.index).astype(np.int16)
    out = out.reset_index()
    d = os.path.join(OUT_ROOT, f"year={year_layer}", f"state={state}")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "ndvi_monthly.parquet")
    out.to_parquet(p + ".part", index=False, compression="zstd")
    os.replace(p + ".part", p)
    meta.update({"fields": int(len(out)), "seconds": round(time.time() - t0, 1),
                 "written": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "share_fields_under_8_valid_months": {
                     str(y): round(float((out[f"n_valid_{y}"] < 8).mean()), 4) for y in AG_YEARS}})
    with open(os.path.join(d, "ndvi_monthly.meta.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    print(json.dumps(meta), flush=True)
    return p


def check(state, year_layer):
    """Sanity numbers: class medians for January and the valid-month shares."""
    p = os.path.join(OUT_ROOT, f"year={year_layer}", f"state={state}", "ndvi_monthly.parquet")
    out = pd.read_parquet(p)
    fp = os.path.join(wts.FIELDS_DIR, f"year={year_layer}", f"state={state}", "fields.parquet")
    f = pq.read_table(fp, columns=["fid", "crop_group", "area_ha"]).to_pandas()
    m = out.merge(f, on="fid", how="left")
    rep = {"state": state, "year_layer": year_layer, "fields": int(len(m))}
    for col in [c for c in ("ndvi_2024-01", "ndvi_2020-01", "ndvi_2024-02", "ndvi_2020-02") if c in m]:
        med = m.groupby("crop_group")[col].median().round(3)
        cnt = m.groupby("crop_group")[col].count()
        rep[col] = {k: {"median": float(med[k]), "n": int(cnt[k])} for k in med.index}
    for y in AG_YEARS:
        rep[f"share_under_8_valid_{y}"] = round(float((m[f"n_valid_{y}"] < 8).mean()), 4)
        rep[f"n_valid_{y}_hist"] = m[f"n_valid_{y}"].value_counts().sort_index().to_dict()
    print(json.dumps(rep, indent=1, default=str))
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", action="append")
    ap.add_argument("--tier", action="append", type=int)
    ap.add_argument("--year", type=int, action="append", help="field layer year, default both")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    states = list(a.state or [])
    for t in a.tier or []:
        states += wts.TIER_STATES[t]
    if not states:
        sys.exit("give --state or --tier")
    years = a.year or list(AG_YEARS)
    for st in states:
        for y in years:
            if assemble(st, y) and a.check:
                check(st, y)


if __name__ == "__main__":
    main()
