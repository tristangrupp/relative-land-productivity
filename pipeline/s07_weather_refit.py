"""Stage 7a: refit the layer 2 weather term per ecoregion and peer class, with the long-run mean
precipitation of the field's location as an extra regressor, and test whether it removes the
weather-shaped blocks of the area term (pipeline/EXPLORE_ECOREGIONS.md, pipeline/DECISIONS_V2.md).

  python s07_weather_refit.py pclim      long-run mean annual CHIRPS precipitation per field (2024 and 2020 polygons)
  python s07_weather_refit.py compare    fit both designs, score the area term under each, write the comparison
  python s07_weather_refit.py apply      write the relative tables on the new fit (only if compare says it helps)

The existing fit (s04_relative.py) is per state and peer class, on the peer-group medians of
both years: median = a + b1 P + b2 T + b3 P^2 + b4 T^2, with P and T the window precipitation and
temperature anomalies in baseline SD. The refit keeps the same form and adds b5 (Pc - Pc0):
Pc is the field's mean annual CHIRPS precipitation over the nine agricultural years 2016 to 2024
(September 2015 to August 2024), in meters, and Pc0 the mean of Pc over the groups the fit saw,
so the intercept stays the level at the unit's mean climate and the cap at half the intercept
keeps its meaning. The unit is the RESOLVE 2017 ecoregion instead of the state. The guards are
those of s04_relative: at least 30 groups and both years, P, T and Pc clipped to the range the
fit saw, the term capped at half the intercept in absolute value. An ecoregion and class that
cannot be fitted falls back to the state and class fit, so no field loses the correction it had.

Comparison of the two designs (compare):
  1. R squared of each fit over the group medians, median and group-weighted.
  2. The area term (cell against ecoregion, s06_ecoregion_peers.score_year) under each fit, its
     2024 minus 2020 change class-weighted per H3 resolution 5 cell, and three block measures:
     Moran's I over the ring-1 neighbors, the correlation of a cell with the mean of its ring-k
     neighbors for k = 1, 2, 4, 8 (about 15, 30, 60 and 120 km), and the correlation of the
     cell's change with the change in its mean precipitation anomaly (2024 minus 2020).
Written to analysis\\weather_refit\\ and data/summaries/weather_refit_compare.json.

apply writes analysis\\relative\\source=modis\\polys=<2024|2020>\\ay=<ay>\\<State>.parquet on the
new fit after copying the existing tables and weather_fit.json to analysis\\relative_v1\\.
Downstream: rerun s04_change.py --force, s06_ecoregion_peers.py score.
"""
import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s04_common as C  # noqa: E402
import s04_relative as R  # noqa: E402

SOURCE = "modis"
OUT = os.path.join(C.ANALYSIS, "weather_refit")
ECO = os.path.join(C.ANALYSIS, "ecoregions")
CLIM_AYS = list(range(2016, 2025))  # September of the year before to August
OLD_FIT = os.path.join(C.RELATIVE, f"source={SOURCE}", "weather_fit.json")
NEW_FIT = os.path.join(OUT, "weather_fit_eco.json")


def log(**kw):
    kw["t"] = datetime.now().isoformat(timespec="seconds")
    print(json.dumps(kw, ensure_ascii=False, default=str), flush=True)


# ----------------------------------------------------------------------------- pclim

def pclim_raster():
    import rasterio
    total = None
    for ay in CLIM_AYS:
        for m in list(range(9, 13)) + list(range(1, 9)):
            y = ay - 1 if m >= 9 else ay
            with rasterio.open(os.path.join(C.WEATHER, "chirps", f"{y}-{m:02d}.tif")) as src:
                a = src.read(1).astype(np.float64)
                a[a == src.nodata] = np.nan
                tr = src.transform
            total = a if total is None else total + a
    return (total / len(CLIM_AYS) / 1000.0).astype(np.float32), tr  # meters per year


def sample(grid, tr, lon, lat):
    col = np.floor((lon - tr.c) / tr.a).astype(np.int64)
    row = np.floor((lat - tr.f) / tr.e).astype(np.int64)
    ok = (row >= 0) & (row < grid.shape[0]) & (col >= 0) & (col < grid.shape[1])
    out = np.full(len(lon), np.nan, np.float32)
    out[ok] = grid[row[ok], col[ok]]
    # a centroid on a nodata coast pixel takes the mean of its 3 x 3 neighborhood
    miss = ok & ~np.isfinite(out)
    if miss.any():
        from scipy import ndimage
        g = np.where(np.isfinite(grid), grid, 0)
        w = ndimage.uniform_filter(np.isfinite(grid).astype(np.float32), 3)
        s = ndimage.uniform_filter(g, 3)
        with np.errstate(all="ignore"):
            sm = np.where(w > 0, s / w, np.nan)
        out[miss] = sm[row[miss], col[miss]]
    return out


