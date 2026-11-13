"""Stage 4d: validation of the field metrics against IBGE PAM municipal yields (METHODS.md section 8).

  python s04_validate.py [--source modis] [--states ...] [--ays 2020 2024] [--download]

Yields: SIDRA table 5457, variable 112 (Rendimento medio da producao, kg per ha), every
municipality (n6/all), years 2020 and 2024, products 40124 soybean, 40122 maize, 40106
sugarcane, one request per product:
https://apisidra.ibge.gov.br/values/t/5457/n6/all/v/112/p/2020,2024/c782/<product>?formato=json
The raw answers are kept under analysis\\validation\\raw\\ and re-downloaded only with
--download. Values "-" (zero or not applicable) and "..." (not available) are dropped.

Field side, from the metrics and relative tables on the 2024 polygons: soybean is class 39,
sugarcane class 20, maize is classes 19 and 41 in the states where maize is the dominant
temporary crop by PAM 2023 harvested area (the dominant_other_crop_pam2023 column of
data/calendars/class_window_lookup.csv starts with "Milho"). Only fields that passed the
validity gate (half the window observed, agricultural class) count. Municipal means weighted
by area_ha of the raw seasonal integral and of prod are formed for municipalities with at
least 20 such fields.

Correlations: Spearman and Pearson of the municipal metric with yield per crop and year,
for Brazil and for every state with at least 20 municipalities, and of the municipal 2024
minus 2020 differences in prod (and in the integral) with the difference in yield.

Outputs: data/summaries/validation.csv (crop, year, scope, metric, n_muni, spearman,
pearson, yield_mean_kg_ha) and analysis\\validation\\municipal.parquet with the municipal rows.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.stats import pearsonr, spearmanr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s04_common as C  # noqa: E402

VAL = os.path.join(C.ANALYSIS, "validation")
RAW = os.path.join(VAL, "raw")
PRODUCTS = {"40124": "soybean", "40122": "maize", "40106": "sugarcane"}
URL = "https://apisidra.ibge.gov.br/values/t/5457/n6/all/v/112/p/2020,2024/c782/{p}?formato=json"
MIN_FIELDS = 20
MIN_MUNIS = 20


def download(force=False):
    os.makedirs(RAW, exist_ok=True)
    for p in PRODUCTS:
        out = os.path.join(RAW, f"sidra_5457_v112_{p}.json")
        if os.path.exists(out) and not force:
            continue
        req = urllib.request.Request(URL.format(p=p), headers={"User-Agent": "relative-land-productivity-validate/1.0"})
        with urllib.request.urlopen(req, timeout=900) as r, open(out, "wb") as fh:
            fh.write(r.read())
        print("downloaded", out, flush=True)


def load_yields():
    rows = []
    for p, crop in PRODUCTS.items():
        with open(os.path.join(RAW, f"sidra_5457_v112_{p}.json"), encoding="utf-8") as fh:
            d = json.load(fh)
        for r in d[1:]:
            v = r["V"]
            if not v.replace(".", "", 1).isdigit():
                continue
            rows.append((int(r["D1C"]), int(r["D3C"]), crop, float(v)))
    y = pd.DataFrame(rows, columns=["muni_code", "year", "crop", "yield_kg_ha"])
    return y


def maize_states():
    df = pd.read_csv(C.CALENDAR)
    sub = df[df["mapbiomas_class"].isin([19, 41])]
    return set(sub.loc[sub["dominant_other_crop_pam2023"].fillna("").str.startswith("Milho"), "state"])


def municipal_means(source, ay, states, mz_states):
    frames = []
    for s in states:
        mp = C.metrics_path(source, 2024, ay, s)
        rp = C.relative_path(source, 2024, ay, s)
        if not (os.path.exists(mp) and os.path.exists(rp)):
            continue
        m = pq.read_table(mp, columns=["fid", "cls", "muni_code", "state_uf", "area_ha", "integral"]).to_pandas()
        r = pq.read_table(rp, columns=["fid", "valid", "prod", "r_adj"]).to_pandas().set_index("fid")
        m = m.join(r, on="fid")
        m = m[m["valid"].values & np.isfinite(m["prod"].values)]
        uf = m["state_uf"].iloc[0] if len(m) else None
        crop = np.where(m["cls"] == 39, "soybean", np.where(m["cls"] == 20, "sugarcane",
                        np.where(m["cls"].isin([19, 41]) & (uf in mz_states), "maize", "")))
        m = m.assign(crop=crop)
        m = m[m["crop"] != ""]
        frames.append(m[["muni_code", "state_uf", "crop", "area_ha", "integral", "prod", "r_adj"]])
    df = pd.concat(frames, ignore_index=True)
    df["w"] = df["area_ha"]
    for c in ("integral", "prod", "r_adj"):
        df[f"w_{c}"] = df[c] * df["w"]
    g = df.groupby(["muni_code", "state_uf", "crop"], observed=True).agg(
        n_fields=("w", "size"), area_ha=("w", "sum"), w_integral=("w_integral", "sum"), w_prod=("w_prod", "sum"),
        w_r_adj=("w_r_adj", "sum")).reset_index()
    for c in ("integral", "prod", "r_adj"):
        g[c] = g[f"w_{c}"] / g["area_ha"]
        g = g.drop(columns=[f"w_{c}"])
    g = g[g["n_fields"] >= MIN_FIELDS]
    g["year"] = ay
    return g


def corr(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 5:
        return np.nan, np.nan, int(ok.sum())
    return float(spearmanr(x[ok], y[ok]).statistic), float(pearsonr(x[ok], y[ok]).statistic), int(ok.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["modis", "s2"], default="modis")
    ap.add_argument("--states", nargs="*", default=None)
    ap.add_argument("--ays", type=int, nargs="*", default=[2020, 2024])
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--no-summary-copy", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    download(args.download)
    yields = load_yields()
    states = args.states or C.state_dirs(2024)
    mz = maize_states()
    muni = pd.concat([municipal_means(args.source, ay, states, mz) for ay in args.ays], ignore_index=True)
    muni = muni.merge(yields, on=["muni_code", "year", "crop"], how="inner")
    os.makedirs(VAL, exist_ok=True)
    muni.to_parquet(os.path.join(VAL, "municipal.parquet"), index=False)
    rows = []
    for (crop, year), sub in muni.groupby(["crop", "year"]):
        for metric in ("integral", "prod", "r_adj"):
            sp, pe, n = corr(sub[metric].values, sub["yield_kg_ha"].values)
            rows.append({"crop": crop, "year": str(year), "scope": "BR", "metric": metric, "n_muni": n,
                         "spearman": sp, "pearson": pe, "yield_mean_kg_ha": float(sub["yield_kg_ha"].mean())})
            for uf, s2 in sub.groupby("state_uf", observed=True):
                if len(s2) >= MIN_MUNIS:
                    sp, pe, n = corr(s2[metric].values, s2["yield_kg_ha"].values)
                    rows.append({"crop": crop, "year": str(year), "scope": uf, "metric": metric, "n_muni": n,
                                 "spearman": sp, "pearson": pe, "yield_mean_kg_ha": float(s2["yield_kg_ha"].mean())})
    if set(args.ays) >= {2020, 2024}:
        a = muni[muni["year"] == 2020].set_index(["muni_code", "crop"])
        b = muni[muni["year"] == 2024].set_index(["muni_code", "crop"])
        both = a.join(b, lsuffix="_2020", rsuffix="_2024", how="inner").reset_index()
        both["d_yield"] = both["yield_kg_ha_2024"] - both["yield_kg_ha_2020"]
        both["d_yield_rel"] = both["d_yield"] / both["yield_kg_ha_2020"]
        for crop, sub in both.groupby("crop"):
            for metric in ("integral", "prod", "r_adj"):
                d = sub[f"{metric}_2024"].values - sub[f"{metric}_2020"].values
                sp, pe, n = corr(d, sub["d_yield_rel"].values)
                rows.append({"crop": crop, "year": "change", "scope": "BR", "metric": metric, "n_muni": n,
                             "spearman": sp, "pearson": pe, "yield_mean_kg_ha": float(sub["d_yield"].mean())})
                for uf, s2 in sub.groupby("state_uf_2024", observed=True):
                    if len(s2) >= MIN_MUNIS:
                        d = s2[f"{metric}_2024"].values - s2[f"{metric}_2020"].values
                        sp, pe, n = corr(d, s2["d_yield_rel"].values)
                        rows.append({"crop": crop, "year": "change", "scope": uf, "metric": metric, "n_muni": n,
                                     "spearman": sp, "pearson": pe, "yield_mean_kg_ha": float(s2["d_yield"].mean())})
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(VAL, "validation.csv"), index=False, float_format="%.4g")
    if not args.no_summary_copy:
        os.makedirs(C.SUMMARIES, exist_ok=True)
        out.to_csv(os.path.join(C.SUMMARIES, "validation.csv"), index=False, float_format="%.4g")
    pd.set_option("display.width", 200)
    print(out[out["scope"] == "BR"].to_string(index=False))
    print(f"done in {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
