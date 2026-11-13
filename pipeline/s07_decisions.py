"""Stage 7b: two-tier land use decisions, the area call per H3 resolution 5 cell first and the
field call inside it second (methods/METHODS.md section 7, pipeline/DECISIONS_V2.md).

  python s07_decisions.py national   cell_vs_nation and the plain change per H3 cell and class, resolutions 5 and 6
  python s07_decisions.py dist       distributions of the area term, to set the thresholds
  python s07_decisions.py area       area call per cell -> analysis\\decisions\\area_cells.parquet, data/summaries/area_cells.csv.gz
  python s07_decisions.py fields     field call per state, written into fields_scored.parquet and the abandoned layer
  python s07_decisions.py report     national, state and ecoregion counts, old against new cross table
  python s07_decisions.py lookup     docs/data/ecoregions.json for the site (names and Scale C context)
  python s07_decisions.py all

Run after s04_change.py and s06_ecoregion_peers.py score. Rerunning s04_change.py rewrites
fields_scored.parquet with the first-version decision only, so this stage must follow it.

Area call. The area term is the national reference (user direction of 13 November 2026, "lets
do brazil as a whole then to get the true frontiers of productivity change"): cell_vs_nation,
the median of the weather-adjusted seasonal integral of a peer class in an H3 resolution 5
cell minus the national median of the class, divided by 1.4826 MAD of the national
distribution of cell medians of the class (cells with 30 valid fields). A (cell, class) row
exists only with 30 valid fields of the class. The cell-within-ecoregion term of s06 and the
ecoregion's Scale C change are kept as secondary context (eco_* columns), not used in the call.
Per cell the rows are pooled into two groups, weighted by the 2024 field count: crops
(soybean 39, temporary crops 19 and 41, sugarcane 20, rice 40, cotton 62, the perennials
coffee 46, citrus 47, other perennials 48 and oil palm 35) and pasture (15). Mosaic of uses
(21) is reported on its own and does not enter the call; forest plantation (9) and the generic
agriculture class (18) do not either. A group is present when it has a 2024 value, which
means at least MIN_FIELDS fields of one of its classes in the cell. Level = the pooled 2024
value; change = the pooled 2024 minus 2020 value over rows with both years.

  below      level < -LEVEL_T
  declining  change < -CHANGE_T
  restore_area          crops and pasture both present, both below, both declining
  good_land_underused   crops present and not below, pasture present and below
  system_misfit         crops present and below, pasture present and not below
  area_declining        every present group below and at least one declining (not restore_area)
  area_fine             at least one group present and none of the above
  none                  neither group present

Field call, in order (first match wins):
  none                no comparison possible: change_class no_data, or a switched field with no 2024 value
  abandon             the bare-soil rule of version 1 (below cell peers in both years, declining,
                      2024 integral under the 20th percentile of the class in the state)
  converted_below     newly cropped (not crop or pasture in 2020), 2024 below ecoregion peers (r_eco_2024 < -0.5)
  converted_ok        newly cropped, 2024 at or above ecoregion peers, or no 2024 ecoregion value
  restore             the cell's area call is restore_area
  convert_pasture     a pasture field not above its cell peers in a good_land_underused cell
  switch_paid_off     crop group switched, 2024 at or above cell peers (r_adj_2024 >= -0.5)
  switch_failed       crop group switched, 2024 below cell peers
  improve_yields      same crop, declined against cell peers, or below them in 2024
  intensify           same crop, at cell peers and not declining
  keep                same crop, above cell peers and not declining
  abandoned_outline   2020 outline with no crop or pasture in 2024 (abandoned layer)

Every field keeps the version 1 decision as decision_v1. eco_trend is the ecoregion-class
Scale C change (ecoregion median against the national median, national cell SD units) read as
declining (<= -ECO_T), gaining (>= ECO_T) or steady; it is context and does not enter the call.
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

SOURCE = "modis"
OUT = os.path.join(C.ANALYSIS, "decisions")
ECO = os.path.join(C.ANALYSIS, "ecoregions")
CELL_CSV = os.path.join(C.SUMMARIES, "cell_vs_ecoregion.csv")
ECO_CSV = os.path.join(C.SUMMARIES, "ecoregions.csv")

CROP_CLASSES = [39, 19, 20, 40, 62, 46, 47, 48, 35]  # peer classes; 41 pools into 19
PASTURE = 15
MOSAIC = 21
LEVEL_T = 0.75    # national cell SD of the class
CHANGE_T = 0.4    # national cell SD of the class
MIN_FIELDS = 30   # per class row, inherited from s06 MIN_CELL
FIELD_LEVEL = 0.5  # cell peer SD, as in version 1
ECO_T = 0.1       # national cell SD

AREA = ["restore_area", "good_land_underused", "system_misfit", "area_declining", "area_fine", "none"]
DECISIONS = ["restore", "converted_below", "converted_ok", "convert_pasture", "switch_paid_off", "switch_failed",
             "improve_yields", "intensify", "keep", "abandon", "abandoned_outline", "none"]
DECISIONS_V1 = ["restore", "switch_crop", "change_pattern", "abandon", "intensify", "improve_yields", "keep", "none"]
TRENDS = ["declining", "steady", "gaining", "unknown"]
FRONTIER = ["Madeira-Tapajós moist forests", "Xingu-Tocantins-Araguaia moist forests", "Mato Grosso tropical dry forests",
            "Tocantins/Pindare moist forests", "Tapajós-Xingu moist forests", "Purus-Madeira moist forests",
            "Southwest Amazon moist forests"]


def log(**kw):
    kw["t"] = datetime.now().isoformat(timespec="seconds")
    print(json.dumps(kw, ensure_ascii=False, default=str), flush=True)


# ----------------------------------------------------------------------------- national reference

def national(states, levels=(5, 6)):
    """cell_vs_nation and the plain change per (H3 cell, peer class), at resolutions 5 and 6.

    cell_vs_nation = (cell median of metric_adj - national class median of metric_adj) /
    (1.4826 MAD of the national distribution of cell medians of the class), over cells with at
    least MIN_FIELDS valid fields of the class, per year; the unit is computed per resolution.
    plain_pct = 100 * median(metric_adj_2024 - metric_adj_2020) / median(metric_adj_2020) over
    the cell's fields valid in both years with the same peer class (at least MIN_FIELDS)."""
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    frames = {}
    for ay in (2020, 2024):
        parts = []
        for s in states:
            m = read(C.metrics_path(SOURCE, 2024, ay, s), ["fid", "peer_cls", "h3_5", "h3_6"])
            r = read(C.relative_path(SOURCE, 2024, ay, s), ["fid", "valid", "metric_adj"])
            assert np.array_equal(m["fid"].values, r["fid"].values), "relative table order differs"
            parts.append(pd.DataFrame({"cls": m["peer_cls"].values.astype(np.int16), "h3_5": m["h3_5"].values,
                                       "h3_6": m["h3_6"].values, "valid": r["valid"].values,
                                       "m": r["metric_adj"].values.astype(np.float32)}))
        frames[ay] = pd.concat(parts, ignore_index=True)
        log(step="national", ay=ay, rows=len(frames[ay]), seconds=round(time.time() - t0))
    f20, f24 = frames[2020], frames[2024]
    out = {}
    summary = {}
    for res in levels:
        key = f"h3_{res}"
        per_year = {}
        for ay, f in frames.items():
            v = f[f["valid"].values & np.isfinite(f["m"].values)]
            nat_med = v.groupby("cls")["m"].median()
            cell = v.groupby([key, "cls"])["m"].agg(["median", "size"]).reset_index()
            big = cell[cell["size"] >= MIN_FIELDS]
            cell_sd = big.groupby("cls")["median"].agg(lambda x: 1.4826 * np.median(np.abs(x - np.median(x))))
            big = big.assign(v=(big["median"] - big["cls"].map(nat_med)) / big["cls"].map(cell_sd))
            per_year[ay] = big.rename(columns={key: "cell", "size": f"n_{ay}", "v": f"v{ay % 100}"})[["cell", "cls", f"n_{ay}", f"v{ay % 100}"]]
            summary[f"r{res}_{ay}"] = {"cells_classes": int(len(big)),
                                       "cell_sd": {int(k): round(float(x), 4) for k, x in cell_sd.items()},
                                       "nat_med": {int(k): round(float(x), 4) for k, x in nat_med.items()}}
        t = per_year[2020].merge(per_year[2024], on=["cell", "cls"], how="outer")
        t["change"] = t["v24"] - t["v20"]
        ok = (f20["valid"].values & f24["valid"].values & (f20["cls"].values == f24["cls"].values)
              & np.isfinite(f20["m"].values) & np.isfinite(f24["m"].values))
        p = pd.DataFrame({"cell": f24[key].values[ok], "cls": f24["cls"].values[ok],
                          "d": f24["m"].values[ok] - f20["m"].values[ok], "m20": f20["m"].values[ok]})
        pl = p.groupby(["cell", "cls"]).agg(n_both=("d", "size"), md=("d", "median"), m20=("m20", "median")).reset_index()
        pl = pl[pl["n_both"] >= MIN_FIELDS]
        with np.errstate(all="ignore"):
            pl["pct"] = 100 * pl["md"] / pl["m20"]
        t = t.merge(pl[["cell", "cls", "n_both", "pct"]], on=["cell", "cls"], how="left")
        t["n_2020"] = t["n_2020"].fillna(0).astype(np.int32)
        t["n_2024"] = t["n_2024"].fillna(0).astype(np.int32)
        t["n_both"] = t["n_both"].fillna(0).astype(np.int32)
        t.to_parquet(os.path.join(OUT, f"cell_nation_r{res}.parquet"), index=False)
        out[res] = t
        if res == 5:
            import h3
            csv = t.copy()
            csv.insert(0, "h3_5", [h3.int_to_str(int(x)) for x in csv["cell"]])
            csv = csv.drop(columns="cell").rename(columns={"cls": "peer_cls", "v20": "cell_vs_nation_2020", "v24": "cell_vs_nation_2024",
                                                            "pct": "plain_change_pct"})
            csv.to_csv(os.path.join(C.SUMMARIES, "cell_vs_nation.csv.gz"), index=False, float_format="%.3f")
        log(step="national", res=res, rows=int(len(t)), with_change=int(np.isfinite(t["change"]).sum()),
            with_pct=int(np.isfinite(t["pct"]).sum()), seconds=round(time.time() - t0))
    with open(os.path.join(OUT, "national_summary.json"), "w") as fh:
        json.dump(summary, fh, indent=1)
    return out