def pclim(states_by_polys):
    t0 = time.time()
    grid, tr = pclim_raster()
    for polys, states in states_by_polys.items():
        d = os.path.join(OUT, "pclim", f"polys={polys}")
        os.makedirs(d, exist_ok=True)
        for s in states:
            m = pq.read_table(C.metrics_path(SOURCE, polys, polys, s), columns=["fid", "lon", "lat"]).to_pandas()
            v = sample(grid, tr, m["lon"].values, m["lat"].values)
            pq.write_table(pa.Table.from_pandas(pd.DataFrame({"fid": m["fid"].values, "pclim": v}), preserve_index=False),
                           os.path.join(d, f"{s}.parquet"), compression="zstd")
        log(step="pclim", polys=polys, states=len(states), seconds=round(time.time() - t0))


def read_concat(path_fn, states, cols):
    return pd.concat([pq.read_table(path_fn(s), columns=cols).to_pandas() for s in states], ignore_index=True)


def eco_for(polys, states):
    if polys == 2024:
        return read_concat(lambda s: os.path.join(ECO, "field_eco", f"{s}.parquet"), states, ["fid", "eco_id"])
    return read_concat(lambda s: os.path.join(OUT, "field_eco_2020", f"{s}.parquet"), states, ["fid", "eco_id"])


def assign_eco_2020(states):
    """Ecoregion of each 2020 polygon, by the same 0.005 degree grid as s06 (centroid cell, nearest within 0.05 degree)."""
    import s06_ecoregion_peers as E
    from scipy import ndimage
    grid = np.load(os.path.join(ECO, "eco_grid.npz"))["grid"]
    dist, (ri, ci) = ndimage.distance_transform_edt(grid == 0, return_indices=True)
    d = os.path.join(OUT, "field_eco_2020")
    os.makedirs(d, exist_ok=True)
    for s in states:
        m = pq.read_table(C.metrics_path(SOURCE, 2020, 2020, s), columns=["fid", "lon", "lat"]).to_pandas()
        row, col, inside = E.grid_index(m["lon"].values.astype(np.float64), m["lat"].values.astype(np.float64))
        eco = np.zeros(len(m), np.int32)
        eco[inside] = grid[row[inside], col[inside]]
        miss = inside & (eco == 0)
        if miss.any():
            near = grid[ri[row[miss], col[miss]], ci[row[miss], col[miss]]]
            ok = dist[row[miss], col[miss]] <= E.FILL_CELLS
            idx = np.where(miss)[0]
            eco[idx[ok]] = near[ok]
        pq.write_table(pa.Table.from_pandas(pd.DataFrame({"fid": m["fid"].values, "eco_id": eco}), preserve_index=False),
                       os.path.join(d, f"{s}.parquet"), compression="zstd")
    log(step="assign_eco_2020", states=len(states))


# ----------------------------------------------------------------------------- fit

def load(polys, ay, states):
    df = R.load_year(SOURCE, polys, ay, states)
    level, cell = R.assign_groups(df)
    df["level"] = level
    df["cell"] = cell
    e = eco_for(polys, states)
    assert np.array_equal(e["fid"].values, df["fid"].values), "ecoregion table order differs"
    df["eco_id"] = e["eco_id"].values
    pc = read_concat(lambda s: os.path.join(OUT, "pclim", f"polys={polys}", f"{s}.parquet"), states, ["fid", "pclim"])
    assert np.array_equal(pc["fid"].values, df["fid"].values), "pclim table order differs"
    df["pclim"] = pc["pclim"].values
    return df


