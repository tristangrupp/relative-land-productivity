"""Stage 6 (exploration): relative productivity against RESOLVE 2017 ecoregion peers.

  python s06_ecoregion_peers.py assign      rasterize the ecoregions and assign every 2024 field
  python s06_ecoregion_peers.py score       Scale B and Scale C scores, per-field tables, CSVs
  python s06_ecoregion_peers.py figures     the five PNG figures under docs/figures/ecoregions/
  python s06_ecoregion_peers.py all

The question this stage explores is written up in pipeline/EXPLORE_ECOREGIONS.md. The existing
product (Scale A, s04_relative.py) scores a field against the peers of the same MapBiomas class
in its H3 resolution 5 cell, so a decline shared by a whole region cancels out. This stage keeps
the same weather-adjusted metric (metric_adj, reproduced here with the saved fit so it matches
the s04 tables) and builds two larger references:

Scale B. Field against its ecoregion peers: group (ECO_ID, peer class, year) over valid fields,
at least 30 fields, r_eco = (metric_adj - median) / (1.4826 MAD). D_eco = r_eco_2024 -
r_eco_2020 when the peer class is the same in both years, classed at the METHODS.md section 6
thresholds. The cell-within-ecoregion term is the H3 resolution 5 cell median of metric_adj
(cells with at least 30 valid fields of the class inside the ecoregion) against the
ecoregion-class median, in the same robust SD units.

Scale C. Ecoregion against the nation, per class: the ecoregion-class median of metric_adj
minus the national class median of metric_adj, divided by 1.4826 MAD of the national
distribution of H3 resolution 5 cell medians of the class (cells with at least 30 valid
fields). The plain weather-adjusted change is the median over the ecoregion's fields of
(metric_adj_2024 - metric_adj_2020), fields valid in both years with the same peer class,
divided by the ecoregion-class median of metric_adj_2020.

Inputs: analysis\\metrics\\source=modis\\polys=2024\\ay=<2020|2024>\\<State>.parquet, the saved
weather fit analysis\\relative\\source=modis\\weather_fit.json, analysis\\relative\\...\\<State>.parquet
(only to verify metric_adj and to read Scale A), analysis\\year=2024\\state=<State>\\
fields_scored.parquet (Scale A change_class), raw\\ecoregions\\Ecoregions2017.shp.

Outputs under analysis\\ecoregions\\: eco_grid.npz (the rasterized ECO_ID grid),
ecoregions_brazil.gpkg (the clipped polygons with names), field_eco\\<State>.parquet (fid,
eco_id, eco_filled), fields\\<State>.parquet (per-field Scale B values and classes), and
the three committed CSVs in data/summaries/ (ecoregions.csv, ecoregions_by_biome.csv,
cell_vs_ecoregion.csv). No Earth Engine, no AWS compute, nothing under E:\\ is touched.
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
import s04_relative as R  # noqa: E402

ECO_RAW = os.path.join(C.DATA, "raw", "ecoregions", "Ecoregions2017.shp")
BIOMES_BR = r"D:\WRI\Field Boundaries\Biomes\Brazil_biomes\Brazil_biomes.shp"  # IBGE biomes, used only as the national outline on maps
OUT = os.path.join(C.ANALYSIS, "ecoregions")
FIELD_ECO = os.path.join(OUT, "field_eco")
FIELDS_OUT = os.path.join(OUT, "fields")
FIG_DIR = os.path.join(C.REPO, "docs", "figures", "ecoregions")
SOURCE = "modis"
POLYS = 2024
AYS = [2020, 2024]

# Grid over Brazil's bounding box, 0.005 degree cells (about 550 m), ECO_ID as int32, 0 = none.
X0, Y0, X1, Y1 = -74.1, -33.9, -34.7, 5.4
RES = 0.005
NCOL = int(round((X1 - X0) / RES))
NROW = int(round((Y1 - Y0) / RES))
FILL_CELLS = 10  # nearest ecoregion within 0.05 degree for fields that fall on no ecoregion

MIN_GROUP = 30  # ecoregion-class peer groups, same as the cell design
MIN_CELL = 30   # a cell median enters only with 30 valid fields of the class
CLASSES5 = ["large_decline", "decline", "stable", "gain", "large_gain"]
ALL_CLASSES = CLASSES5 + ["crop_switched", "no_data"]
FRONTIER = ["Madeira-Tapajós moist forests", "Xingu-Tocantins-Araguaia moist forests", "Mato Grosso tropical dry forests",
            "Tocantins/Pindare moist forests", "Tapajós-Xingu moist forests", "Purus-Madeira moist forests",
            "Southwest Amazon moist forests", "Cerrado", "Caatinga", "Alto Paraná Atlantic forests", "Uruguayan savanna", "Pantanal"]


def log(**kw):
    kw["t"] = datetime.now().isoformat(timespec="seconds")
    print(json.dumps(kw, ensure_ascii=False, default=str), flush=True)


def change_class(D):
    out = np.full(len(D), "no_data", dtype=object)
    ok = np.isfinite(D)
    out[ok & (D < -2)] = "large_decline"
    out[ok & (D >= -2) & (D < -1)] = "decline"
    out[ok & (D >= -1) & (D <= 1)] = "stable"
    out[ok & (D > 1) & (D <= 2)] = "gain"
    out[ok & (D > 2)] = "large_gain"
    return out


# ----------------------------------------------------------------------------------------------
# assign
# ----------------------------------------------------------------------------------------------

def read_ecoregions():
    import pyogrio
    pyogrio.set_gdal_config_options({"SHAPE_ENCODING": "ISO-8859-1"})  # the DBF is latin-1 without a .cpg
    g = pyogrio.read_dataframe(ECO_RAW, bbox=(X0 - 0.5, Y0 - 0.5, X1 + 0.5, Y1 + 0.5),
                               columns=["ECO_ID", "ECO_NAME", "BIOME_NUM", "BIOME_NAME", "REALM"])
    g["ECO_ID"] = g["ECO_ID"].astype(np.int32)
    g["BIOME_NUM"] = g["BIOME_NUM"].astype(int)
    return g


def rasterize_ecoregions(g):
    from rasterio import features
    from rasterio.transform import from_origin
    transform = from_origin(X0, Y1, RES, RES)
    shapes = ((geom, int(eid)) for geom, eid in zip(g.geometry, g["ECO_ID"]))
    grid = features.rasterize(shapes, out_shape=(NROW, NCOL), transform=transform, fill=0, dtype="int32", all_touched=False)
    return grid


def grid_index(lon, lat):
    col = np.floor((lon - X0) / RES).astype(np.int64)
    row = np.floor((Y1 - lat) / RES).astype(np.int64)
    inside = (col >= 0) & (col < NCOL) & (row >= 0) & (row < NROW)
    return row, col, inside


def assign(states, force=False):
    t0 = time.time()
    os.makedirs(FIELD_ECO, exist_ok=True)
    grid_path = os.path.join(OUT, "eco_grid.npz")
    gpkg = os.path.join(OUT, "ecoregions_brazil.gpkg")
    if os.path.exists(grid_path) and os.path.exists(gpkg) and not force:
        grid = np.load(grid_path)["grid"]
        log(step="assign", grid="cached", shape=list(grid.shape))
    else:
        g = read_ecoregions()
        g.to_file(gpkg, driver="GPKG")
        grid = rasterize_ecoregions(g)
        np.savez_compressed(grid_path, grid=grid)
        log(step="assign", grid="rasterized", shape=list(grid.shape), ecoregions_in_bbox=int(len(g)),
            cells_with_eco=int((grid > 0).sum()), seconds=round(time.time() - t0))
    # nearest ecoregion cell for the no-ecoregion cells (coast, large rivers), capped at FILL_CELLS
    from scipy import ndimage
    dist, (ri, ci) = ndimage.distance_transform_edt(grid == 0, return_indices=True)
    log(step="assign", edt_seconds=round(time.time() - t0))
    totals = {"fields": 0, "direct": 0, "filled": 0, "unassigned": 0, "outside_bbox": 0}
    for s in states:
        p = os.path.join(FIELD_ECO, f"{s}.parquet")
        if os.path.exists(p) and not force:
            t = pq.read_table(p, columns=["eco_id", "eco_filled"]).to_pandas()
            totals["fields"] += len(t)
            totals["direct"] += int(((t.eco_id > 0) & ~t.eco_filled).sum())
            totals["filled"] += int(t.eco_filled.sum())
            totals["unassigned"] += int((t.eco_id == 0).sum())
            continue
        m = pq.read_table(C.metrics_path(SOURCE, POLYS, 2024, s), columns=["fid", "lon", "lat"]).to_pandas()
        lon = m["lon"].values.astype(np.float64)
        lat = m["lat"].values.astype(np.float64)
        row, col, inside = grid_index(lon, lat)
        eco = np.zeros(len(m), np.int32)
        filled = np.zeros(len(m), bool)
        eco[inside] = grid[row[inside], col[inside]]
        miss = inside & (eco == 0)
        if miss.any():
            d = dist[row[miss], col[miss]]
            near = eco.copy()
            near[miss] = grid[ri[row[miss], col[miss]], ci[row[miss], col[miss]]]
            ok = d <= FILL_CELLS
            idx = np.where(miss)[0][ok]
            eco[idx] = near[idx]
            filled[idx] = True
        out = pa.Table.from_pandas(pd.DataFrame({"fid": m["fid"].values, "eco_id": eco, "eco_filled": filled}), preserve_index=False)
        pq.write_table(out, p + ".part", compression="zstd")
        os.replace(p + ".part", p)
        rec = {"state": s, "fields": int(len(m)), "direct": int(((eco > 0) & ~filled).sum()), "filled": int(filled.sum()),
               "unassigned": int((eco == 0).sum()), "outside_bbox": int((~inside).sum())}
        for k in totals:
            totals[k] += rec[k]
        log(step="assign", **rec, seconds=round(time.time() - t0))
    log(step="assign", done=True, **totals, seconds=round(time.time() - t0))
    with open(os.path.join(OUT, "assign_summary.json"), "w") as fh:
        json.dump(totals, fh, indent=1)


# ----------------------------------------------------------------------------------------------
# score
# ----------------------------------------------------------------------------------------------

def load_adjusted(ay, states, fit, verify_state=None):
    """fid, peer_cls, valid, h3_5, metric_adj, state for one agricultural year on the 2024 polygons."""
    df = R.load_year(SOURCE, POLYS, ay, states)
    df["metric_adj"] = R.apply_weather(df, fit)
    log(step="score", ay=ay, rows=len(df), valid=int(df["valid"].sum()), term_capped=R.apply_weather.capped)
    if verify_state:
        ref = pq.read_table(C.relative_path(SOURCE, POLYS, ay, verify_state), columns=["fid", "metric_adj", "valid"]).to_pandas()
        sub = df.loc[df["state"] == verify_state, ["fid", "metric_adj", "valid"]]
        assert np.array_equal(sub["fid"].values, ref["fid"].values), "fid order differs from the relative table"
        both = np.isfinite(sub["metric_adj"].values) & np.isfinite(ref["metric_adj"].values)
        diff = float(np.nanmax(np.abs(sub["metric_adj"].values[both] - ref["metric_adj"].values[both])))
        nan_mismatch = int((np.isfinite(sub["metric_adj"].values) != np.isfinite(ref["metric_adj"].values)).sum())
        valid_mismatch = int((sub["valid"].values != ref["valid"].values).sum())
        log(step="verify", ay=ay, state=verify_state, rows=len(ref), max_abs_diff_metric_adj=diff,
            nan_mismatch=nan_mismatch, valid_mismatch=valid_mismatch)
        if diff > 1e-4 or valid_mismatch:
            raise RuntimeError("metric_adj does not reproduce the s04_relative table")
    slim = pd.DataFrame({"fid": df["fid"].values, "peer_cls": df["peer_cls"].values.astype(np.int16),
                         "valid": df["valid"].values, "h3_5": df["h3_5"].values,
                         "metric_adj": df["metric_adj"].values.astype(np.float32), "state": df["state"].values})
    slim["state"] = slim["state"].astype("category")
    del df
    return slim


def attach_eco(slim, states):
    parts = []
    for s in states:
        parts.append(pq.read_table(os.path.join(FIELD_ECO, f"{s}.parquet"), columns=["fid", "eco_id"]).to_pandas())
    e = pd.concat(parts, ignore_index=True)
    assert np.array_equal(e["fid"].values, slim["fid"].values), "field_eco order differs from the metrics tables"
    slim["eco_id"] = e["eco_id"].values.astype(np.int32)


def robust_group(frame, keys, col, min_n):
    """median, 1.4826 MAD and n per group over the rows of frame; groups under min_n get NaN."""
    grp = frame.groupby(keys, sort=False, observed=True)[col]
    med = grp.transform("median").values
    n = grp.transform("size").values
    dev = pd.Series(np.abs(frame[col].values - med), index=frame.index)
    mad = dev.groupby([frame[k] for k in keys], sort=False, observed=True).transform("median").values
    sd = 1.4826 * mad
    small = n < min_n
    med = np.where(small, np.nan, med)
    sd = np.where(small, np.nan, sd)
    return med.astype(np.float32), sd.astype(np.float32), n.astype(np.int32)


def score_year(both, ay):
    """Scale B per field, cell-within-ecoregion per cell, Scale C per ecoregion-class, for one year."""
    cls = both[f"cls_{ay}"].values
    valid = both[f"valid_{ay}"].values & (both["eco_id"].values > 0) & np.isfinite(both[f"m_{ay}"].values)
    f = pd.DataFrame({"eco_id": both["eco_id"].values[valid], "cls": cls[valid], "h3_5": both["h3_5"].values[valid],
                      "m": both[f"m_{ay}"].values[valid]})
    # Scale B groups
    med, sd, n = robust_group(f, ["eco_id", "cls"], "m", MIN_GROUP)
    with np.errstate(all="ignore"):
        r = (f["m"].values - med) / sd
    r[~np.isfinite(r)] = np.nan
    r_eco = np.full(len(both), np.nan, np.float32)
    r_eco[valid] = r.astype(np.float32)
    eco_groups = pd.DataFrame({"eco_id": f["eco_id"].values, "cls": f["cls"].values, "eco_med": med, "eco_sd": sd, "n": n}) \
        .drop_duplicates(["eco_id", "cls"]).reset_index(drop=True)
    # cell medians inside the ecoregion
    cell = f.groupby(["h3_5", "eco_id", "cls"], sort=False).agg(cell_med=("m", "median"), n_cell=("m", "size")).reset_index()
    cell = cell.merge(eco_groups[["eco_id", "cls", "eco_med", "eco_sd"]], on=["eco_id", "cls"], how="left")
    with np.errstate(all="ignore"):
        cell["cell_vs_eco"] = np.where(cell["n_cell"] >= MIN_CELL, (cell["cell_med"] - cell["eco_med"]) / cell["eco_sd"], np.nan)
    cell.loc[~np.isfinite(cell["cell_vs_eco"]), "cell_vs_eco"] = np.nan
    # per-field cell term
    key = pd.MultiIndex.from_arrays([f["h3_5"].values, f["eco_id"].values, f["cls"].values])
    cidx = cell.set_index(["h3_5", "eco_id", "cls"])["cell_vs_eco"]
    cv = np.full(len(both), np.nan, np.float32)
    cv[valid] = cidx.reindex(key).values.astype(np.float32)
    # Scale C: national class distribution of cell medians (cells by class, ignoring ecoregions)
    nat_cells = f.groupby(["h3_5", "cls"], sort=False).agg(cell_med=("m", "median"), n_cell=("m", "size")).reset_index()
    nat_cells = nat_cells[nat_cells["n_cell"] >= MIN_CELL]
    nat = nat_cells.groupby("cls").agg(cells=("cell_med", "size"),
                                       cell_med_median=("cell_med", "median"),
                                       cell_sd=("cell_med", lambda x: 1.4826 * np.median(np.abs(x - np.median(x))))).reset_index()
    nat_field = f.groupby("cls").agg(nat_med=("m", "median"), nat_n=("m", "size")).reset_index()
    nat = nat.merge(nat_field, on="cls", how="outer")
    eco_groups = eco_groups.merge(nat, on="cls", how="left")
    with np.errstate(all="ignore"):
        eco_groups["scale_c"] = (eco_groups["eco_med"] - eco_groups["nat_med"]) / eco_groups["cell_sd"]
    eco_groups.loc[~np.isfinite(eco_groups["scale_c"]), "scale_c"] = np.nan
    return r_eco, cv, cell, eco_groups, nat


def score(states, verify_state="Acre", force=False):
    t0 = time.time()
    os.makedirs(FIELDS_OUT, exist_ok=True)
    os.makedirs(C.SUMMARIES, exist_ok=True)
    fit = pd.read_json(os.path.join(C.RELATIVE, f"source={SOURCE}", "weather_fit.json"), orient="records")
    a20 = load_adjusted(2020, states, fit, verify_state)
    a24 = load_adjusted(2024, states, fit, verify_state)
    assert np.array_equal(a20["fid"].values, a24["fid"].values), "fid order differs between the two years"
    attach_eco(a24, states)
    both = pd.DataFrame({"fid": a24["fid"].values, "eco_id": a24["eco_id"].values, "h3_5": a24["h3_5"].values,
                         "state": a24["state"].values,
                         "cls_2020": a20["peer_cls"].values, "cls_2024": a24["peer_cls"].values,
                         "valid_2020": a20["valid"].values, "valid_2024": a24["valid"].values,
                         "m_2020": a20["metric_adj"].values, "m_2024": a24["metric_adj"].values})
    del a20, a24
    log(step="score", merged_rows=len(both), with_eco=int((both["eco_id"] > 0).sum()), seconds=round(time.time() - t0))

    per_year = {}
    for ay in AYS:
        per_year[ay] = score_year(both, ay)
        r_eco, cv, cell, eco_groups, nat = per_year[ay]
        both[f"r_eco_{ay}"] = r_eco
        both[f"cell_vs_eco_{ay}"] = cv
        log(step="score", ay=ay, scored_b=int(np.isfinite(r_eco).sum()), eco_groups=int(eco_groups["eco_med"].notna().sum()),
            ecoregions=int(eco_groups.loc[eco_groups["eco_med"].notna(), "eco_id"].nunique()),
            cells_with_term=int(cell["cell_vs_eco"].notna().sum()), seconds=round(time.time() - t0))

    same = both["cls_2020"].values == both["cls_2024"].values
    # national class table: the Scale C unit (robust SD of cell medians) and the national plain change
    nat = per_year[2020][4].merge(per_year[2024][4], on="cls", suffixes=("_2020", "_2024"), how="outer")
    okn = both["valid_2020"].values & both["valid_2024"].values & same & np.isfinite(both["m_2020"].values) & np.isfinite(both["m_2024"].values)
    pn = pd.DataFrame({"cls": both["cls_2024"].values[okn], "d": both["m_2024"].values[okn] - both["m_2020"].values[okn], "m20": both["m_2020"].values[okn]})
    pn = pn.groupby("cls").agg(n_both=("d", "size"), median_diff=("d", "median"), median_2020_both=("m20", "median")).reset_index()
    pn["plain_change_pct"] = 100 * pn["median_diff"] / pn["median_2020_both"]
    nat = nat.merge(pn, on="cls", how="left")
    nat.insert(1, "crop_group", nat["cls"].map(C.CROP_GROUP))
    nat.to_csv(os.path.join(OUT, "national_class.csv"), index=False, float_format="%.4f")
    with np.errstate(all="ignore"):
        d_eco = np.where(same, both["r_eco_2024"].values - both["r_eco_2020"].values, np.nan).astype(np.float32)
    both["d_eco"] = d_eco
    cc = change_class(d_eco)
    cc[(~same) & both["valid_2020"].values & both["valid_2024"].values] = "crop_switched"
    both["eco_change_class"] = pd.Categorical(cc, categories=ALL_CLASSES)

    # Scale A change class for the same fields
    parts = []
    for s in states:
        parts.append(pq.read_table(os.path.join(C.ANALYSIS, f"year={POLYS}", f"state={s}", "fields_scored.parquet"),
                                   columns=["fid", "change_class"]).to_pandas())
    sa = pd.concat(parts, ignore_index=True)
    assert np.array_equal(sa["fid"].values, both["fid"].values), "fields_scored order differs"
    both["change_class_a"] = sa["change_class"].astype(str).values
    both["change_class_a"] = both["change_class_a"].astype("category")
    del sa
    log(step="score", classes_done=True, seconds=round(time.time() - t0))

    # per-field tables per state
    for s, sub in both.groupby("state", observed=True, sort=True):
        out = pd.DataFrame({"fid": sub["fid"].values, "eco_id": sub["eco_id"].values,
                            "peer_cls_2020": sub["cls_2020"].values, "peer_cls_2024": sub["cls_2024"].values,
                            "r_eco_2020": sub["r_eco_2020"].values, "r_eco_2024": sub["r_eco_2024"].values, "d_eco": sub["d_eco"].values,
                            "cell_vs_eco_2020": sub["cell_vs_eco_2020"].values, "cell_vs_eco_2024": sub["cell_vs_eco_2024"].values,
                            "eco_change_class": sub["eco_change_class"].values, "change_class_a": sub["change_class_a"].values})
        table = pa.Table.from_pandas(out, preserve_index=False)
        meta = dict(table.schema.metadata or {})
        meta[b"s06_ecoregion_peers"] = json.dumps({"state": s, "written": datetime.now().isoformat(timespec="seconds")}).encode()
        p = os.path.join(FIELDS_OUT, f"{s}.parquet")
        pq.write_table(table.replace_schema_metadata(meta), p + ".part", compression="zstd")
        os.replace(p + ".part", p)
    log(step="score", fields_written=True, seconds=round(time.time() - t0))

    # agreement matrix of Scale A and Scale B change classes
    five = both["change_class_a"].isin(CLASSES5).values & both["eco_change_class"].isin(CLASSES5).values
    agree = pd.crosstab(both.loc[five, "change_class_a"].astype(str), both.loc[five, "eco_change_class"].astype(str))
    agree = agree.reindex(index=CLASSES5, columns=CLASSES5, fill_value=0)
    agree.index.name = "scale_a"
    agree.columns.name = "scale_b"
    agree.to_csv(os.path.join(OUT, "agreement_matrix.csv"))
    full = pd.crosstab(both["change_class_a"].astype(str), both["eco_change_class"].astype(str))
    full.to_csv(os.path.join(OUT, "agreement_matrix_all.csv"))
    exact = int(np.trace(agree.values))
    direction = lambda c: np.where(np.isin(c, ["large_decline", "decline"]), -1, np.where(np.isin(c, ["gain", "large_gain"]), 1, 0))
    da = direction(both.loc[five, "change_class_a"].astype(str).values)
    db = direction(both.loc[five, "eco_change_class"].astype(str).values)
    agreement = {"fields_both_five": int(five.sum()), "exact": exact, "exact_share": exact / max(1, five.sum()),
                 "direction_agree": int((da == db).sum()), "direction_share": float((da == db).mean()) if five.any() else None,
                 "a_decline_b_not": int(((da == -1) & (db != -1)).sum()), "b_decline_a_not": int(((db == -1) & (da != -1)).sum()),
                 "opposite_sign": int(((da * db) == -1).sum())}
    log(step="score", **agreement)

    # ecoregion summaries
    eco_tab = build_ecoregion_table(both, per_year)
    eco_tab.to_csv(os.path.join(C.SUMMARIES, "ecoregions.csv"), index=False, float_format="%.4f")
    biome_tab = build_biome_table(both, per_year, eco_tab)
    biome_tab.to_csv(os.path.join(C.SUMMARIES, "ecoregions_by_biome.csv"), index=False, float_format="%.4f")
    cell_tab = build_cell_table(per_year)
    cell_tab.to_csv(os.path.join(C.SUMMARIES, "cell_vs_ecoregion.csv"), index=False, float_format="%.3f")
    summary = {"rows": int(len(both)), "with_eco": int((both["eco_id"] > 0).sum()),
               "scored_b_2020": int(np.isfinite(both["r_eco_2020"]).sum()), "scored_b_2024": int(np.isfinite(both["r_eco_2024"]).sum()),
               "d_eco": int(np.isfinite(both["d_eco"]).sum()),
               "eco_change_class": {k: int(v) for k, v in both["eco_change_class"].value_counts().items()},
               "ecoregions_scored_b": int(eco_tab.loc[eco_tab["peer_cls"] != "all", "eco_id"].nunique()),
               "agreement": agreement, "cell_rows": int(len(cell_tab)), "seconds": round(time.time() - t0)}
    with open(os.path.join(OUT, "score_summary.json"), "w") as fh:
        json.dump(summary, fh, indent=1)
    log(step="score", done=True, seconds=round(time.time() - t0))


def names_table():
    import geopandas as gpd
    g = gpd.read_file(os.path.join(OUT, "ecoregions_brazil.gpkg"))
    return g[["ECO_ID", "ECO_NAME", "BIOME_NUM", "BIOME_NAME"]].drop_duplicates("ECO_ID").rename(
        columns={"ECO_ID": "eco_id", "ECO_NAME": "eco_name", "BIOME_NUM": "biome_num", "BIOME_NAME": "biome_name"})


def shares(frame, col, classes, prefix):
    """Shares of each class in col over the rows of frame, per group index already applied."""
    cnt = pd.crosstab(frame["key"], frame[col].astype(str)).reindex(columns=classes, fill_value=0)
    tot = cnt.sum(axis=1)
    out = cnt.div(tot.replace(0, np.nan), axis=0)
    out.columns = [f"{prefix}{c}" for c in classes]
    out[f"{prefix}n"] = tot
    return out


def build_ecoregion_table(both, per_year):
    names = names_table()
    g20 = per_year[2020][3].rename(columns={"eco_med": "median_adj_2020", "n": "n_fields_2020", "scale_c": "scale_c_2020"})
    g24 = per_year[2024][3].rename(columns={"eco_med": "median_adj_2024", "n": "n_fields_2024", "scale_c": "scale_c_2024"})
    tab = g20[["eco_id", "cls", "n_fields_2020", "median_adj_2020", "scale_c_2020"]].merge(
        g24[["eco_id", "cls", "n_fields_2024", "median_adj_2024", "scale_c_2024"]], on=["eco_id", "cls"], how="outer")
    tab["scale_c_change"] = tab["scale_c_2024"] - tab["scale_c_2020"]
    # plain change over fields valid in both years with the same class
    ok = both["valid_2020"].values & both["valid_2024"].values & (both["cls_2020"].values == both["cls_2024"].values) \
        & (both["eco_id"].values > 0) & np.isfinite(both["m_2020"].values) & np.isfinite(both["m_2024"].values)
    p = pd.DataFrame({"eco_id": both["eco_id"].values[ok], "cls": both["cls_2024"].values[ok],
                      "d": both["m_2024"].values[ok] - both["m_2020"].values[ok], "m20": both["m_2020"].values[ok]})
    plain = p.groupby(["eco_id", "cls"]).agg(n_both=("d", "size"), median_diff=("d", "median"), median_2020_both=("m20", "median")).reset_index()
    with np.errstate(all="ignore"):
        plain["plain_change_pct"] = 100 * plain["median_diff"] / plain["median_2020_both"]
    plain.loc[plain["n_both"] < MIN_GROUP, "plain_change_pct"] = np.nan
    tab = tab.merge(plain[["eco_id", "cls", "n_both", "plain_change_pct"]], on=["eco_id", "cls"], how="left")
    # Scale B and Scale A class shares over the fields with a Scale B change value
    hb = np.isfinite(both["d_eco"].values)
    fb = pd.DataFrame({"key": both["eco_id"].values[hb].astype(str) + "|" + both["cls_2024"].values[hb].astype(str),
                       "b": both["eco_change_class"].values[hb], "a": both["change_class_a"].values[hb]})
    sh = shares(fb, "b", CLASSES5, "share_b_").join(shares(fb, "a", CLASSES5 + ["no_data"], "share_a_")).reset_index()
    sh["eco_id"] = sh["key"].str.split("|").str[0].astype(int)
    sh["cls"] = sh["key"].str.split("|").str[1].astype(int)
    tab = tab.merge(sh.drop(columns="key"), on=["eco_id", "cls"], how="left")
    tab["share_b_decline_any"] = tab["share_b_large_decline"] + tab["share_b_decline"]
    tab["share_a_decline_any"] = tab["share_a_large_decline"] + tab["share_a_decline"]
    tab["peer_cls"] = tab["cls"].astype(int).astype(str)
    tab["crop_group"] = tab["cls"].map(C.CROP_GROUP)
    # class-weighted row per ecoregion, weights n_both
    rows = []
    for eid, sub in tab.groupby("eco_id"):
        w = sub["n_both"].fillna(0).values.astype(float)
        def wmean(col):
            v = sub[col].values.astype(float)
            m = np.isfinite(v) & (w > 0)
            return float(np.sum(v[m] * w[m]) / np.sum(w[m])) if m.any() else np.nan
        rec = {"eco_id": eid, "cls": -1, "peer_cls": "all", "crop_group": "all",
               "n_fields_2020": int(sub["n_fields_2020"].fillna(0).sum()), "n_fields_2024": int(sub["n_fields_2024"].fillna(0).sum()),
               "n_both": int(np.nansum(w)), "median_adj_2020": np.nan, "median_adj_2024": np.nan,
               "scale_c_2020": wmean("scale_c_2020"), "scale_c_2024": wmean("scale_c_2024"), "scale_c_change": wmean("scale_c_change"),
               "plain_change_pct": wmean("plain_change_pct")}
        nb = sub["share_b_n"].fillna(0).values
        for c in CLASSES5:
            rec[f"share_b_{c}"] = float(np.nansum(sub[f"share_b_{c}"].values * nb) / nb.sum()) if nb.sum() else np.nan
        rec["share_b_n"] = int(nb.sum())
        na = sub["share_a_n"].fillna(0).values
        for c in CLASSES5 + ["no_data"]:
            rec[f"share_a_{c}"] = float(np.nansum(sub[f"share_a_{c}"].values * na) / na.sum()) if na.sum() else np.nan
        rec["share_a_n"] = int(na.sum())
        rec["share_b_decline_any"] = rec["share_b_large_decline"] + rec["share_b_decline"]
        rec["share_a_decline_any"] = rec["share_a_large_decline"] + rec["share_a_decline"]
        rows.append(rec)
    tab = pd.concat([tab, pd.DataFrame(rows)], ignore_index=True)
    tab = tab.merge(names, on="eco_id", how="left")
    cols = ["eco_id", "eco_name", "biome_num", "biome_name", "peer_cls", "crop_group", "n_fields_2020", "n_fields_2024", "n_both",
            "median_adj_2020", "median_adj_2024", "scale_c_2020", "scale_c_2024", "scale_c_change", "plain_change_pct",
            "share_b_n"] + [f"share_b_{c}" for c in CLASSES5] + ["share_b_decline_any", "share_a_n"] + \
           [f"share_a_{c}" for c in CLASSES5 + ["no_data"]] + ["share_a_decline_any"]
    tab = tab[cols].copy()
    tab["_all"] = (tab["peer_cls"] == "all").astype(int)
    tab = tab.sort_values(["eco_name", "_all", "peer_cls"]).drop(columns="_all")
    return tab.reset_index(drop=True)


def build_biome_table(both, per_year, eco_tab):
    """Same quantities with the biome as the reference region: biome-class medians against the nation."""
    names = names_table()
    eco_to_biome = dict(zip(names["eco_id"], names["biome_name"]))
    biome = both["eco_id"].map(eco_to_biome)
    rows = []
    for ay in AYS:
        nat = per_year[ay][4]
        valid = both[f"valid_{ay}"].values & (both["eco_id"].values > 0) & np.isfinite(both[f"m_{ay}"].values)
        f = pd.DataFrame({"biome": biome.values[valid], "cls": both[f"cls_{ay}"].values[valid], "m": both[f"m_{ay}"].values[valid]})
        g = f.groupby(["biome", "cls"]).agg(n=("m", "size"), med=("m", "median")).reset_index()
        g = g.merge(nat[["cls", "nat_med", "cell_sd"]], on="cls", how="left")
        with np.errstate(all="ignore"):
            g["scale_c"] = (g["med"] - g["nat_med"]) / g["cell_sd"]
        g.loc[g["n"] < MIN_GROUP, ["med", "scale_c"]] = np.nan
        g = g.rename(columns={"n": f"n_fields_{ay}", "med": f"median_adj_{ay}", "scale_c": f"scale_c_{ay}"})
        rows.append(g[["biome", "cls", f"n_fields_{ay}", f"median_adj_{ay}", f"scale_c_{ay}"]])
    tab = rows[0].merge(rows[1], on=["biome", "cls"], how="outer")
    tab["scale_c_change"] = tab["scale_c_2024"] - tab["scale_c_2020"]
    ok = both["valid_2020"].values & both["valid_2024"].values & (both["cls_2020"].values == both["cls_2024"].values) \
        & (both["eco_id"].values > 0) & np.isfinite(both["m_2020"].values) & np.isfinite(both["m_2024"].values)
    p = pd.DataFrame({"biome": biome.values[ok], "cls": both["cls_2024"].values[ok],
                      "d": both["m_2024"].values[ok] - both["m_2020"].values[ok], "m20": both["m_2020"].values[ok]})
    plain = p.groupby(["biome", "cls"]).agg(n_both=("d", "size"), md=("d", "median"), m20=("m20", "median")).reset_index()
    with np.errstate(all="ignore"):
        plain["plain_change_pct"] = 100 * plain["md"] / plain["m20"]
    tab = tab.merge(plain[["biome", "cls", "n_both", "plain_change_pct"]], on=["biome", "cls"], how="left")
    hb = np.isfinite(both["d_eco"].values)
    fb = pd.DataFrame({"key": biome.values[hb].astype(str) + "|" + both["cls_2024"].values[hb].astype(str),
                       "b": both["eco_change_class"].values[hb], "a": both["change_class_a"].values[hb]})
    sh = shares(fb, "b", CLASSES5, "share_b_").join(shares(fb, "a", CLASSES5 + ["no_data"], "share_a_"))
    sh = sh.reset_index()
    sh["biome"] = sh["key"].str.split("|").str[0]
    sh["cls"] = sh["key"].str.split("|").str[1].astype(int)
    tab = tab.merge(sh.drop(columns="key"), on=["biome", "cls"], how="left")
    tab["share_b_decline_any"] = tab["share_b_large_decline"] + tab["share_b_decline"]
    tab["share_a_decline_any"] = tab["share_a_large_decline"] + tab["share_a_decline"]
    tab["peer_cls"] = tab["cls"].astype(int).astype(str)
    tab["crop_group"] = tab["cls"].map(C.CROP_GROUP)
    rows = []
    for b, sub in tab.groupby("biome"):
        w = sub["n_both"].fillna(0).values.astype(float)
        def wmean(col):
            v = sub[col].values.astype(float)
            m = np.isfinite(v) & (w > 0)
            return float(np.sum(v[m] * w[m]) / np.sum(w[m])) if m.any() else np.nan
        rec = {"biome": b, "peer_cls": "all", "crop_group": "all", "n_fields_2020": int(sub["n_fields_2020"].fillna(0).sum()),
               "n_fields_2024": int(sub["n_fields_2024"].fillna(0).sum()), "n_both": int(w.sum()),
               "scale_c_2020": wmean("scale_c_2020"), "scale_c_2024": wmean("scale_c_2024"), "scale_c_change": wmean("scale_c_change"),
               "plain_change_pct": wmean("plain_change_pct")}
        nb = sub["share_b_n"].fillna(0).values
        for c in CLASSES5:
            rec[f"share_b_{c}"] = float(np.nansum(sub[f"share_b_{c}"].values * nb) / nb.sum()) if nb.sum() else np.nan
        na = sub["share_a_n"].fillna(0).values
        for c in CLASSES5 + ["no_data"]:
            rec[f"share_a_{c}"] = float(np.nansum(sub[f"share_a_{c}"].values * na) / na.sum()) if na.sum() else np.nan
        rec["share_b_n"], rec["share_a_n"] = int(nb.sum()), int(na.sum())
        rec["share_b_decline_any"] = rec["share_b_large_decline"] + rec["share_b_decline"]
        rec["share_a_decline_any"] = rec["share_a_large_decline"] + rec["share_a_decline"]
        rows.append(rec)
    tab = pd.concat([tab, pd.DataFrame(rows)], ignore_index=True).rename(columns={"biome": "biome_name"})
    cols = ["biome_name", "peer_cls", "crop_group", "n_fields_2020", "n_fields_2024", "n_both", "median_adj_2020", "median_adj_2024",
            "scale_c_2020", "scale_c_2024", "scale_c_change", "plain_change_pct", "share_b_n"] + [f"share_b_{c}" for c in CLASSES5] + \
           ["share_b_decline_any", "share_a_n"] + [f"share_a_{c}" for c in CLASSES5 + ["no_data"]] + ["share_a_decline_any"]
    return tab[cols].sort_values(["biome_name", "peer_cls"]).reset_index(drop=True)


def build_cell_table(per_year):
    import h3
    c20 = per_year[2020][2].rename(columns={"n_cell": "n_2020", "cell_vs_eco": "cell_vs_eco_2020"})
    c24 = per_year[2024][2].rename(columns={"n_cell": "n_2024", "cell_vs_eco": "cell_vs_eco_2024"})
    tab = c20[["h3_5", "eco_id", "cls", "n_2020", "cell_vs_eco_2020"]].merge(
        c24[["h3_5", "eco_id", "cls", "n_2024", "cell_vs_eco_2024"]], on=["h3_5", "eco_id", "cls"], how="outer")
    tab = tab[tab["cell_vs_eco_2020"].notna() | tab["cell_vs_eco_2024"].notna()].copy()
    tab["change"] = tab["cell_vs_eco_2024"] - tab["cell_vs_eco_2020"]
    tab["n_2020"] = tab["n_2020"].fillna(0).astype(int)
    tab["n_2024"] = tab["n_2024"].fillna(0).astype(int)
    tab["h3_5"] = [h3.int_to_str(int(v)) for v in tab["h3_5"].values]
    tab = tab.rename(columns={"cls": "peer_cls"})
    return tab[["h3_5", "eco_id", "peer_cls", "n_2020", "n_2024", "cell_vs_eco_2020", "cell_vs_eco_2024", "change"]] \
        .sort_values(["eco_id", "peer_cls", "h3_5"]).reset_index(drop=True)


# ----------------------------------------------------------------------------------------------
# figures
# ----------------------------------------------------------------------------------------------

def brazil_outline():
    import geopandas as gpd
    b = gpd.read_file(BIOMES_BR).to_crs(4326)
    return b.geometry.union_all()


def figures():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    import geopandas as gpd
    import h3
    from shapely.geometry import Polygon
    os.makedirs(FIG_DIR, exist_ok=True)
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    W, DPI = 16, 100  # 1600 px wide
    cmap = plt.get_cmap("RdBu")  # ColorBrewer diverging, red decline, blue gain, near-white middle
    br = brazil_outline()
    eco = gpd.read_file(os.path.join(OUT, "ecoregions_brazil.gpkg"))
    eco["geometry"] = eco.geometry.intersection(br)
    eco = eco[~eco.geometry.is_empty]
    tab = pd.read_csv(os.path.join(C.SUMMARIES, "ecoregions.csv"))
    allrows = tab[tab["peer_cls"] == "all"].set_index("eco_id")
    eco = eco.merge(allrows[["scale_c_change", "plain_change_pct", "n_both", "share_a_decline_any", "share_b_decline_any", "eco_name"]],
                    left_on="ECO_ID", right_index=True, how="left")
    eco_plot = eco[eco["n_both"].fillna(0) >= 1000]

    def eco_map(col, vlim, label, fname, fmt):
        fig, ax = plt.subplots(figsize=(W, W * 0.95), dpi=DPI)
        eco.plot(ax=ax, color="#e8e8e6", edgecolor="white", linewidth=0.3)
        norm = TwoSlopeNorm(vmin=-vlim, vcenter=0, vmax=vlim)
        eco_plot.plot(ax=ax, column=col, cmap=cmap, norm=norm, edgecolor="#555555", linewidth=0.4, legend=False)
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        cb = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.01, shrink=0.6)
        cb.set_label(label)
        for _, r in eco_plot.iterrows():
            if r["n_both"] >= 40000:
                c = r.geometry.representative_point()
                ax.annotate(f"{r['eco_name']}\n{fmt(r[col])}", (c.x, c.y), ha="center", va="center", fontsize=7.5, color="#222222")
        ax.set_axis_off()
        ax.set_title("", loc="left")
        fig.text(0.01, 0.01, "gray: ecoregions with under 1,000 fields valid in both years; ecoregion polygons clipped to the IBGE biome outline",
                 fontsize=9, color="#555555")
        fig.savefig(os.path.join(FIG_DIR, fname), bbox_inches="tight", facecolor="white")
        plt.close(fig)

    eco_map("scale_c_change", 1.0, "change in Scale C score, 2024 minus 2020 (national cell SD units, class weighted)",
            "fig1_scale_c_change.png", lambda v: f"{v:+.2f} SD")
    eco_map("plain_change_pct", 20.0, "weather-adjusted seasonal NDVI integral, median field change 2020 to 2024 (percent, class weighted)",
            "fig2_plain_change_pct.png", lambda v: f"{v:+.1f}%")

    # figure 3: H3 resolution 5 cells colored by the change in cell_vs_eco (class weighted by n)
    ct = pd.read_csv(os.path.join(C.SUMMARIES, "cell_vs_ecoregion.csv"))
    ct = ct[ct["change"].notna()]
    ct["w"] = np.minimum(ct["n_2020"], ct["n_2024"])
    ct["wc"] = ct["change"] * ct["w"]
    agg = ct.groupby("h3_5").agg(wc=("wc", "sum"), n=("w", "sum")).reset_index()
    agg = agg[agg["n"] > 0]
    agg["change"] = agg["wc"] / agg["n"]
    polys = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in agg["h3_5"]]
    cells = gpd.GeoDataFrame(agg, geometry=polys, crs=4326)
    fig, ax = plt.subplots(figsize=(W, W * 0.95), dpi=DPI)
    gpd.GeoSeries([br], crs=4326).plot(ax=ax, color="#f2f2f0", edgecolor="none")
    norm = TwoSlopeNorm(vmin=-1.0, vcenter=0, vmax=1.0)
    cells.plot(ax=ax, column="change", cmap=cmap, norm=norm, edgecolor="none")
    eco.boundary.plot(ax=ax, color="#333333", linewidth=0.5)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    cb = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.01, shrink=0.6)
    cb.set_label("change in the cell median against its ecoregion, 2024 minus 2020 (ecoregion SD units)")
    ax.set_axis_off()
    fig.text(0.01, 0.01, f"{len(cells):,} H3 resolution 5 cells with at least 30 valid fields of a class in both years; black lines are RESOLVE 2017 ecoregions",
             fontsize=9, color="#555555")
    fig.savefig(os.path.join(FIG_DIR, "fig3_cell_vs_eco_change.png"), bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # figure 4: share declining under Scale A against Scale B per ecoregion
    d = allrows[allrows["n_both"] >= 1000].copy()
    fig, ax = plt.subplots(figsize=(W, W * 0.6), dpi=DPI)
    lim = max(d["share_a_decline_any"].max(), d["share_b_decline_any"].max()) * 100 + 2
    ax.plot([0, lim], [0, lim], color="#999999", linewidth=1, linestyle="--")
    ax.scatter(d["share_a_decline_any"] * 100, d["share_b_decline_any"] * 100, s=np.sqrt(d["n_both"]) / 4, color="#2166ac", alpha=0.6, edgecolor="white")
    for eid, r in d.iterrows():
        if r["eco_name"] in FRONTIER or r["n_both"] > 500000:
            ax.annotate(r["eco_name"], (r["share_a_decline_any"] * 100, r["share_b_decline_any"] * 100), fontsize=8, xytext=(4, 2), textcoords="offset points")
    ax.set_xlabel("share of fields declining under Scale A, cell peers (percent)")
    ax.set_ylabel("share of fields declining under Scale B, ecoregion peers (percent)")
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.grid(color="#eeeeee")
    fig.text(0.01, 0.01, "one point per ecoregion with at least 1,000 fields valid in both years; area scales with field count; declining is decline plus large decline",
             fontsize=9, color="#555555")
    fig.savefig(os.path.join(FIG_DIR, "fig4_share_declining_a_vs_b.png"), bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # figure 5: agreement matrix
    am = pd.read_csv(os.path.join(OUT, "agreement_matrix.csv"), index_col=0).reindex(index=CLASSES5, columns=CLASSES5)
    row_share = am.div(am.sum(axis=1), axis=0)
    fig, ax = plt.subplots(figsize=(W * 0.6, W * 0.5), dpi=DPI)
    im = ax.imshow(row_share.values, cmap="Blues", vmin=0, vmax=1)
    labels = [c.replace("_", " ") for c in CLASSES5]
    ax.set_xticks(range(5), labels, rotation=20)
    ax.set_yticks(range(5), labels)
    ax.set_xlabel("Scale B class (ecoregion peers)")
    ax.set_ylabel("Scale A class (cell peers)")
    for i in range(5):
        for j in range(5):
            v = row_share.values[i, j]
            ax.text(j, i, f"{v * 100:.1f}%\n{am.values[i, j]:,}", ha="center", va="center", fontsize=9, color="white" if v > 0.5 else "#222222")
    fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02, label="share of the Scale A row")
    ax.spines[:].set_visible(False)
    fig.savefig(os.path.join(FIG_DIR, "fig5_agreement_matrix.png"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    for f in sorted(os.listdir(FIG_DIR)):
        log(step="figures", file=f, bytes=os.path.getsize(os.path.join(FIG_DIR, f)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["assign", "score", "figures", "all"])
    ap.add_argument("--states", nargs="*", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--verify-state", default="Acre")
    args = ap.parse_args()
    states = args.states or C.state_dirs(POLYS)
    os.makedirs(OUT, exist_ok=True)
    if args.step in ("assign", "all"):
        assign(states, force=args.force)
    if args.step in ("score", "all"):
        score(states, verify_state=args.verify_state, force=args.force)
    if args.step in ("figures", "all"):
        figures()


if __name__ == "__main__":
    main()