def group_of(cls):
    cls = np.asarray(cls)
    return np.where(np.isin(cls, CROP_CLASSES), "crops", np.where(cls == PASTURE, "pasture", np.where(cls == MOSAIC, "mosaic", "other")))


def load_nation(res=5):
    c = pd.read_parquet(os.path.join(OUT, f"cell_nation_r{res}.parquet"))
    c["group"] = group_of(c["cls"].values)
    return c


def frontier(c):
    """Class-weighted national change and plain percent change per cell, over every class (the frontier map)."""
    ch = c[np.isfinite(c["change"])]
    ch = ch.assign(wv=ch["n_2024"] * ch["change"]).groupby("cell").agg(w=("n_2024", "sum"), wv=("wv", "sum"))
    pc = c[np.isfinite(c["pct"])]
    pc = pc.assign(wv=pc["n_both"] * pc["pct"]).groupby("cell").agg(w=("n_both", "sum"), wv=("wv", "sum"))
    return pd.DataFrame({"nat_change": ch["wv"] / ch["w"]}).join(pd.DataFrame({"nat_pct_change": pc["wv"] / pc["w"]}), how="outer")


# ----------------------------------------------------------------------------- area

def load_cells():
    """The ecoregion area term of s06 (secondary context since the national reference became primary)."""
    c = pd.read_csv(CELL_CSV)
    c["cell"] = c["h3_5"].map(lambda s: int(s, 16)).astype(np.int64)
    c["group"] = group_of(c["peer_cls"].values)
    return c