def fit_eco(frames, with_pclim=True):
    """Layer 2 per (eco_id, peer_cls), optionally with the mean precipitation regressor."""
    rows = []
    for ay, df in frames.items():
        g = df.loc[(df["level"] > 0) & (df["eco_id"] > 0), ["cell", "peer_cls", "eco_id", "integral", "p_anom", "t_anom", "pclim"]].copy()
        g["p_anom"] = g["p_anom"].clip(-R.ANOM_CLIP, R.ANOM_CLIP)
        g["t_anom"] = g["t_anom"].clip(-R.ANOM_CLIP, R.ANOM_CLIP)
        agg = g.groupby(["eco_id", "peer_cls", "cell"], observed=True).agg(
            median=("integral", "median"), p=("p_anom", "mean"), t=("t_anom", "mean"), c=("pclim", "mean"),
            n=("integral", "size")).reset_index()
        agg["ay"] = ay
        rows.append(agg)
    groups = pd.concat(rows, ignore_index=True)
    fits = []
    for (eco, cls), sub in groups.groupby(["eco_id", "peer_cls"], observed=True):
        sub = sub[np.isfinite(sub["p"]) & np.isfinite(sub["t"]) & np.isfinite(sub["median"]) & np.isfinite(sub["c"])]
        n = len(sub)
        rec = {"eco_id": int(eco), "peer_cls": int(cls), "n_groups": int(n), "n_years": int(sub["ay"].nunique()),
               "a": float(sub["median"].mean()) if n else np.nan, "b1": 0.0, "b2": 0.0, "b3": 0.0, "b4": 0.0, "b5": 0.0,
               "c0": float(sub["c"].mean()) if n else np.nan, "r2": np.nan, "fitted": False,
               "p_min": float(sub["p"].min()) if n else np.nan, "p_max": float(sub["p"].max()) if n else np.nan,
               "t_min": float(sub["t"].min()) if n else np.nan, "t_max": float(sub["t"].max()) if n else np.nan,
               "c_min": float(sub["c"].min()) if n else np.nan, "c_max": float(sub["c"].max()) if n else np.nan}
        if n >= R.MIN_FIT_GROUPS and sub["ay"].nunique() >= R.MIN_FIT_YEARS:
            P, T, y = sub["p"].values, sub["t"].values, sub["median"].values
            Cc = sub["c"].values - rec["c0"]
            cols = [np.ones(n), P, T, P ** 2, T ** 2] + ([Cc] if with_pclim else [])
            X = np.column_stack(cols)
            beta, _, rank, _ = np.linalg.lstsq(X, y, rcond=None)
            pred = X @ beta
            ss_res = float(((y - pred) ** 2).sum())
            ss_tot = float(((y - y.mean()) ** 2).sum())
            rec.update({"a": float(beta[0]), "b1": float(beta[1]), "b2": float(beta[2]), "b3": float(beta[3]), "b4": float(beta[4]),
                        "b5": float(beta[5]) if with_pclim else 0.0, "r2": 1 - ss_res / ss_tot if ss_tot > 0 else np.nan,
                        "rank": int(rank), "fitted": True, "ss_res": ss_res, "ss_tot": ss_tot})
        fits.append(rec)
    return pd.DataFrame(fits)


def r2_state_fit(frames, fit):
    """The existing state fit's R squared, recomputed with ss_res and ss_tot so it can be pooled."""
    rows = []
    for ay, df in frames.items():
        g = df.loc[df["level"] > 0, ["cell", "peer_cls", "state_uf", "integral", "p_anom", "t_anom"]].copy()
        g["p_anom"] = g["p_anom"].clip(-R.ANOM_CLIP, R.ANOM_CLIP)
        g["t_anom"] = g["t_anom"].clip(-R.ANOM_CLIP, R.ANOM_CLIP)
        agg = g.groupby(["state_uf", "peer_cls", "cell"], observed=True).agg(
            median=("integral", "median"), p=("p_anom", "mean"), t=("t_anom", "mean")).reset_index()
        rows.append(agg)
    groups = pd.concat(rows, ignore_index=True)
    groups["state_uf"] = groups["state_uf"].astype(str)
    f = fit.set_index(["state_uf", "peer_cls"])
    out = []
    for (uf, cls), sub in groups.groupby(["state_uf", "peer_cls"], observed=True):
        if (uf, cls) not in f.index or not bool(f.loc[(uf, cls), "fitted"]):
            continue
        r = f.loc[(uf, cls)]
        sub = sub[np.isfinite(sub["p"]) & np.isfinite(sub["t"]) & np.isfinite(sub["median"])]
        P, T, y = sub["p"].values, sub["t"].values, sub["median"].values
        pred = r["a"] + r["b1"] * P + r["b2"] * T + r["b3"] * P ** 2 + r["b4"] * T ** 2
        out.append({"state_uf": uf, "peer_cls": int(cls), "n_groups": len(sub), "ss_res": float(((y - pred) ** 2).sum()),
                    "ss_tot": float(((y - y.mean()) ** 2).sum())})
    o = pd.DataFrame(out)
    o["r2"] = 1 - o["ss_res"] / o["ss_tot"]
    return o


