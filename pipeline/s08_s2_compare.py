"""Stage 8: Sentinel-2 change classes and decisions for one state, and the comparison with MODIS
(pipeline/S2_MATO_GROSSO.md).

  python s08_s2_compare.py border      MODIS peer groups with and without the neighboring states
  python s08_s2_compare.py change      s2 change classes and version 1 decisions, in memory from s04_change
  python s08_s2_compare.py calibrate   s2 metric_adj to the MODIS scale, per peer class and year
  python s08_s2_compare.py area        s2 area call per H3 resolution 5 cell on the MODIS national reference
  python s08_s2_compare.py fields      s2 field call (decisions version 2)
  python s08_s2_compare.py compare     field by field agreement with the live MODIS result
  python s08_s2_compare.py validate    s2 and MODIS municipal means against IBGE yields, same municipalities
  python s08_s2_compare.py all

Run after s04_metrics.py --source s2 (polys 2024, ay 2020 and 2024) and s04_relative.py --source s2
--polys 2024 --no-summary-copy for the state. Nothing here writes into the live MODIS tables
(analysis\\year=2024, analysis\\decisions, docs/): s04_change.py and s07_decisions.py write
fields_scored.parquet at a path with no source in it, so this stage reuses their functions and
writes under analysis\\source=s2\\ instead.

Area tier. The national reference of s07_decisions.py is MODIS: the national class medians and
the SD of cell medians come from MODIS metric_adj over Brazil. Sentinel-2 integrals are on
another scale (monthly maximum composites at 30 m against 16-day composites at 250 m), so s2
values are mapped to the MODIS scale first. Per peer class and agricultural year, on fields
over CAL_MIN_HA hectares with high MODIS confidence, valid on both sensors and in the same peer
class, the map is linear and matches the median and the robust SD (1.4826 MAD) of the two
distributions: cal = med_modis + (s2 - med_s2) * sd_modis / sd_s2. An OLS fit of MODIS on s2
is reported beside it; OLS is not used because noise in s2 flattens its slope. Cell medians of
the calibrated s2 values over cells with MIN_FIELDS valid s2 fields are then scored against the
MODIS national medians and cell SD (analysis\\decisions\\national_summary.json, resolution 5),
and the area rule of s07_decisions.area_call applies unchanged. The within-state alternative
(s2 cells against s2 state medians) is computed as a sensitivity.

Field call. s07_decisions.field_call unchanged. Its inputs: s2 change class, the s2 version 1
decision (for abandon), s2 r_adj_2024, the s2 area call, and for newly cropped fields an s2
r_eco_2024: the calibrated s2 value against the MODIS ecoregion-class median and SD, which are
recovered exactly from the MODIS fields of the state (metric_adj = med + sd * r_eco is linear
in each group).

s2 confidence: low when fewer than 75 percent of the window months were observed in either
year, or the field is under S2_MIN_HA hectares (five 30 m pixels).
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
from scipy.stats import pearsonr, spearmanr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s04_common as C  # noqa: E402
import s04_change as CH  # noqa: E402
import s04_relative as RL  # noqa: E402
import s04_validate as VA  # noqa: E402
import s07_decisions as DV  # noqa: E402

OUT = os.path.join(C.ANALYSIS, "source=s2")
CAL_MIN_HA = 25.0
S2_MIN_HA = 0.45
MIN_FIELDS = DV.MIN_FIELDS
BANDS = [(0, 6.25, "under 6.25 ha"), (6.25, 25, "6.25 to 25 ha"), (25, 100, "25 to 100 ha"), (100, np.inf, "over 100 ha")]
NEIGHBORS = ["Rondonia", "Amazonas", "Para", "Tocantins", "Goias", "Mato_Grosso_Do_Sul"]
CC_ORDER = ["large_decline", "decline", "stable", "gain", "large_gain", "crop_switched", "newly_cropped", "no_data"]
UF = {"Mato_Grosso": "MT"}


def log(**kw):
    kw["t"] = datetime.now().isoformat(timespec="seconds")
    print(json.dumps(kw, ensure_ascii=False, default=str), flush=True)


def p(*a):
    path = os.path.join(OUT, *a)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def summ(name):
    os.makedirs(C.SUMMARIES, exist_ok=True)
    return os.path.join(C.SUMMARIES, name)


def rd(path, cols):
    return pq.read_table(path, columns=cols).to_pandas()


def band_of(area):
    out = np.empty(len(area), dtype=object)
    for lo, hi, name in BANDS:
        out[(area >= lo) & (area < hi)] = name
    return out


# ----------------------------------------------------------------------------- border

def border(state):
    """How many fields of the state lose or change their MODIS peer group when the neighbors are dropped."""
    t0 = time.time()
    pooled = RL.load_year("modis", 2024, 2024, [state] + NEIGHBORS)
    alone = RL.load_year("modis", 2024, 2024, [state])
    res = {}
    for name, df in (("pooled", pooled), ("alone", alone)):
        lv, cell = RL.assign_groups(df)
        df["level"], df["cell"] = lv, cell
    st = pooled["state"].astype(str).values == state
    a = pooled[st].reset_index(drop=True)
    b = alone.reset_index(drop=True)
    assert np.array_equal(a["fid"].values, b["fid"].values)
    g = pooled[pooled["level"] > 0]
    other = g.assign(o=(g["state"].astype(str) != state)).groupby(["cell", "peer_cls"])["o"].agg(["sum", "size"])
    key = pd.MultiIndex.from_arrays([a["cell"].values, a["peer_cls"].values])
    n_other = other["sum"].reindex(key).fillna(0).values
    grouped_a = a["level"].values > 0
    shared = np.intersect1d(a["h3_5"].unique(), pooled.loc[~st, "h3_5"].unique())
    lost = grouped_a & (b["level"].values == 0)
    changed = grouped_a & (b["level"].values > 0) & ((a["level"].values != b["level"].values) | (a["cell"].values != b["cell"].values))
    same_fewer = grouped_a & ~lost & ~changed & (n_other > 0)
    res = {"fields": int(len(a)), "grouped_pooled": int(grouped_a.sum()), "grouped_alone": int((b["level"].values > 0).sum()),
           "lose_group": int(lost.sum()), "change_group": int(changed.sum()), "same_group_fewer_peers": int(same_fewer.sum()),
           "change_to_coarser": int((changed & (b["level"].values < a["level"].values)).sum()),
           "fields_in_groups_with_other_state_fields": int((n_other > 0).sum()),
           "h3_5_cells_of_state": int(a["h3_5"].nunique()),
           "h3_5_cells_shared_with_neighbors": int(len(shared)),
           "fields_in_shared_h3_5_cells": int(np.isin(a["h3_5"].values, shared).sum()),
           "seconds": round(time.time() - t0)}
    with open(p("compare", f"border_{state}.json"), "w") as fh:
        json.dump(res, fh, indent=1)
    log(step="border", **res)
    return res


# ----------------------------------------------------------------------------- change

def change(state):
    """s04_change.score_state logic for the 2024 polygons, without geometry, under source=s2."""
    t0 = time.time()
    f = rd(C.fields_path(2024, state), ["fid", "area_ha", "mbmode", "muni_code"])
    cl = rd(C.classes_path(2024, state), ["fid", "mb_2020"]).set_index("fid")
    df = f.join(cl, on="fid")
    for ay in (2020, 2024):
        r = rd(C.relative_path("s2", 2024, ay, state), ["fid", "prod", "r_adj", "valid", "metric", "metric_adj", "group_level"]).set_index("fid").add_suffix(f"_{ay}")
        m = rd(C.metrics_path("s2", 2024, ay, state), ["fid", "n_window", "n_valid_window", "integral", "peer_cls"]).set_index("fid").add_suffix(f"_{ay}")
        df = df.join(r, on="fid").join(m, on="fid")
    mb20 = df["mb_2020"].fillna(-1).values.astype(np.int16)
    mb24 = df["mbmode"].values.astype(np.int16)
    ag20 = np.isin(mb20, C.AG_CLASSES)
    grp20 = np.array([C.CROP_GROUP.get(int(c), "none") for c in mb20], dtype=object)
    grp24 = np.array([C.CROP_GROUP.get(int(c), "none") for c in mb24], dtype=object)
    r20 = df["r_adj_2020"].values.astype(np.float32)
    r24 = df["r_adj_2024"].values.astype(np.float32)
    with np.errstate(invalid="ignore"):
        D = r24 - r20
    cc = CH.change_class(D)
    cc[~ag20] = "newly_cropped"
    cc[ag20 & (grp20 != grp24)] = "crop_switched"
    integ = df["integral_2024"].values
    valid24 = df["valid_2024"].fillna(False).values.astype(bool)
    pctl = {}
    for c in np.unique(mb24):
        sel = (mb24 == c) & valid24 & np.isfinite(integ)
        if sel.sum() >= 30:
            pctl[int(c)] = float(np.percentile(integ[sel], CH.ABANDON_PCTL))
    dec1 = CH.decide(cc, r20, r24, integ, mb24, pctl)
    nw = {ay: df[f"n_window_{ay}"].fillna(0).values.astype(np.float32) for ay in (2020, 2024)}
    nv = {ay: df[f"n_valid_window_{ay}"].fillna(0).values.astype(np.float32) for ay in (2020, 2024)}
    low = (df["area_ha"].values < S2_MIN_HA) | (nv[2024] < CH.CONF_SHARE * nw[2024]) | np.where(nw[2020] > 0, nv[2020] < CH.CONF_SHARE * nw[2020], False)
    out = pd.DataFrame({"fid": df["fid"].values.astype(np.int64), "area_ha": df["area_ha"].values.astype(np.float32),
                        "crop_2020": mb20, "crop_2024": mb24,
                        "metric_2020": df["metric_2020"].values.astype(np.float32), "metric_2024": df["metric_2024"].values.astype(np.float32),
                        "metric_adj_2020": df["metric_adj_2020"].values.astype(np.float32), "metric_adj_2024": df["metric_adj_2024"].values.astype(np.float32),
                        "valid_2020": df["valid_2020"].fillna(False).values.astype(bool), "valid_2024": valid24,
                        "peer_cls_2020": df["peer_cls_2020"].fillna(-1).values.astype(np.int16),
                        "peer_cls_2024": df["peer_cls_2024"].fillna(-1).values.astype(np.int16),
                        "group_level_2020": df["group_level_2020"].fillna(0).values.astype(np.int8),
                        "group_level_2024": df["group_level_2024"].fillna(0).values.astype(np.int8),
                        "prod_2020": df["prod_2020"].values.astype(np.float32), "prod_2024": df["prod_2024"].values.astype(np.float32),
                        "r_adj_2020": r20, "r_adj_2024": r24,
                        "change_class": pd.Categorical(cc, categories=CH.CHANGE_CLASSES),
                        "decision_v1": pd.Categorical(dec1, categories=CH.DECISIONS),
                        "n_obs_2020": nv[2020].astype(np.int8), "n_obs_2024": nv[2024].astype(np.int8),
                        "muni_code": C.muni_to_int(df["muni_code"]),
                        "confidence": pd.Categorical(np.where(low, "low", "high"), categories=["high", "low"])})
    path = p("year=2024", f"state={state}", "fields_scored.parquet")
    out.to_parquet(path, index=False)
    res = {"rows": int(len(out)), "change_class": out["change_class"].value_counts().to_dict(),
           "confidence_low": int(low.sum()), "seconds": round(time.time() - t0)}
    log(step="change", **res)
    return out


# ----------------------------------------------------------------------------- calibrate

def modis_fields(state):
    """Live MODIS per-field values for the state (2024 polygons), in fields order."""
    sc = rd(os.path.join(C.ANALYSIS, "year=2024", f"state={state}", "fields_scored.parquet"),
            ["fid", "change_class", "decision", "area_decision", "confidence", "r_adj_2020", "r_adj_2024", "prod_2020", "prod_2024"])
    for ay in (2020, 2024):
        r = rd(C.relative_path("modis", 2024, ay, state), ["fid", "valid", "metric", "metric_adj", "group_level"])
        m = rd(C.metrics_path("modis", 2024, ay, state), ["fid", "peer_cls", "h3_5", "h3_6"])
        assert np.array_equal(r["fid"].values, sc["fid"].values) and np.array_equal(m["fid"].values, sc["fid"].values)
        for c in ("valid", "metric", "metric_adj", "group_level"):
            sc[f"{c}_{ay}"] = r[c].values
        sc[f"peer_cls_{ay}"] = m["peer_cls"].values
    sc["h3_5"] = m["h3_5"].values
    sc["h3_6"] = m["h3_6"].values
    for c in ("change_class", "decision", "area_decision", "confidence"):
        sc[c] = sc[c].astype(str)
    return sc


def calibrate(state, s2=None, mo=None):
    t0 = time.time()
    s2 = s2 if s2 is not None else pd.read_parquet(p("year=2024", f"state={state}", "fields_scored.parquet"))
    mo = mo if mo is not None else modis_fields(state)
    assert np.array_equal(s2["fid"].values, mo["fid"].values)
    rows = []
    for ay in (2020, 2024):
        sel0 = ((s2["area_ha"].values > CAL_MIN_HA) & (mo["confidence"].values == "high") & s2[f"valid_{ay}"].values
                & mo[f"valid_{ay}"].values.astype(bool) & (s2[f"peer_cls_{ay}"].values == mo[f"peer_cls_{ay}"].values)
                & np.isfinite(s2[f"metric_adj_{ay}"].values) & np.isfinite(mo[f"metric_adj_{ay}"].values))
        for cls in np.unique(s2[f"peer_cls_{ay}"].values[sel0]):
            sel = sel0 & (s2[f"peer_cls_{ay}"].values == cls)
            x = s2[f"metric_adj_{ay}"].values[sel].astype(np.float64)
            y = mo[f"metric_adj_{ay}"].values[sel].astype(np.float64)
            rec = {"ay": ay, "peer_cls": int(cls), "n": int(sel.sum())}
            if rec["n"] >= 100:
                mx, my = np.median(x), np.median(y)
                sx, sy = C.mad_sd(x), C.mad_sd(y)
                slope = sy / sx
                ols = np.polyfit(x, y, 1)
                cal = my + (x - mx) * slope
                rec.update({"med_s2": mx, "med_modis": my, "sd_s2": sx, "sd_modis": sy, "slope": slope, "intercept": my - mx * slope,
                            "ols_slope": float(ols[0]), "ols_intercept": float(ols[1]),
                            "pearson": float(pearsonr(x, y).statistic), "spearman": float(spearmanr(x, y).statistic),
                            "resid_sd_modis_units": float(C.mad_sd(y - cal)), "resid_in_cell_sd": np.nan})
            rows.append(rec)
    cal = pd.DataFrame(rows)
    nat = json.load(open(os.path.join(C.ANALYSIS, "decisions", "national_summary.json")))
    cal["resid_in_cell_sd"] = [r.resid_sd_modis_units / nat["r5_2024"]["cell_sd"].get(str(int(r.peer_cls)), np.nan)
                               if np.isfinite(r.resid_sd_modis_units) else np.nan for r in cal.itertuples()]
    cal.to_csv(p("decisions", f"calibration_{state}.csv"), index=False, float_format="%.5g")
    cal.to_csv(summ("s2_mt_calibration.csv"), index=False, float_format="%.4g")
    log(step="calibrate", rows=len(cal), fitted=int(cal["slope"].notna().sum()), seconds=round(time.time() - t0))
    print(cal.to_string(), flush=True)
    return cal


def apply_cal(s2, cal, ay):
    c = cal[(cal["ay"] == ay) & cal["slope"].notna()].set_index("peer_cls")
    cls = s2[f"peer_cls_{ay}"].values
    sl = pd.Series(cls).map(c["slope"]).values
    ic = pd.Series(cls).map(c["intercept"]).values
    return (ic + sl * s2[f"metric_adj_{ay}"].values).astype(np.float32)


# ----------------------------------------------------------------------------- area

def cell_table(cell, cls, valid, m, nat_med, cell_sd, ay):
    v = pd.DataFrame({"cell": cell, "cls": cls, "m": m})[valid & np.isfinite(m)]
    g = v.groupby(["cell", "cls"])["m"].agg(["median", "size"]).reset_index()
    g = g[g["size"] >= MIN_FIELDS]
    g[f"v{ay % 100}"] = (g["median"] - g["cls"].map(nat_med)) / g["cls"].map(cell_sd)
    return g.rename(columns={"size": f"n_{ay}"})[["cell", "cls", f"n_{ay}", f"v{ay % 100}"]]


def area_from(s2, m_by_year, nat_med_by_year, cell_sd_by_year, cells):
    per = {}
    for ay in (2020, 2024):
        per[ay] = cell_table(cells, s2[f"peer_cls_{ay}"].values, s2[f"valid_{ay}"].values, m_by_year[ay],
                             nat_med_by_year[ay], cell_sd_by_year[ay], ay)
    t = per[2020].merge(per[2024], on=["cell", "cls"], how="outer")
    t["change"] = t["v24"] - t["v20"]
    t["n_2024"] = t["n_2024"].fillna(0)
    t["group"] = DV.group_of(t["cls"].values)
    a = DV.pool(t, "crops", "v24", "change").join(DV.pool(t, "pasture", "v24", "change"), how="outer")
    for c in ("crops_level", "pasture_level", "crops_change", "pasture_change"):
        if c not in a:
            a[c] = np.nan
    a["area_decision"] = DV.area_call(a)
    a.index.name = "cell"
    return t, a.reset_index()


def area(state, s2=None, cal=None):
    t0 = time.time()
    s2 = s2 if s2 is not None else pd.read_parquet(p("year=2024", f"state={state}", "fields_scored.parquet"))
    cal = cal if cal is not None else pd.read_csv(p("decisions", f"calibration_{state}.csv"))
    m = rd(C.metrics_path("s2", 2024, 2024, state), ["fid", "h3_5"])
    assert np.array_equal(m["fid"].values, s2["fid"].values)
    cells = m["h3_5"].values
    nat = json.load(open(os.path.join(C.ANALYSIS, "decisions", "national_summary.json")))
    nm = {ay: {int(k): v for k, v in nat[f"r5_{ay}"]["nat_med"].items()} for ay in (2020, 2024)}
    cs = {ay: {int(k): v for k, v in nat[f"r5_{ay}"]["cell_sd"].items()} for ay in (2020, 2024)}
    mcal = {ay: apply_cal(s2, cal, ay) for ay in (2020, 2024)}
    t, a = area_from(s2, mcal, nm, cs, cells)
    t.to_parquet(p("decisions", f"cell_nation_r5_{state}.parquet"), index=False)
    a.to_parquet(p("decisions", f"area_cells_{state}.parquet"), index=False)
    # sensitivity: the state as its own reference, on uncalibrated s2
    sm, sc = {}, {}
    for ay in (2020, 2024):
        v = s2[f"valid_{ay}"].values & np.isfinite(s2[f"metric_adj_{ay}"].values)
        d = pd.DataFrame({"cell": cells[v], "cls": s2[f"peer_cls_{ay}"].values[v], "m": s2[f"metric_adj_{ay}"].values[v]})
        sm[ay] = d.groupby("cls")["m"].median().to_dict()
        g = d.groupby(["cell", "cls"])["m"].agg(["median", "size"]).reset_index()
        g = g[g["size"] >= MIN_FIELDS]
        sc[ay] = g.groupby("cls")["median"].agg(lambda x: 1.4826 * np.median(np.abs(x - np.median(x)))).to_dict()
    raw = {ay: s2[f"metric_adj_{ay}"].values for ay in (2020, 2024)}
    t_in, a_in = area_from(s2, raw, sm, sc, cells)
    a_in.to_parquet(p("decisions", f"area_cells_within_state_{state}.parquet"), index=False)
    vc = a["area_decision"].value_counts().to_dict()
    log(step="area", cells=int(len(a)), calls=vc, within_state=a_in["area_decision"].value_counts().to_dict(), seconds=round(time.time() - t0))
    return a, a_in


# ----------------------------------------------------------------------------- fields

def eco_stats(state, mo):
    """MODIS ecoregion-class median and SD of metric_adj_2024, solved from metric_adj = med + sd * r_eco per group."""
    e = rd(os.path.join(C.ANALYSIS, "ecoregions", "fields", f"{state}.parquet"), ["fid", "eco_id", "peer_cls_2024", "r_eco_2024"])
    assert np.array_equal(e["fid"].values, mo["fid"].values)
    d = pd.DataFrame({"eco_id": e["eco_id"].values, "cls": e["peer_cls_2024"].values, "r": e["r_eco_2024"].values,
                      "m": mo["metric_adj_2024"].values})
    d = d[np.isfinite(d["r"]) & np.isfinite(d["m"])]
    rows = []
    for (eid, cls), g in d.groupby(["eco_id", "cls"]):
        if len(g) >= 2 and np.ptp(g["r"].values) > 0:
            sd, med = np.polyfit(g["r"].values, g["m"].values, 1)
            resid = float(np.max(np.abs(g["m"].values - (med + sd * g["r"].values))))
            rows.append({"eco_id": int(eid), "cls": int(cls), "med": med, "sd": sd, "n": len(g), "max_resid": resid})
    return e, pd.DataFrame(rows)


def fields(state, s2=None, cal=None, a=None, mo=None):
    t0 = time.time()
    s2 = s2 if s2 is not None else pd.read_parquet(p("year=2024", f"state={state}", "fields_scored.parquet"))
    cal = cal if cal is not None else pd.read_csv(p("decisions", f"calibration_{state}.csv"))
    a = a if a is not None else pd.read_parquet(p("decisions", f"area_cells_{state}.parquet"))
    mo = mo if mo is not None else modis_fields(state)
    m = rd(C.metrics_path("s2", 2024, 2024, state), ["fid", "h3_5"])
    cells = m["h3_5"].values
    area_s2 = pd.Series(cells).map(pd.Series(a["area_decision"].values, index=a["cell"].values)).fillna("none").values.astype(object)
    e, es = eco_stats(state, mo)
    key = pd.MultiIndex.from_arrays([e["eco_id"].values.astype(np.int64), s2["peer_cls_2024"].values.astype(np.int64)])
    esi = es.set_index(["eco_id", "cls"])
    med = esi["med"].reindex(key).values
    sd = esi["sd"].reindex(key).values
    mcal24 = apply_cal(s2, cal, 2024)
    with np.errstate(all="ignore"):
        r_eco = np.where(s2["valid_2024"].values, (mcal24 - med) / sd, np.nan).astype(np.float32)
    cc = s2["change_class"].astype(str).values
    dec = DV.field_call(cc, s2["decision_v1"].astype(str).values, s2["r_adj_2024"].values, r_eco,
                        s2["crop_2024"].values, area_s2, s2["peer_cls_2024"].values)
    s2 = s2.copy()
    s2["decision"] = pd.Categorical(dec, categories=DV.DECISIONS)
    s2["area_decision"] = pd.Categorical(area_s2, categories=DV.AREA)
    s2["r_eco_2024"] = r_eco
    s2["metric_cal_2020"] = apply_cal(s2, cal, 2020)
    s2["metric_cal_2024"] = mcal24
    s2.to_parquet(p("year=2024", f"state={state}", "fields_scored.parquet"), index=False)
    log(step="fields", decision=s2["decision"].value_counts().to_dict(), eco_groups=int(len(es)),
        eco_max_resid=float(es["max_resid"].max()), seconds=round(time.time() - t0))
    return s2


# ----------------------------------------------------------------------------- compare

def corr(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 10:
        return np.nan, np.nan, int(ok.sum())
    return float(pearsonr(x[ok], y[ok]).statistic), float(spearmanr(x[ok], y[ok]).statistic), int(ok.sum())


def compare(state, s2=None, mo=None):
    t0 = time.time()
    s2 = s2 if s2 is not None else pd.read_parquet(p("year=2024", f"state={state}", "fields_scored.parquet"))
    mo = mo if mo is not None else modis_fields(state)
    assert np.array_equal(s2["fid"].values, mo["fid"].values)
    res = {"fields": int(len(s2))}
    cc_s, cc_m = s2["change_class"].astype(str).values, mo["change_class"].values
    cm = pd.crosstab(pd.Series(cc_m, name="modis"), pd.Series(cc_s, name="s2")).reindex(index=CC_ORDER, columns=CC_ORDER, fill_value=0)
    cm.to_csv(summ("s2_mt_change_confusion.csv"))
    res["change_exact"] = float((cc_s == cc_m).mean())
    trend = {"large_decline": "decline", "decline": "decline", "stable": "stable", "gain": "gain", "large_gain": "gain"}
    both = np.isin(cc_s, list(trend)) & np.isin(cc_m, list(trend))
    res["change_comparable_both"] = int(both.sum())
    res["change_exact_comparable"] = float((cc_s[both] == cc_m[both]).mean())
    ts = pd.Series(cc_s[both]).map(trend).values
    tm = pd.Series(cc_m[both]).map(trend).values
    res["trend_agree_comparable"] = float((ts == tm).mean())
    res["trend_opposite_comparable"] = float((((ts == "decline") & (tm == "gain")) | ((ts == "gain") & (tm == "decline"))).mean())
    # weighted kappa-free summary per MODIS class: share s2 puts in the same class
    dm = pd.crosstab(pd.Series(mo["decision"].values, name="modis"), pd.Series(s2["decision"].astype(str).values, name="s2")) \
        .reindex(index=DV.DECISIONS, columns=DV.DECISIONS, fill_value=0)
    dm.to_csv(summ("s2_mt_decision_confusion.csv"))
    res["decision_exact"] = float((mo["decision"].values == s2["decision"].astype(str).values).mean())
    am = pd.crosstab(pd.Series(mo["area_decision"].values, name="modis"), pd.Series(s2["area_decision"].astype(str).values, name="s2")) \
        .reindex(index=DV.AREA, columns=DV.AREA, fill_value=0)
    am.to_csv(summ("s2_mt_area_confusion_fields.csv"))
    res["area_exact_fields"] = float((mo["area_decision"].values == s2["area_decision"].astype(str).values).mean())
    # area calls per cell, over the state's cells in the live MODIS table
    live = pd.read_parquet(os.path.join(C.ANALYSIS, "decisions", "area_cells.parquet"))
    a2 = pd.read_parquet(p("decisions", f"area_cells_{state}.parquet"))
    ain = pd.read_parquet(p("decisions", f"area_cells_within_state_{state}.parquet"))
    cells_state = pd.Series(mo["h3_5"].values).value_counts()
    cells_state = cells_state[cells_state >= 1].index.values
    lc = live.set_index("cell").reindex(cells_state)
    ac = a2.set_index("cell").reindex(cells_state)
    ic = ain.set_index("cell").reindex(cells_state)
    lcall = lc["area_decision"].fillna("none").values
    acall = ac["area_decision"].fillna("none").values
    icall = ic["area_decision"].fillna("none").values
    cc_cells = pd.crosstab(pd.Series(lcall, name="modis"), pd.Series(acall, name="s2")).reindex(index=DV.AREA, columns=DV.AREA, fill_value=0)
    cc_cells.to_csv(summ("s2_mt_area_confusion_cells.csv"))
    res["area_cells"] = int(len(cells_state))
    res["area_exact_cells"] = float((lcall == acall).mean())
    res["area_exact_cells_within_state"] = float((lcall == icall).mean())
    res["area_cells_modis"] = pd.Series(lcall).value_counts().to_dict()
    res["area_cells_s2"] = pd.Series(acall).value_counts().to_dict()
    res["area_cells_s2_within_state"] = pd.Series(icall).value_counts().to_dict()
    for g in ("crops", "pasture"):
        for k in ("level", "change"):
            c = f"{g}_{k}"
            res[f"cell_corr_{c}"] = corr(lc[c].values.astype(float), ac[c].values.astype(float))
            res[f"cell_corr_{c}_within_state"] = corr(lc[c].values.astype(float), ic[c].values.astype(float))
    # correlations by size band
    rows = []
    band = band_of(s2["area_ha"].values)
    mats = {"integral": ("metric", "metric"), "r_adj": ("r_adj", "r_adj"), "prod": ("prod", "prod")}
    for name, (cs, cm_) in mats.items():
        for ay in (2020, 2024):
            xs = s2[f"{cs}_{ay}"].values.astype(float)
            xm = mo[f"{cm_}_{ay}"].values.astype(float)
            same = s2[f"peer_cls_{ay}"].values == mo[f"peer_cls_{ay}"].values
            for lo, hi, bn in BANDS + [(0, np.inf, "all")]:
                sel = (band == bn) if bn != "all" else np.ones(len(band), bool)
                sel = sel & same
                pe, sp, n = corr(xs[sel], xm[sel])
                rows.append({"metric": name, "year": ay, "band": bn, "n": n, "pearson": pe, "spearman": sp})
    D_s = s2["r_adj_2024"].values - s2["r_adj_2020"].values
    D_m = mo["r_adj_2024"].values - mo["r_adj_2020"].values
    for lo, hi, bn in BANDS + [(0, np.inf, "all")]:
        sel = (band == bn) if bn != "all" else np.ones(len(band), bool)
        pe, sp, n = corr(D_s[sel], D_m[sel])
        rows.append({"metric": "change_D", "year": "2024-2020", "band": bn, "n": n, "pearson": pe, "spearman": sp})
        ex = sel & np.isin(cc_s, list(trend)) & np.isin(cc_m, list(trend))
        rows.append({"metric": "change_class_exact", "year": "2024-2020", "band": bn, "n": int(ex.sum()),
                     "pearson": float((cc_s[ex] == cc_m[ex]).mean()) if ex.any() else np.nan, "spearman": np.nan})
        de = sel
        rows.append({"metric": "decision_exact", "year": "", "band": bn, "n": int(de.sum()),
                     "pearson": float((mo["decision"].values[de] == s2["decision"].astype(str).values[de]).mean()), "spearman": np.nan})
        for src, Dv in (("s2", D_s), ("modis", D_m)):
            v = Dv[sel & np.isfinite(Dv)]
            rows.append({"metric": f"change_D_sd_{src}", "year": "2024-2020", "band": bn, "n": int(len(v)),
                         "pearson": float(C.mad_sd(v)), "spearman": float(np.std(v))})
    cb = pd.DataFrame(rows)
    cb.to_csv(summ("s2_mt_corr_by_size.csv"), index=False, float_format="%.4f")
    # low-confidence MODIS fields that get a usable s2 value
    lowm = mo["confidence"].values == "low"
    s2_meas = cc_s != "no_data"
    s2_high = s2["confidence"].astype(str).values == "high"
    s2_rel = np.isfinite(s2["r_adj_2024"].values)
    res["modis_low_conf"] = int(lowm.sum())
    res["modis_low_conf_s2_r_adj_2024"] = int((lowm & s2_rel).sum())
    res["modis_low_conf_s2_class_not_no_data"] = int((lowm & s2_meas).sum())
    res["modis_low_conf_s2_high_conf"] = int((lowm & s2_high).sum())
    res["modis_low_conf_s2_high_conf_and_class"] = int((lowm & s2_high & s2_meas).sum())
    res["s2_low_conf"] = int((~s2_high).sum())
    res["s2_under_min_ha"] = int((s2["area_ha"].values < S2_MIN_HA).sum())
    res["no_data_modis"] = int((cc_m == "no_data").sum())
    res["no_data_s2"] = int((cc_s == "no_data").sum())
    res["s2_counts_change"] = pd.Series(cc_s).value_counts().to_dict()
    res["modis_counts_change"] = pd.Series(cc_m).value_counts().to_dict()
    res["s2_counts_decision"] = s2["decision"].astype(str).value_counts().to_dict()
    res["modis_counts_decision"] = pd.Series(mo["decision"].values).value_counts().to_dict()
    res["group_level_s2_2024"] = s2["group_level_2024"].value_counts().to_dict()
    res["group_level_modis_2024"] = pd.Series(mo["group_level_2024"].values).value_counts().to_dict()
    # sensitivity: s2 with the MODIS weather fit instead of the s2 refit
    res["modis_fit_sensitivity"] = fit_sensitivity(state, s2)
    with open(p("compare", f"compare_{state}.json"), "w") as fh:
        json.dump(res, fh, indent=1, default=lambda o: o if not isinstance(o, (np.integer, np.floating)) else o.item())
    log(step="compare", seconds=round(time.time() - t0))
    print(json.dumps(res, indent=1, default=str))
    print(cm.to_string())
    print(cb.to_string())
    return res


def fit_sensitivity(state, s2):
    fit = pd.read_json(os.path.join(C.RELATIVE, "source=modis", "weather_fit.json"), orient="records")
    r = {}
    for ay in (2020, 2024):
        df = RL.load_year("s2", 2024, ay, [state])
        lv, cell = RL.assign_groups(df)
        df["level"], df["cell"] = lv, cell
        df["metric_adj"] = RL.apply_weather(df, fit)
        st = RL.group_stats(df, "metric_adj")
        r[ay] = RL.relative(df["metric_adj"].values, st)
    D = r[2024] - r[2020]
    cc = CH.change_class(D)
    base = s2["change_class"].astype(str).values
    comp = np.isin(base, ["large_decline", "decline", "stable", "gain", "large_gain"])
    return {"r_adj_2024_pearson": corr(r[2024], s2["r_adj_2024"].values)[0],
            "change_class_exact_on_comparable": float((cc[comp] == base[comp]).mean())}


# ----------------------------------------------------------------------------- validate

def validate(state):
    t0 = time.time()
    VA.download(False)
    y = VA.load_yields()
    mz = VA.maize_states()
    rows = []
    munis = {}
    for src in ("modis", "s2"):
        munis[src] = pd.concat([VA.municipal_means(src, ay, [state], mz) for ay in (2020, 2024)], ignore_index=True) \
            .merge(y, on=["muni_code", "year", "crop"], how="inner")
    k = ["muni_code", "crop", "year"]
    common = munis["modis"][k].merge(munis["s2"][k], on=k)
    for src in ("modis", "s2"):
        m = munis[src].merge(common, on=k)
        m.to_parquet(p("validation", f"municipal_{src}_{state}.parquet"), index=False)
        for (crop, year), sub in m.groupby(["crop", "year"]):
            for metric in ("integral", "prod", "r_adj"):
                pe, sp, n = corr(sub[metric].values, sub["yield_kg_ha"].values)
                rows.append({"source": src, "crop": crop, "year": str(year), "metric": metric, "n_muni": n, "spearman": sp, "pearson": pe})
        a = m[m["year"] == 2020].set_index(["muni_code", "crop"])
        b = m[m["year"] == 2024].set_index(["muni_code", "crop"])
        bb = a.join(b, lsuffix="_2020", rsuffix="_2024", how="inner").reset_index()
        bb["d_rel"] = (bb["yield_kg_ha_2024"] - bb["yield_kg_ha_2020"]) / bb["yield_kg_ha_2020"]
        for crop, sub in bb.groupby("crop"):
            for metric in ("integral", "prod", "r_adj"):
                d = sub[f"{metric}_2024"].values - sub[f"{metric}_2020"].values
                pe, sp, n = corr(d, sub["d_rel"].values)
                rows.append({"source": src, "crop": crop, "year": "change", "metric": metric, "n_muni": n, "spearman": sp, "pearson": pe})
    out = pd.DataFrame(rows)
    out.to_csv(p("validation", f"validation_{state}.csv"), index=False, float_format="%.4f")
    wide = out.pivot_table(index=["crop", "year", "metric", "n_muni"], columns="source", values=["spearman", "pearson"]).reset_index()
    wide.columns = ["_".join([c for c in col if c]) for col in wide.columns]
    wide.to_csv(summ("s2_mt_validation.csv"), index=False, float_format="%.4f")
    log(step="validate", seconds=round(time.time() - t0))
    pd.set_option("display.width", 200)
    print(wide.to_string(index=False))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["border", "change", "calibrate", "area", "fields", "compare", "validate", "all"])
    ap.add_argument("--state", default="Mato_Grosso")
    args = ap.parse_args()
    s = args.state
    if args.step == "all":
        border(s)
        s2 = change(s)
        mo = modis_fields(s)
        cal = calibrate(s, s2, mo)
        a, _ = area(s, s2, cal)
        s2 = fields(s, s2, cal, a, mo)
        compare(s, s2, mo)
        validate(s)
        return
    {"border": border, "change": change, "calibrate": calibrate, "area": lambda st: area(st), "fields": fields,
     "compare": compare, "validate": validate}[args.step](s)


if __name__ == "__main__":
    main()