def pool(c, group, lv_col, ch_col, prefix=""):
    g = c[c["group"] == group]
    lv = g[np.isfinite(g[lv_col])]
    lv = lv.assign(w=lv["n_2024"], wv=lv["n_2024"] * lv[lv_col]).groupby("cell").agg(w=("w", "sum"), wv=("wv", "sum"))
    ch = g[np.isfinite(g[ch_col])]
    ch = ch.assign(w=ch["n_2024"], wv=ch["n_2024"] * ch[ch_col]).groupby("cell").agg(w=("w", "sum"), wv=("wv", "sum"))
    out = pd.DataFrame({f"{prefix}{group}_level": lv["wv"] / lv["w"], f"{prefix}{group}_n": lv["w"]})
    out = out.join(pd.DataFrame({f"{prefix}{group}_change": ch["wv"] / ch["w"]}), how="outer")
    return out


def area_call(t):
    n = len(t)
    cp = np.isfinite(t["crops_level"].values)
    pp = np.isfinite(t["pasture_level"].values)
    cb = cp & (t["crops_level"].values < -LEVEL_T)
    pb = pp & (t["pasture_level"].values < -LEVEL_T)
    with np.errstate(invalid="ignore"):
        cd = cp & (t["crops_change"].values < -CHANGE_T)
        pd_ = pp & (t["pasture_change"].values < -CHANGE_T)
    out = np.full(n, "none", dtype=object)
    out[cp | pp] = "area_fine"
    all_below = (cp | pp) & (~cp | cb) & (~pp | pb)
    out[all_below & (cd | pd_)] = "area_declining"
    out[cp & pp & ~cb & pb] = "good_land_underused"
    out[cp & pp & cb & ~pb] = "system_misfit"
    out[cp & pp & cb & pb & cd & pd_] = "restore_area"
    return out