def apply_eco(df, fit_eco_tab, fit_state):
    """metric_adj on the ecoregion fit; unfitted ecoregion-class pairs use the state fit."""
    key = pd.MultiIndex.from_arrays([df["eco_id"].values.astype(np.int64), df["peer_cls"].values.astype(np.int64)])
    f = fit_eco_tab[fit_eco_tab["fitted"]].set_index(["eco_id", "peer_cls"])
    ff = f.reindex(key)
    has = ff["fitted"].fillna(False).values.astype(bool)
    old = R.apply_weather(df, fit_state)  # the state-fit adjusted metric, for the fallback
    P = np.nan_to_num(np.clip(df["p_anom"].values, -R.ANOM_CLIP, R.ANOM_CLIP))
    T = np.nan_to_num(np.clip(df["t_anom"].values, -R.ANOM_CLIP, R.ANOM_CLIP))
    P = np.clip(P, ff["p_min"].fillna(-R.ANOM_CLIP).values, ff["p_max"].fillna(R.ANOM_CLIP).values)
    T = np.clip(T, ff["t_min"].fillna(-R.ANOM_CLIP).values, ff["t_max"].fillna(R.ANOM_CLIP).values)
    c0 = ff["c0"].fillna(0).values
    pc = df["pclim"].values.astype(np.float64)
    Cc = np.clip(np.nan_to_num(pc, nan=0.0), ff["c_min"].fillna(-1e9).values, ff["c_max"].fillna(1e9).values) - c0
    Cc = np.where(np.isfinite(pc), Cc, 0.0)  # no climate value: no climate term
    b = ff[["b1", "b2", "b3", "b4", "b5"]].fillna(0.0).values
    term = b[:, 0] * P + b[:, 1] * T + b[:, 2] * P ** 2 + b[:, 3] * T ** 2 + b[:, 4] * Cc
    cap = R.TERM_CAP_SHARE * np.abs(ff["a"].fillna(0.0).values)
    capped = has & (np.abs(term) > cap)
    term = np.clip(term, -cap, cap)
    new = (df["integral"].values - term).astype(np.float32)
    apply_eco.stats = {"fields": int(len(df)), "eco_fit": int(has.sum()), "state_fallback": int((~has).sum()), "capped": int(capped.sum())}
    return np.where(has, new, old).astype(np.float32)


# ----------------------------------------------------------------------------- compare

def area_term(frames, madj_col):
    """cell_vs_eco per (h3_5, eco, class) for both years under one adjusted metric, via s06.score_year."""
    import s06_ecoregion_peers as E
    a20, a24 = frames[2020], frames[2024]
    both = pd.DataFrame({"eco_id": a24["eco_id"].values, "h3_5": a24["h3_5"].values,
                         "cls_2020": a20["peer_cls"].values, "cls_2024": a24["peer_cls"].values,
                         "valid_2020": a20["valid"].values, "valid_2024": a24["valid"].values,
                         "m_2020": a20[madj_col].values, "m_2024": a24[madj_col].values})
    out = {}
    for ay in (2020, 2024):
        r_eco, cv, cell, eco_groups, nat = E.score_year(both, ay)
        out[ay] = (cell, eco_groups, cv)
    c20 = out[2020][0].rename(columns={"n_cell": "n_2020", "cell_vs_eco": "v20"})
    c24 = out[2024][0].rename(columns={"n_cell": "n_2024", "cell_vs_eco": "v24"})
    cell = c20[["h3_5", "eco_id", "cls", "n_2020", "v20"]].merge(c24[["h3_5", "eco_id", "cls", "n_2024", "v24"]],
                                                                 on=["h3_5", "eco_id", "cls"], how="outer")
    cell["change"] = cell["v24"] - cell["v20"]
    return cell, out


def cell_change(cell):
    c = cell[np.isfinite(cell["change"])].copy()
    c["w"] = c["n_2024"].fillna(0)
    c["wc"] = c["w"] * c["change"]
    g = c.groupby("h3_5").agg(wc=("wc", "sum"), w=("w", "sum"))
    return (g["wc"] / g["w"]).rename("change")


