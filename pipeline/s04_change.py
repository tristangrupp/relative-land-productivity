"""Stage 4c: change classes and decisions per field (METHODS.md sections 6 and 7).

  python s04_change.py --source modis [--states ...] [--workers 3] [--allow-missing-2020]

Per state, on the 2024 polygons, joins the prepared fields (geometry, area, municipality),
the MapBiomas classes (s03f), the two relative tables of s04_relative.py (agricultural
years 2020 and 2024 on the 2024 polygons) and the metrics tables, and writes the attributes
the site reads (docs/config.js ATTR, docs/DATA_CONTRACT.md):

  fid, area_ha, crop_2020 (MapBiomas 2020 modal class inside the 2024 outline), crop_2024
  (the Trazo4 modal class `mbmode`, the class the 2024 peers were formed on), prod_2020,
  prod_2024 (weather-adjusted relative productivity, 1.0 at the peer median), change
  (prod_2024 - prod_2020 when both exist and the crop group is the same), change_class,
  vigor_2020, vigor_2024 (null, no vigor raster), decision, n_obs_2020, n_obs_2024 (valid
  composites inside the window), muni_code, plus confidence (high or low).

change_class, in order of precedence:
  newly_cropped   the 2020 class is not agricultural
  crop_switched   the 2020 and 2024 crop groups differ (19 and 41 are one group)
  no_data         either year has no relative value (under half the window observed, or no
                  peer group of 30 fields up to H3 resolution 3)
  large_decline, decline, stable, gain, large_gain   from D = r_adj_2024 - r_adj_2020, the
                  change in peer standard deviations, at -2, -1, 1 and 2

decision, from the 2024 level (r_adj_2024 below -0.5, between, above 0.5) and the trend:
  below+decline restore; below+stable switch_crop; below+gain improve_yields;
  at+decline improve_yields; at+stable intensify; at+gain intensify;
  above+decline improve_yields; above+stable keep; above+gain keep;
  abandon when below in both years, declining, and the 2024 integral is under the 20th
  percentile of the class in the state; change_pattern for crop_switched; none for
  newly_cropped and no_data (METHODS.md gives no suggestion there); restore for abandoned.

confidence is low when the field is under 6.25 ha (one MODIS pixel) or fewer than 75 percent
of the window composites were observed in either year.

Abandoned layer: 2020 polygons whose MapBiomas 2024 class is not agricultural, with the 2020
relative value from the 2020 polygons, change_class abandoned and decision restore. The
METHODS.md overlay rule (no 2024 field covering half the 2020 field) is not applied; only the
class rule is.

Outputs, GeoParquet with the geometry and bbox columns and the `geo` metadata copied from the
prepared fields:
  analysis\\year=2024\\state=<State>\\fields_scored.parquet
  analysis\\abandoned\\state=<State>.parquet
and a per-state count file analysis\\year=2024\\state=<State>\\counts.json.
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s04_common as C  # noqa: E402

LEVEL_SD = 0.5
ABANDON_PCTL = 20
CONF_SHARE = 0.75
CHANGE_CLASSES = ["large_decline", "decline", "stable", "gain", "large_gain", "crop_switched", "newly_cropped", "no_data", "abandoned"]
DECISIONS = ["restore", "switch_crop", "change_pattern", "abandon", "intensify", "improve_yields", "keep", "none"]
DECISION_TABLE = {("below", "decline"): "restore", ("below", "stable"): "switch_crop", ("below", "gain"): "improve_yields",
                  ("at", "decline"): "improve_yields", ("at", "stable"): "intensify", ("at", "gain"): "intensify",
                  ("above", "decline"): "improve_yields", ("above", "stable"): "keep", ("above", "gain"): "keep"}


def read(path, cols, index="fid"):
    return pq.read_table(path, columns=cols).to_pandas().set_index(index)


def geo_metadata(path):
    md = pq.ParquetFile(path).schema_arrow.metadata or {}
    return md.get(b"geo")


def change_class(D):
    out = np.full(len(D), "no_data", dtype=object)
    ok = np.isfinite(D)
    out[ok & (D < -2)] = "large_decline"
    out[ok & (D >= -2) & (D < -1)] = "decline"
    out[ok & (D >= -1) & (D <= 1)] = "stable"
    out[ok & (D > 1) & (D <= 2)] = "gain"
    out[ok & (D > 2)] = "large_gain"
    return out


def decide(cc, r20, r24, integral24, cls24, uf_pctl):
    n = len(cc)
    trend = np.where(np.isin(cc, ["large_decline", "decline"]), "decline",
                     np.where(np.isin(cc, ["gain", "large_gain"]), "gain", "stable"))
    level = np.where(r24 < -LEVEL_SD, "below", np.where(r24 > LEVEL_SD, "above", "at"))
    dec = np.full(n, "none", dtype=object)
    comparable = np.isin(cc, ["large_decline", "decline", "stable", "gain", "large_gain"])
    for (lv, tr), d in DECISION_TABLE.items():
        dec[comparable & (level == lv) & (trend == tr)] = d
    p20 = np.array([uf_pctl.get(int(c), np.nan) for c in cls24])
    abandon = comparable & (trend == "decline") & (r20 < -LEVEL_SD) & (r24 < -LEVEL_SD) & (integral24 < p20)
    dec[abandon] = "abandon"
    dec[cc == "crop_switched"] = "change_pattern"
    return dec


def write_geo(df, path, geo_meta, extra_meta):
    table = pa.Table.from_pandas(df, preserve_index=False)
    meta = {k: v for k, v in (table.schema.metadata or {}).items() if k != b"pandas"}
    if geo_meta:
        meta[b"geo"] = geo_meta
    meta[b"s04_change"] = json.dumps(extra_meta).encode()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pq.write_table(table.replace_schema_metadata(meta), path + ".part", compression="zstd", row_group_size=100_000)
    os.replace(path + ".part", path)


def score_state(source, state, allow_missing_2020=False, force=False):
    t0 = time.time()
    out_path = os.path.join(C.ANALYSIS, "year=2024", f"state={state}", "fields_scored.parquet")
    ab_path = os.path.join(C.ANALYSIS, "abandoned", f"state={state}.parquet")
    if os.path.exists(out_path) and os.path.exists(ab_path) and not force:
        return {"state": state, "status": "exists"}
    fp = C.fields_path(2024, state)
    rel24 = C.relative_path(source, 2024, 2024, state)
    rel20 = C.relative_path(source, 2024, 2020, state)
    met24 = C.metrics_path(source, 2024, 2024, state)
    met20 = C.metrics_path(source, 2024, 2020, state)
    for p in (rel24, met24, C.classes_path(2024, state)):
        if not os.path.exists(p):
            return {"state": state, "status": "waiting", "note": p}
    has20 = os.path.exists(rel20) and os.path.exists(met20)
    if not has20 and not allow_missing_2020:
        return {"state": state, "status": "waiting", "note": rel20}

    f = pq.read_table(fp, columns=["fid", "area_ha", "mbmode", "muni_code", "bbox", "geometry"]).to_pandas()
    cl = read(C.classes_path(2024, state), ["fid", "mb_2020", "mb_2024", "ag_2020", "vigor_2020", "vigor_2024"])
    r24 = read(rel24, ["fid", "prod", "r_adj", "valid"]).add_suffix("_2024")
    m24 = read(met24, ["fid", "n_window", "n_valid_window", "small_field", "integral", "cls"]).add_suffix("_2024")
    df = f.join(cl, on="fid").join(r24, on="fid").join(m24, on="fid")
    if has20:
        r20 = read(rel20, ["fid", "prod", "r_adj", "valid"]).add_suffix("_2020")
        m20 = read(met20, ["fid", "n_window", "n_valid_window"]).add_suffix("_2020")
        df = df.join(r20, on="fid").join(m20, on="fid")
    else:
        for c in ("prod_2020", "r_adj_2020"):
            df[c] = np.float32(np.nan)
        df["valid_2020"] = False
        df["n_window_2020"] = np.int8(0)
        df["n_valid_window_2020"] = np.int8(0)
    n = len(df)
    mb20 = df["mb_2020"].fillna(-1).values.astype(np.int16)
    mb24 = df["mbmode"].values.astype(np.int16)
    ag20 = np.isin(mb20, C.AG_CLASSES)
    grp20 = np.array([C.CROP_GROUP.get(int(c), "none") for c in mb20], dtype=object)
    grp24 = np.array([C.CROP_GROUP.get(int(c), "none") for c in mb24], dtype=object)
    prod20 = df["prod_2020"].values.astype(np.float32)
    prod24 = df["prod_2024"].values.astype(np.float32)
    radj20 = df["r_adj_2020"].values.astype(np.float32)
    radj24 = df["r_adj_2024"].values.astype(np.float32)
    with np.errstate(invalid="ignore"):
        D = radj24 - radj20
    cc = change_class(D)
    cc[~ag20] = "newly_cropped"
    cc[ag20 & (grp20 != grp24)] = "crop_switched"
    same = ag20 & (grp20 == grp24)
    with np.errstate(invalid="ignore"):
        change = np.where(same & np.isfinite(prod20) & np.isfinite(prod24), prod24 - prod20, np.nan).astype(np.float32)
    # 20th percentile of the 2024 integral per class in the state, over valid fields
    integ = df["integral_2024"].values
    pctl = {}
    for c in np.unique(mb24):
        sel = (mb24 == c) & (df["valid_2024"].values == True) & np.isfinite(integ)  # noqa: E712
        if sel.sum() >= 30:
            pctl[int(c)] = float(np.percentile(integ[sel], ABANDON_PCTL))
    dec = decide(cc, radj20, radj24, integ, mb24, pctl)
    nw24 = df["n_window_2024"].values.astype(np.float32)
    nv24 = df["n_valid_window_2024"].values.astype(np.float32)
    nw20 = df["n_window_2020"].values.astype(np.float32)
    nv20 = df["n_valid_window_2020"].values.astype(np.float32)
    low = df["small_field_2024"].values.astype(bool) | (nv24 < CONF_SHARE * nw24)
    low |= np.where(nw20 > 0, nv20 < CONF_SHARE * nw20, False)
    out = pd.DataFrame({
        "fid": df["fid"].values.astype(np.int64),
        "area_ha": np.round(df["area_ha"].values, 2).astype(np.float32),
        "crop_2020": pd.array(np.where(mb20 >= 0, mb20, 0), dtype="Int16"),
        "crop_2024": mb24,
        "prod_2020": np.round(prod20, 3),
        "prod_2024": np.round(prod24, 3),
        "change": np.round(change, 3),
        "change_class": pd.Categorical(cc, categories=CHANGE_CLASSES),
        "vigor_2020": pd.array(df["vigor_2020"].values, dtype="Int16"),
        "vigor_2024": pd.array(df["vigor_2024"].values, dtype="Int16"),
        "decision": pd.Categorical(dec, categories=DECISIONS),
        "n_obs_2020": df["n_valid_window_2020"].fillna(0).values.astype(np.int8),
        "n_obs_2024": df["n_valid_window_2024"].fillna(0).values.astype(np.int8),
        "muni_code": C.muni_to_int(df["muni_code"]),
        "confidence": pd.Categorical(np.where(low, "low", "high"), categories=["high", "low"]),
        "r_adj_2020": radj20,
        "r_adj_2024": radj24,
        "bbox": df["bbox"].values,
        "geometry": df["geometry"].values,
    })
    out.loc[mb20 < 0, "crop_2020"] = pd.NA
    write_geo(out, out_path, geo_metadata(fp), {"state": state, "source": source, "has_2020": has20,
                                                 "written": datetime.now().isoformat(timespec="seconds")})

    # abandoned layer from the 2020 polygons
    fp20 = C.fields_path(2020, state)
    cl20 = C.classes_path(2020, state)
    ab_rows = 0
    if os.path.exists(cl20):
        c20 = read(cl20, ["fid", "mb_2024", "ag_2024"])
        keep = c20.index[c20["ag_2024"].values == False]  # noqa: E712
        f20 = pq.read_table(fp20, columns=["fid", "area_ha", "mbmode", "muni_code", "bbox", "geometry"],
                            filters=[("fid", "in", pa.array(keep.values))]).to_pandas()
        f20 = f20.join(c20, on="fid")
        rp = C.relative_path(source, 2020, 2020, state)
        mp = C.metrics_path(source, 2020, 2020, state)
        if os.path.exists(rp) and os.path.exists(mp):
            f20 = f20.join(read(rp, ["fid", "prod", "r_adj"]), on="fid")
            f20 = f20.join(read(mp, ["fid", "n_window", "n_valid_window", "small_field"]), on="fid")
        else:
            f20["prod"] = np.float32(np.nan)
            f20["r_adj"] = np.float32(np.nan)
            f20["n_window"] = np.int8(0)
            f20["n_valid_window"] = np.int8(0)
            f20["small_field"] = f20["area_ha"].values < 6.25
        nw = f20["n_window"].fillna(0).values.astype(np.float32)
        nv = f20["n_valid_window"].fillna(0).values.astype(np.float32)
        low = f20["small_field"].fillna(True).values.astype(bool) | (nv < CONF_SHARE * nw)
        ab = pd.DataFrame({
            "fid": f20["fid"].values.astype(np.int64),
            "area_ha": np.round(f20["area_ha"].values, 2).astype(np.float32),
            "crop_2020": f20["mbmode"].values.astype(np.int16),
            "crop_2024": pd.array(f20["mb_2024"].values, dtype="Int16"),
            "prod_2020": np.round(f20["prod"].values.astype(np.float32), 3),
            "prod_2024": np.float32(np.nan),
            "change": np.float32(np.nan),
            "change_class": pd.Categorical(["abandoned"] * len(f20), categories=CHANGE_CLASSES),
            "vigor_2020": pd.array([pd.NA] * len(f20), dtype="Int16"),
            "vigor_2024": pd.array([pd.NA] * len(f20), dtype="Int16"),
            "decision": pd.Categorical(["restore"] * len(f20), categories=DECISIONS),
            "n_obs_2020": nv.astype(np.int8),
            "n_obs_2024": np.int8(0),
            "muni_code": C.muni_to_int(f20["muni_code"]),
            "confidence": pd.Categorical(np.where(low, "low", "high"), categories=["high", "low"]),
            "r_adj_2020": f20["r_adj"].values.astype(np.float32),
            "r_adj_2024": np.float32(np.nan),
            "bbox": f20["bbox"].values,
            "geometry": f20["geometry"].values,
        })
        write_geo(ab, ab_path, geo_metadata(fp20), {"state": state, "source": source, "layer": "abandoned",
                                                    "written": datetime.now().isoformat(timespec="seconds")})
        ab_rows = len(ab)
    counts = {"state": state, "n_fields": int(n), "area_ha": float(df["area_ha"].sum()),
              "change_class": {k: int(v) for k, v in pd.Series(cc).value_counts().items()},
              "decision": {k: int(v) for k, v in pd.Series(dec).value_counts().items()},
              "confidence_low": int(low.sum()) if False else int((out["confidence"] == "low").sum()),
              "crop_2020": {str(int(k)): int(v) for k, v in pd.Series(mb20[mb20 >= 0]).value_counts().items()},
              "crop_2024": {str(int(k)): int(v) for k, v in pd.Series(mb24).value_counts().items()},
              "abandoned": ab_rows, "has_2020": has20, "seconds": round(time.time() - t0, 1)}
    with open(os.path.join(os.path.dirname(out_path), "counts.json"), "w") as fh:
        json.dump(counts, fh, indent=1)
    return {"state": state, "status": "ok", "rows": int(n), "abandoned": ab_rows, "has_2020": has20,
            "no_data": counts["change_class"].get("no_data", 0), "low_confidence": counts["confidence_low"],
            "seconds": counts["seconds"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["modis", "s2"], default="modis")
    ap.add_argument("--states", nargs="*", default=None)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--allow-missing-2020", action="store_true", help="score with the 2024 year only (development)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    states = args.states or C.state_dirs(2024)
    sizes = {s: os.path.getsize(C.fields_path(2024, s)) for s in states}
    states = sorted(states, key=lambda s: -sizes[s])
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(score_state, args.source, s, args.allow_missing_2020, args.force): s for s in states}
        for f in as_completed(futs):
            try:
                r = f.result()
            except Exception as e:  # noqa: BLE001
                r = {"state": futs[f], "status": "fail", "error": repr(e)[:400]}
            print(json.dumps(r), flush=True)
    print(f"done in {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