def build_area():
    """Area call per H3 resolution 5 cell on the national reference; the ecoregion terms ride along as context."""
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    n = load_nation(5)
    t = pool(n, "crops", "v24", "change").join(pool(n, "pasture", "v24", "change"), how="outer") \
        .join(pool(n, "mosaic", "v24", "change"), how="outer").join(frontier(n), how="outer")
    e = load_cells()
    t = t.join(pool(e, "crops", "cell_vs_eco_2024", "change", "eco_"), how="outer") \
        .join(pool(e, "pasture", "cell_vs_eco_2024", "change", "eco_"), how="outer")
    dom = e.groupby(["cell", "eco_id"])["n_2024"].sum().reset_index().sort_values("n_2024").drop_duplicates("cell", keep="last")
    t = t.join(dom.set_index("cell")["eco_id"])
    eco = pd.read_csv(ECO_CSV)
    allrow = eco[eco["peer_cls"] == "all"].set_index("eco_id")
    t["eco_scale_c_change"] = t["eco_id"].map(allrow["scale_c_change"])
    t["eco_plain_change_pct"] = t["eco_id"].map(allrow["plain_change_pct"])
    t["eco_trend"] = trend(t["eco_scale_c_change"].values)
    t["area_decision"] = area_call(t)
    t.index.name = "cell"
    t = t.reset_index()
    t.to_parquet(os.path.join(OUT, "area_cells.parquet"), index=False)
    import h3
    out = t.copy()
    out.insert(0, "h3_5", [h3.int_to_str(int(x)) for x in out["cell"]])
    out.drop(columns="cell").to_csv(os.path.join(C.SUMMARIES, "area_cells.csv.gz"), index=False, float_format="%.3f")
    # resolution 6 frontier values for the dense summary level
    f6 = frontier(load_nation(6))
    f6.index.name = "cell"
    f6.reset_index().to_parquet(os.path.join(OUT, "frontier_r6.parquet"), index=False)
    vc = t["area_decision"].value_counts()
    log(step="area", cells=int(len(t)), **{k: int(vc.get(k, 0)) for k in AREA}, r6_cells=int(len(f6)), seconds=round(time.time() - t0))
    return t