def block_measures(series, dp):
    """Moran's I (ring 1), ring-k neighbor correlation, and correlation with the cell's precipitation anomaly change."""
    import h3
    s = series.dropna()
    idx = {int(k): i for i, k in enumerate(s.index.values)}
    v = s.values.astype(np.float64)
    z = v - v.mean()
    res = {"cells": int(len(s))}
    strs = [h3.int_to_str(int(k)) for k in s.index.values]
    for k in (1, 2, 4, 8):
        nb_mean = np.full(len(v), np.nan)
        num = 0.0
        wsum = 0
        for i, hx in enumerate(strs):
            ring = [idx.get(h3.str_to_int(r)) for r in h3.grid_ring(hx, k)]
            ring = [j for j in ring if j is not None]
            if ring:
                nb_mean[i] = v[ring].mean()
                if k == 1:
                    num += z[i] * z[ring].sum()
                    wsum += len(ring)
        ok = np.isfinite(nb_mean)
        res[f"corr_ring{k}"] = float(np.corrcoef(v[ok], nb_mean[ok])[0, 1])
        if k == 1:
            res["morans_i_ring1"] = float((len(v) / wsum) * num / (z ** 2).sum())
    d = dp.reindex(s.index)
    ok = np.isfinite(d.values)
    res["corr_with_dp_anom"] = float(np.corrcoef(v[ok], d.values[ok])[0, 1])
    res["sd_change"] = float(np.std(v))
    res["iqr_change"] = [float(np.percentile(v, 25)), float(np.percentile(v, 75))]
    res["share_abs_gt_0.5"] = float((np.abs(v) > 0.5).mean())
    return res


def compare(states):
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    fit_state = pd.read_json(OLD_FIT, orient="records")
    frames = {}
    for ay in (2020, 2024):
        frames[ay] = load(2024, ay, states)
        frames[ay]["m_old"] = R.apply_weather(frames[ay], fit_state)
        log(step="compare", ay=ay, rows=len(frames[ay]), seconds=round(time.time() - t0))
    fit_new = fit_eco(frames, with_pclim=True)
    fit_anom = fit_eco(frames, with_pclim=False)
    fit_new.to_json(NEW_FIT, orient="records", indent=1)
    fit_anom.to_json(os.path.join(OUT, "weather_fit_eco_anom_only.json"), orient="records", indent=1)
    r2_old = r2_state_fit(frames, fit_state)

    def r2_summary(t):
        t = t[np.isfinite(t["r2"])] if "fitted" not in t else t[t["fitted"] & np.isfinite(t["r2"])]
        return {"pairs": int(len(t)), "r2_median": float(t["r2"].median()),
                "r2_pooled": float(1 - t["ss_res"].sum() / t["ss_tot"].sum()),
                "r2_group_weighted": float(np.average(t["r2"], weights=t["n_groups"])), "r2_above_0.5": int((t["r2"] > 0.5).sum())}
    res = {"fit": {"state_by_class_anomalies (current)": r2_summary(r2_old),
                   "ecoregion_by_class_anomalies": r2_summary(fit_anom),
                   "ecoregion_by_class_anomalies_plus_mean_precip": r2_summary(fit_new)}}
    log(step="compare", **res["fit"])
    for ay in (2020, 2024):
        frames[ay]["m_new"] = apply_eco(frames[ay], fit_new, fit_state)
        res[f"apply_{ay}"] = apply_eco.stats
        frames[ay]["m_anom"] = apply_eco(frames[ay], fit_anom, fit_state)
    # precipitation anomaly change per cell (mean over valid fields of both years)
    ok = frames[2024]["valid"].values & frames[2020]["valid"].values
    dpa = pd.Series(frames[2024]["p_anom"].values[ok] - frames[2020]["p_anom"].values[ok], index=frames[2024]["h3_5"].values[ok])
    dp = dpa.groupby(level=0).mean()
    res["blocks"] = {}
    cells = {}
    for name, col in (("current", "m_old"), ("ecoregion_anomalies", "m_anom"), ("ecoregion_anomalies_plus_mean_precip", "m_new")):
        cell, _ = area_term(frames, col)
        cells[name] = cell
        cc = cell_change(cell)
        res["blocks"][name] = block_measures(cc, dp)
        # the level term in 2024 as well: its gradient with mean precipitation
        lv = cell[np.isfinite(cell["v24"])].copy()
        lv["w"] = lv["n_2024"]
        g = lv.assign(wv=lv["w"] * lv["v24"]).groupby("h3_5").agg(wv=("wv", "sum"), w=("w", "sum"))
        lvl = g["wv"] / g["w"]
        pc_cell = pd.Series(frames[2024]["pclim"].values, index=frames[2024]["h3_5"].values).groupby(level=0).mean()
        ok2 = np.isfinite(pc_cell.reindex(lvl.index).values)
        res["blocks"][name]["level2024_corr_with_mean_precip"] = float(np.corrcoef(lvl.values[ok2], pc_cell.reindex(lvl.index).values[ok2])[0, 1])
        res["blocks"][name]["level2024_corr_ring4"] = block_measures(lvl, dp)["corr_ring4"]
        cell.to_parquet(os.path.join(OUT, f"cell_vs_eco_{name}.parquet"), index=False)
        log(step="compare", design=name, **res["blocks"][name], seconds=round(time.time() - t0))
    res["seconds"] = round(time.time() - t0)
    with open(os.path.join(OUT, "compare.json"), "w") as fh:
        json.dump(res, fh, indent=1)
    shutil.copy(os.path.join(OUT, "compare.json"), os.path.join(C.SUMMARIES, "weather_refit_compare.json"))
    cols = ["eco_id", "peer_cls", "n_groups", "n_years", "fitted", "a", "b1", "b2", "b3", "b4", "b5", "c0", "r2",
            "p_min", "p_max", "t_min", "t_max", "c_min", "c_max"]
    fit_new[cols].sort_values(["eco_id", "peer_cls"]).to_csv(os.path.join(C.SUMMARIES, "weather_fit_eco.csv"), index=False, float_format="%.5g")
    log(step="compare", done=True, seconds=res["seconds"])


