"""Stage 4b: peer-relative and weather-adjusted productivity (METHODS.md section 5).

  python s04_relative.py --source modis --polys 2024            fit layer 2 on both years, apply to both
  python s04_relative.py --source modis --polys 2020            apply the saved fit to the 2020 polygons

Reads every state's metrics table of the polygon year (s04_metrics.py) for the agricultural
years present, so peer groups that straddle a state border pool the fields of both states.

Validity gate: a field enters a peer group when its class is agricultural and at least half
of the composites inside its window have a raw value (`n_valid_window >= 0.5 n_window`).
Everything else gets no relative value for that year.

Layer 1. Peer group = (H3 cell of the centroid, peer class, year), where the peer class is
the MapBiomas class with 19 and 41 pooled. A field uses its resolution 5 cell when that cell
holds at least 30 valid fields of the class, else the resolution 4 cell, else the resolution
3 cell, else it has no group. R1 = (M - median_g(M)) / (1.4826 MAD_g(M)), with M the seasonal
integral. A group whose MAD is zero (fields that share one MODIS cell) gives no R1.

Layer 2. Per peer class and state, the medians of the peer groups of both years are
regressed on the group mean precipitation and temperature anomalies (clipped to plus or minus
3 SD) with quadratic terms: median = a + b1 P + b2 T + b3 P^2 + b4 T^2. Ordinary least
squares by numpy. Three guards keep the correction from inventing values where the design
cannot support it: a class x state is fitted only with at least 30 groups and both years (one
year alone has almost no anomaly spread inside a state, so the quadratic is ill-posed and a
dev run gave an intercept of -68 for Mato Grosso sugarcane), the term is evaluated with the
field's anomalies clipped to the range of group anomalies the fit saw (no extrapolation), and
the term is capped at half the intercept in absolute value. The coefficients, R^2 and the
anomaly ranges go to data/summaries/weather_fit.csv. At field level the fitted weather term,
from the field's own anomalies (NaN anomalies count as zero), is removed:
M* = M - (b1 P + b2 T + b3 P^2 + b4 T^2), and layer 1 is recomputed on M* in the same
groups, giving r_adj. The site's scale is prod = M* / median_g(M*), 1.0 at the peer median,
clipped to 0 to 5.

Output per state: analysis\\relative\\source=<src>\\polys=<polys>\\ay=<ay>\\<State>.parquet with
fid, valid, group_level (5, 4, 3 or 0), group_n, metric, r1, metric_adj, r_adj, prod,
peer_median_adj. The fit is stored at analysis\\relative\\source=<src>\\weather_fit.json and
copied to data/summaries/weather_fit.csv.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s04_common as C  # noqa: E402

MIN_GROUP = 30
MIN_FIT_GROUPS = 30
MIN_FIT_YEARS = 2
TERM_CAP_SHARE = 0.5
ANOM_CLIP = 3.0
PROD_MAX = 5.0
COLS = ["fid", "peer_cls", "ag", "state_uf", "h3_5", "h3_4", "h3_3", "n_window", "n_valid_window",
        "integral", "p_anom", "t_anom"]


def load_year(source, polys, ay, states):
    frames = []
    for s in states:
        p = C.metrics_path(source, polys, ay, s)
        if not os.path.exists(p):
            raise FileNotFoundError(p)
        df = pq.read_table(p, columns=COLS).to_pandas()
        df["state"] = s
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["state"] = df["state"].astype("category")
    df["state_uf"] = df["state_uf"].astype("category")
    df["valid"] = (df["ag"].values & np.isfinite(df["integral"].values)
                   & (df["n_valid_window"].values >= 0.5 * df["n_window"].values))
    return df


def assign_groups(df):
    """Group cell per field after the 30-field rule, and the resolution level used."""
    valid = df["valid"].values
    cls = df["peer_cls"].values
    level = np.zeros(len(df), np.int8)
    cell = np.zeros(len(df), np.int64)
    for res in (5, 4, 3):
        key = pd.DataFrame({"c": df[f"h3_{res}"].values, "k": cls})
        cnt = key[valid].groupby(["c", "k"], sort=False).size()
        idx = pd.MultiIndex.from_arrays([key["c"].values, key["k"].values])
        n = cnt.reindex(idx).fillna(0).values
        take = valid & (level == 0) & (n >= MIN_GROUP)
        level[take] = res
        cell[take] = df[f"h3_{res}"].values[take]
    return level, cell


def group_stats(df, metric_col):
    """Median, robust SD and size of each (cell, peer_cls) group over valid grouped fields."""
    g = df.loc[df["level"] > 0, ["cell", "peer_cls", metric_col]]
    grp = g.groupby(["cell", "peer_cls"], sort=False)[metric_col]
    med = grp.transform("median")
    dev = (g[metric_col] - med).abs()
    mad = dev.groupby([g["cell"], g["peer_cls"]], sort=False).transform("median")
    out = pd.DataFrame({"median": np.nan, "sd": np.nan, "n": 0}, index=df.index)
    out.loc[g.index, "median"] = med.values
    out.loc[g.index, "sd"] = 1.4826 * mad.values
    out.loc[g.index, "n"] = grp.transform("size").values
    return out


def relative(metric, stats):
    with np.errstate(all="ignore"):
        r = (metric - stats["median"].values) / stats["sd"].values
    r[~np.isfinite(r)] = np.nan
    return r.astype(np.float32)


def fit_weather(frames):
    """Layer 2 coefficients per (state_uf, peer_cls) from the group medians of every year given."""
    rows = []
    for ay, df in frames.items():
        g = df.loc[df["level"] > 0, ["cell", "peer_cls", "state_uf", "integral", "p_anom", "t_anom"]].copy()
        g["p_anom"] = g["p_anom"].clip(-ANOM_CLIP, ANOM_CLIP)
        g["t_anom"] = g["t_anom"].clip(-ANOM_CLIP, ANOM_CLIP)
        agg = g.groupby(["state_uf", "peer_cls", "cell"], observed=True).agg(
            median=("integral", "median"), p=("p_anom", "mean"), t=("t_anom", "mean"), n=("integral", "size")).reset_index()
        agg["ay"] = ay
        rows.append(agg)
    groups = pd.concat(rows, ignore_index=True)
    fits = []
    for (uf, cls), sub in groups.groupby(["state_uf", "peer_cls"], observed=True):
        sub = sub[np.isfinite(sub["p"]) & np.isfinite(sub["t"]) & np.isfinite(sub["median"])]
        n = len(sub)
        rec = {"state_uf": uf, "peer_cls": int(cls), "n_groups": int(n), "n_years": int(sub["ay"].nunique()),
               "a": float(sub["median"].mean()) if n else np.nan, "b1": 0.0, "b2": 0.0, "b3": 0.0, "b4": 0.0,
               "r2": np.nan, "fitted": False,
               "p_min": float(sub["p"].min()) if n else np.nan, "p_max": float(sub["p"].max()) if n else np.nan,
               "t_min": float(sub["t"].min()) if n else np.nan, "t_max": float(sub["t"].max()) if n else np.nan,
               "p_anom_mean_2020": float(sub.loc[sub.ay == 2020, "p"].mean()) if (sub.ay == 2020).any() else np.nan,
               "p_anom_mean_2024": float(sub.loc[sub.ay == 2024, "p"].mean()) if (sub.ay == 2024).any() else np.nan,
               "t_anom_mean_2020": float(sub.loc[sub.ay == 2020, "t"].mean()) if (sub.ay == 2020).any() else np.nan,
               "t_anom_mean_2024": float(sub.loc[sub.ay == 2024, "t"].mean()) if (sub.ay == 2024).any() else np.nan}
        if n >= MIN_FIT_GROUPS and sub["ay"].nunique() >= MIN_FIT_YEARS:
            P, T, y = sub["p"].values, sub["t"].values, sub["median"].values
            X = np.column_stack([np.ones(n), P, T, P ** 2, T ** 2])
            beta, _, rank, _ = np.linalg.lstsq(X, y, rcond=None)
            pred = X @ beta
            ss_res = float(((y - pred) ** 2).sum())
            ss_tot = float(((y - y.mean()) ** 2).sum())
            rec.update({"a": float(beta[0]), "b1": float(beta[1]), "b2": float(beta[2]), "b3": float(beta[3]),
                        "b4": float(beta[4]), "r2": 1 - ss_res / ss_tot if ss_tot > 0 else np.nan,
                        "rank": int(rank), "fitted": True})
        fits.append(rec)
    return pd.DataFrame(fits)


def apply_weather(df, fit):
    key = pd.MultiIndex.from_arrays([df["state_uf"].astype(str).values, df["peer_cls"].values])
    f = fit.set_index(["state_uf", "peer_cls"])
    ff = f.reindex(key)
    b = ff[["b1", "b2", "b3", "b4"]].fillna(0.0).values
    P = np.nan_to_num(np.clip(df["p_anom"].values, -ANOM_CLIP, ANOM_CLIP))
    T = np.nan_to_num(np.clip(df["t_anom"].values, -ANOM_CLIP, ANOM_CLIP))
    # no extrapolation beyond the group anomalies the fit saw
    P = np.clip(P, np.nan_to_num(ff["p_min"].values, nan=-ANOM_CLIP), np.nan_to_num(ff["p_max"].values, nan=ANOM_CLIP))
    T = np.clip(T, np.nan_to_num(ff["t_min"].values, nan=-ANOM_CLIP), np.nan_to_num(ff["t_max"].values, nan=ANOM_CLIP))
    term = b[:, 0] * P + b[:, 1] * T + b[:, 2] * P ** 2 + b[:, 3] * T ** 2
    cap = TERM_CAP_SHARE * np.abs(np.nan_to_num(ff["a"].values, nan=0.0))
    capped = np.abs(term) > cap
    term = np.clip(term, -cap, cap)
    apply_weather.capped = int(capped.sum())
    return (df["integral"].values - term).astype(np.float32)


def write_year(source, polys, ay, df, stats_adj):
    out_dir = os.path.join(C.RELATIVE, f"source={source}", f"polys={polys}", f"ay={ay}")
    os.makedirs(out_dir, exist_ok=True)
    with np.errstate(all="ignore"):
        prod = df["metric_adj"].values / stats_adj["median"].values
    prod = np.where(np.isfinite(prod) & (stats_adj["median"].values > 0), np.clip(prod, 0, PROD_MAX), np.nan).astype(np.float32)
    df["prod"] = prod
    df["peer_median_adj"] = stats_adj["median"].values.astype(np.float32)
    df["group_n"] = stats_adj["n"].values.astype(np.int32)
    summary = {}
    for s, sub in df.groupby("state", observed=True, sort=True):
        out = pd.DataFrame({"fid": sub["fid"].values, "valid": sub["valid"].values, "group_level": sub["level"].values,
                            "group_n": sub["group_n"].values, "metric": sub["integral"].values.astype(np.float32),
                            "r1": sub["r1"].values, "metric_adj": sub["metric_adj"].values, "r_adj": sub["r_adj"].values,
                            "prod": sub["prod"].values, "peer_median_adj": sub["peer_median_adj"].values})
        table = pa.Table.from_pandas(out, preserve_index=False)
        meta = dict(table.schema.metadata or {})
        meta[b"s04_relative"] = json.dumps({"source": source, "polys": polys, "ay": ay, "state": s,
                                            "written": datetime.now().isoformat(timespec="seconds")}).encode()
        p = os.path.join(out_dir, f"{s}.parquet")
        pq.write_table(table.replace_schema_metadata(meta), p + ".part", compression="zstd")
        os.replace(p + ".part", p)
        summary[s] = {"rows": int(len(out)), "valid": int(out["valid"].sum()), "grouped": int((out["group_level"] > 0).sum()),
                      "level5": int((out["group_level"] == 5).sum()), "level4": int((out["group_level"] == 4).sum()),
                      "level3": int((out["group_level"] == 3).sum()), "prod_median": float(np.nanmedian(out["prod"])) if out["prod"].notna().any() else None}
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["modis", "s2"], default="modis")
    ap.add_argument("--polys", type=int, default=2024)
    ap.add_argument("--ays", type=int, nargs="*", default=None)
    ap.add_argument("--states", nargs="*", default=None)
    ap.add_argument("--fit-from", default=None, help="weather_fit.json to apply instead of fitting")
    ap.add_argument("--no-summary-copy", action="store_true", help="do not write data/summaries/weather_fit.csv")
    args = ap.parse_args()
    t0 = time.time()
    states = args.states or C.state_dirs(args.polys)
    ays = args.ays or [a for a in C.AG_YEARS if os.path.isdir(os.path.join(C.METRICS, f"source={args.source}", f"polys={args.polys}", f"ay={a}"))]
    frames = {}
    for ay in ays:
        df = load_year(args.source, args.polys, ay, states)
        level, cell = assign_groups(df)
        df["level"] = level
        df["cell"] = cell
        st = group_stats(df, "integral")
        df["r1"] = relative(df["integral"].values, st)
        frames[ay] = df
        print(json.dumps({"ay": ay, "rows": len(df), "valid": int(df["valid"].sum()), "grouped": int((level > 0).sum()),
                          "seconds": round(time.time() - t0)}), flush=True)
    fit_dir = os.path.join(C.RELATIVE, f"source={args.source}")
    os.makedirs(fit_dir, exist_ok=True)
    fit_path = args.fit_from or os.path.join(fit_dir, "weather_fit.json")
    if args.fit_from or (args.polys != 2024 and os.path.exists(fit_path)):
        fit = pd.read_json(fit_path, orient="records")
        print(f"applying fit from {fit_path}", flush=True)
    else:
        fit = fit_weather(frames)
        fit.to_json(fit_path, orient="records", indent=1)
        if not args.no_summary_copy:
            os.makedirs(C.SUMMARIES, exist_ok=True)
            cols = ["state_uf", "peer_cls", "n_groups", "n_years", "a", "b1", "b2", "b3", "b4", "r2", "fitted",
                    "p_anom_mean_2020", "p_anom_mean_2024", "t_anom_mean_2020", "t_anom_mean_2024",
                    "p_min", "p_max", "t_min", "t_max"]
            fit[cols].sort_values(["state_uf", "peer_cls"]).to_csv(os.path.join(C.SUMMARIES, "weather_fit.csv"), index=False, float_format="%.5g")
        fitted = fit[fit["fitted"]]
        print(json.dumps({"fit_rows": len(fit), "fitted": int(fit["fitted"].sum()),
                          "r2_median": float(fitted["r2"].median()) if len(fitted) else None,
                          "r2_above_0.5": int((fitted["r2"] > 0.5).sum())}), flush=True)
    report = {}
    for ay, df in frames.items():
        df["metric_adj"] = apply_weather(df, fit)
        print(json.dumps({"ay": ay, "term_capped_fields": apply_weather.capped}), flush=True)
        st = group_stats(df, "metric_adj")
        df["r_adj"] = relative(df["metric_adj"].values, st)
        report[ay] = write_year(args.source, args.polys, ay, df, st)
        print(json.dumps({"ay": ay, "written": len(report[ay]), "seconds": round(time.time() - t0)}), flush=True)
    with open(os.path.join(fit_dir, f"relative_summary_polys={args.polys}.json"), "w") as fh:
        json.dump(report, fh, indent=1)
    print(f"done in {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