def trend(v):
    v = np.asarray(v, dtype=float)
    out = np.full(len(v), "unknown", dtype=object)
    ok = np.isfinite(v)
    out[ok] = "steady"
    out[ok & (v <= -ECO_T)] = "declining"
    out[ok & (v >= ECO_T)] = "gaining"
    return out


def dist():
    """Quantiles of the pooled national area term and of the frontier values, to set the thresholds and breaks."""
    q = [0.05, 0.1, 0.2, 0.25, 0.5, 0.75, 0.8, 0.9, 0.95]
    res = {}
    for r in (5, 6):
        c = load_nation(r)
        for grp in ("crops", "pasture", "mosaic"):
            p = pool(c, grp, "v24", "change")
            lv = p[f"{grp}_level"].dropna()
            ch = p[f"{grp}_change"].dropna()
            res[f"r{r}_{grp}"] = {"cells_level": int(len(lv)), "cells_change": int(len(ch)),
                                  "level_q": {str(k): round(float(lv.quantile(k)), 3) for k in q},
                                  "change_q": {str(k): round(float(ch.quantile(k)), 3) for k in q},
                                  "n_median": float(p[f"{grp}_n"].median())}
        fr = frontier(c)
        for col in ("nat_change", "nat_pct_change"):
            v = fr[col].dropna()
            res[f"r{r}_{col}"] = {"cells": int(len(v)), "q": {str(k): round(float(v.quantile(k)), 3) for k in q}}
    print(json.dumps(res, indent=1))
    return res


# ----------------------------------------------------------------------------- fields

def read(path, cols):
    return pq.read_table(path, columns=cols).to_pandas()


def eco_lookup():
    eco = pd.read_csv(ECO_CSV)
    cls = eco[eco["peer_cls"] != "all"].copy()
    cls["peer_cls"] = cls["peer_cls"].astype(int)
    return cls.set_index(["eco_id", "peer_cls"])["scale_c_change"]


def field_call(cc, dec_v1, r24, r_eco24, crop24, area, peer24):
    n = len(cc)
    out = np.full(n, "none", dtype=object)
    level_below = r24 < -FIELD_LEVEL
    level_above = r24 > FIELD_LEVEL
    has24 = np.isfinite(r24)
    same = np.isin(cc, ["large_decline", "decline", "stable", "gain", "large_gain"])
    declining = np.isin(cc, ["large_decline", "decline"])
    # same crop
    out[same & ~declining & ~level_below & ~level_above] = "intensify"
    out[same & ~declining & level_above] = "keep"
    out[same & (declining | level_below)] = "improve_yields"
    # switched
    sw = cc == "crop_switched"
    out[sw & has24 & ~level_below] = "switch_paid_off"
    out[sw & has24 & level_below] = "switch_failed"
    # area tier
    out[(same | (sw & has24)) & (area == "good_land_underused") & (crop24 == PASTURE) & ~level_above] = "convert_pasture"
    out[(same | (sw & has24)) & (area == "restore_area")] = "restore"
    # recently converted, against ecoregion peers
    nc = cc == "newly_cropped"
    out[nc] = "converted_ok"
    out[nc & (r_eco24 < -FIELD_LEVEL)] = "converted_below"
    # bare-soil rule of version 1
    out[dec_v1 == "abandon"] = "abandon"
    return out