# ----------------------------------------------------------------------------- apply

def apply(states24, states20):
    """Rewrite the relative tables on the ecoregion fit, keeping a copy of the state-fit tables."""
    t0 = time.time()
    backup = os.path.join(C.ANALYSIS, "relative_v1", f"source={SOURCE}")
    src = os.path.join(C.RELATIVE, f"source={SOURCE}")
    if not os.path.exists(backup):
        shutil.copytree(src, backup)
        log(step="apply", backup=backup)
    fit_state = pd.read_json(os.path.join(backup, "weather_fit.json"), orient="records")
    fit_new = pd.read_json(NEW_FIT, orient="records")
    for polys, states, ays in ((2024, states24, (2020, 2024)), (2020, states20, (2020,))):
        report = {}
        for ay in ays:
            df = load(polys, ay, states)
            st = R.group_stats(df, "integral")
            df["r1"] = R.relative(df["integral"].values, st)
            df["metric_adj"] = apply_eco(df, fit_new, fit_state)
            log(step="apply", polys=polys, ay=ay, **apply_eco.stats)
            st = R.group_stats(df, "metric_adj")
            df["r_adj"] = R.relative(df["metric_adj"].values, st)
            report[ay] = R.write_year(SOURCE, polys, ay, df, st)
            report[ay]["_apply"] = dict(apply_eco.stats)
            del df
            log(step="apply", polys=polys, ay=ay, written=len(report[ay]) - 1, seconds=round(time.time() - t0))
        with open(os.path.join(src, f"relative_summary_polys={polys}.json"), "w") as fh:
            json.dump(report, fh, indent=1)
    meta = {"design": "ecoregion by peer class, anomalies plus mean annual precipitation; state fit as fallback",
            "fit": NEW_FIT, "fallback": os.path.join(backup, "weather_fit.json"), "written": datetime.now().isoformat(timespec="seconds")}
    with open(os.path.join(src, "weather_fit_design.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    log(step="apply", done=True, seconds=round(time.time() - t0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["pclim", "compare", "apply"])
    args = ap.parse_args()
    s24 = C.state_dirs(2024)
    s20 = [s for s in C.state_dirs(2020) if os.path.exists(C.metrics_path(SOURCE, 2020, 2020, s))]
    if args.step == "pclim":
        pclim({2024: s24, 2020: s20})
        assign_eco_2020(s20)
    elif args.step == "compare":
        compare(s24)
    else:
        apply(s24, s20)


if __name__ == "__main__":
    main()