def fields_state(state, area_map, eco_cls):
    t0 = time.time()
    p = os.path.join(C.ANALYSIS, "year=2024", f"state={state}", "fields_scored.parquet")
    tab = pq.read_table(p)
    df_cols = tab.schema.names
    dec_v1 = (tab.column("decision_v1") if "decision_v1" in df_cols else tab.column("decision")).to_pandas().astype(str).values
    cc = tab.column("change_class").to_pandas().astype(str).values
    r24 = tab.column("r_adj_2024").to_numpy(zero_copy_only=False).astype(np.float32)
    crop24 = tab.column("crop_2024").to_numpy(zero_copy_only=False).astype(np.int16)
    fid = tab.column("fid").to_numpy()
    m = read(C.metrics_path(SOURCE, 2024, 2024, state), ["fid", "h3_5"])
    e = read(os.path.join(ECO, "fields", f"{state}.parquet"), ["fid", "eco_id", "peer_cls_2024", "r_eco_2024"])
    assert np.array_equal(m["fid"].values, fid) and np.array_equal(e["fid"].values, fid), "fid order differs"
    cell = m["h3_5"].values.astype(np.int64)
    area = pd.Series(cell).map(area_map).fillna("none").values.astype(object)
    r_eco24 = e["r_eco_2024"].values.astype(np.float32)
    peer24 = e["peer_cls_2024"].values.astype(np.int64)
    dec = field_call(cc, dec_v1, r24, r_eco24, crop24, area, peer24)
    sc = eco_cls.reindex(pd.MultiIndex.from_arrays([e["eco_id"].values.astype(np.int64), peer24])).values
    tr = trend(sc)
    keep = [c for c in df_cols if c not in ("decision", "decision_v1", "area_decision", "eco_id", "eco_trend")]
    new = {c: tab.column(c) for c in keep}
    cols = {}
    for c in keep:
        cols[c] = new[c]
        if c == "change_class":
            cols["decision"] = pa.array(pd.Categorical(dec, categories=DECISIONS))
            cols["area_decision"] = pa.array(pd.Categorical(area, categories=AREA))
            cols["decision_v1"] = pa.array(pd.Categorical(dec_v1, categories=DECISIONS_V1))
            cols["eco_id"] = pa.array(e["eco_id"].values.astype(np.int32))
            cols["eco_trend"] = pa.array(pd.Categorical(tr, categories=TRENDS))
    out = pa.table(cols)
    meta = dict(tab.schema.metadata or {})
    meta[b"s07_decisions"] = json.dumps({"state": state, "level_t": LEVEL_T, "change_t": CHANGE_T, "eco_t": ECO_T,
                                         "written": datetime.now().isoformat(timespec="seconds")}).encode()
    out = out.replace_schema_metadata(meta)
    pq.write_table(out, p + ".part", compression="zstd", row_group_size=100_000)
    del tab, out
    os.replace(p + ".part", p)

    # abandoned 2020 outlines
    ab_p = os.path.join(C.ANALYSIS, "abandoned", f"state={state}.parquet")
    ab_area = {}
    if os.path.exists(ab_p):
        at = pq.read_table(ab_p)
        afid = at.column("fid").to_numpy()
        m20 = read(C.metrics_path(SOURCE, 2020, 2020, state), ["fid", "h3_5"]).set_index("fid")
        e20 = read(os.path.join(C.ANALYSIS, "weather_refit", "field_eco_2020", f"{state}.parquet"), ["fid", "eco_id"]).set_index("fid")
        acell = m20["h3_5"].reindex(afid).values
        aarea = pd.Series(acell).map(area_map).fillna("none").values.astype(object)
        aeco = e20["eco_id"].reindex(afid).fillna(0).values.astype(np.int32)
        acrop20 = at.column("crop_2020").to_numpy(zero_copy_only=False).astype(np.int64)
        apeer = np.where(acrop20 == 41, 19, acrop20)
        atr = trend(eco_cls.reindex(pd.MultiIndex.from_arrays([aeco.astype(np.int64), apeer])).values)
        akeep = [c for c in at.schema.names if c not in ("decision", "decision_v1", "area_decision", "eco_id", "eco_trend")]
        av1 = (at.column("decision_v1") if "decision_v1" in at.schema.names else at.column("decision")).to_pandas().astype(str).values
        acols = {}
        for c in akeep:
            acols[c] = at.column(c)
            if c == "change_class":
                acols["decision"] = pa.array(pd.Categorical(["abandoned_outline"] * len(afid), categories=DECISIONS))
                acols["area_decision"] = pa.array(pd.Categorical(aarea, categories=AREA))
                acols["decision_v1"] = pa.array(pd.Categorical(av1, categories=DECISIONS_V1))
                acols["eco_id"] = pa.array(aeco)
                acols["eco_trend"] = pa.array(pd.Categorical(atr, categories=TRENDS))
        aout = pa.table(acols).replace_schema_metadata(at.schema.metadata)
        pq.write_table(aout, ab_p + ".part", compression="zstd", row_group_size=100_000)
        os.replace(ab_p + ".part", ab_p)
        ab_area = {k: int(v) for k, v in pd.Series(aarea).value_counts().items()}

    # counts.json: version 1 decision kept as decision_v1
    cp = os.path.join(os.path.dirname(p), "counts.json")
    with open(cp) as fh:
        counts = json.load(fh)
    counts["decision"] = {k: int(v) for k, v in pd.Series(dec).value_counts().items()}
    counts["decision_v1"] = {k: int(v) for k, v in pd.Series(dec_v1).value_counts().items()}
    counts["area_decision"] = {k: int(v) for k, v in pd.Series(area).value_counts().items()}
    counts["area_decision_abandoned"] = ab_area
    counts["eco_trend"] = {k: int(v) for k, v in pd.Series(tr).value_counts().items()}
    with open(cp, "w") as fh:
        json.dump(counts, fh, indent=1)
    # slim per-field table for the report
    slim = pd.DataFrame({"fid": fid, "state": state, "cell": cell, "eco_id": e["eco_id"].values.astype(np.int32),
                         "decision": dec, "decision_v1": dec_v1, "area_decision": area, "change_class": cc, "crop_2024": crop24})
    os.makedirs(os.path.join(OUT, "fields"), exist_ok=True)
    slim.to_parquet(os.path.join(OUT, "fields", f"{state}.parquet"), index=False)
    return {"state": state, "rows": int(len(fid)), "abandoned": int(sum(ab_area.values())), "seconds": round(time.time() - t0, 1)}


def fields(states):
    t = pd.read_parquet(os.path.join(OUT, "area_cells.parquet"))
    area_map = pd.Series(t["area_decision"].values, index=t["cell"].values)
    eco_cls = eco_lookup()
    for s in states:
        log(step="fields", **fields_state(s, area_map, eco_cls))


# ----------------------------------------------------------------------------- report

def report(states):
    t0 = time.time()
    uf = C.state_uf_map(2024)
    df = pd.concat([pd.read_parquet(os.path.join(OUT, "fields", f"{s}.parquet")) for s in states], ignore_index=True)
    df["uf"] = df["state"].map(uf)
    names = pd.read_csv(ECO_CSV)[["eco_id", "eco_name"]].drop_duplicates("eco_id").set_index("eco_id")["eco_name"]
    df["eco_name"] = df["eco_id"].map(names).fillna("none")
    ab = {}
    for s in states:
        with open(os.path.join(C.ANALYSIS, "year=2024", f"state={s}", "counts.json")) as fh:
            ab[uf[s]] = json.load(fh).get("abandoned", 0)
    nat = {"decision": df["decision"].value_counts().reindex(DECISIONS, fill_value=0).to_dict(),
           "area_decision_fields": df["area_decision"].value_counts().reindex(AREA, fill_value=0).to_dict(),
           "abandoned_outlines": int(sum(ab.values()))}
    nat["decision"]["abandoned_outline"] = nat["abandoned_outlines"]
    cells = pd.read_parquet(os.path.join(OUT, "area_cells.parquet"))
    nat["area_decision_cells"] = cells["area_decision"].value_counts().reindex(AREA, fill_value=0).to_dict()
    by_state = pd.crosstab(df["uf"], df["decision"]).reindex(columns=DECISIONS, fill_value=0)
    by_state["abandoned_outline"] = by_state.index.map(ab)
    by_state.to_csv(os.path.join(C.SUMMARIES, "decisions_v2_by_state.csv"))
    pd.crosstab(df["uf"], df["area_decision"]).reindex(columns=AREA, fill_value=0).to_csv(os.path.join(C.SUMMARIES, "area_decisions_by_state.csv"))
    cross = pd.crosstab(df["decision_v1"], df["decision"]).reindex(index=DECISIONS_V1, columns=DECISIONS, fill_value=0)
    cross.to_csv(os.path.join(C.SUMMARIES, "decisions_v1_vs_v2.csv"))
    fr = df[df["eco_name"].isin(FRONTIER)]
    fr_dec = pd.crosstab(fr["eco_name"], fr["decision"]).reindex(columns=DECISIONS, fill_value=0)
    fr_area = pd.crosstab(fr["eco_name"], fr["area_decision"]).reindex(columns=AREA, fill_value=0)
    fr_dec.join(fr_area, rsuffix="_area").to_csv(os.path.join(C.SUMMARIES, "decisions_v2_frontier.csv"))
    area_class = pd.crosstab(df["area_decision"], df["decision"]).reindex(index=AREA, columns=DECISIONS, fill_value=0)
    area_class.to_csv(os.path.join(C.SUMMARIES, "area_vs_field_decision.csv"))
    res = {"national": nat,
           "frontier_total": {"fields": int(len(fr)), "decision": fr["decision"].value_counts().reindex(DECISIONS, fill_value=0).to_dict(),
                              "area_decision": fr["area_decision"].value_counts().reindex(AREA, fill_value=0).to_dict()},
           "v1_to_v2_same_key": int(sum(cross.loc[k, k] for k in DECISIONS_V1 if k in DECISIONS)),
           "fields": int(len(df)), "seconds": round(time.time() - t0)}
    with open(os.path.join(C.SUMMARIES, "decisions_v2.json"), "w") as fh:
        json.dump(res, fh, indent=1, default=int)
    log(step="report", **{k: v for k, v in res.items() if k != "national"})
    print(json.dumps(nat, indent=1, default=int))
    print(cross.to_string())
    print(fr_dec.to_string())
    print(fr_area.to_string())


def lookup():
    """docs/data/ecoregions.json: names, class-weighted and per-class Scale C change and plain change."""
    eco = pd.read_csv(ECO_CSV)
    out = {}
    for eid, sub in eco.groupby("eco_id"):
        allr = sub[sub["peer_cls"] == "all"].iloc[0]
        rec = {"name": allr["eco_name"], "c": rnd(allr["scale_c_change"]), "p": rnd(allr["plain_change_pct"], 1), "k": {}}
        for _, r in sub[sub["peer_cls"] != "all"].iterrows():
            if np.isfinite(r["scale_c_change"]) or np.isfinite(r["plain_change_pct"]):
                rec["k"][str(int(r["peer_cls"]))] = [rnd(r["scale_c_change"]), rnd(r["plain_change_pct"], 1)]
        out[str(int(eid))] = rec
    p = os.path.join(C.REPO, "docs", "data", "ecoregions.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"trend_threshold": ECO_T, "ecoregions": out}, fh, ensure_ascii=False, separators=(",", ":"))
    log(step="lookup", ecoregions=len(out), bytes=os.path.getsize(p))


def rnd(v, d=2):
    return None if v is None or not np.isfinite(v) else round(float(v), d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["national", "dist", "area", "fields", "report", "lookup", "all"])
    ap.add_argument("--states", nargs="*", default=None)
    args = ap.parse_args()
    states = args.states or C.state_dirs(2024)
    if args.step in ("national", "all"):
        national(states)
    if args.step == "dist":
        dist()
    if args.step in ("area", "all"):
        build_area()
    if args.step in ("fields", "all"):
        fields(states)
    if args.step in ("report", "all"):
        report(states)
    if args.step in ("lookup", "all"):
        lookup()


if __name__ == "__main__":
    main()
