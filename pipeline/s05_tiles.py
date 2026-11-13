"""Stage 5a: PMTiles and stats.json for the site (docs/DATA_CONTRACT.md).

  python s05_tiles.py geojson [--states ...] [--workers 3]   newline-delimited GeoJSON per state
  python s05_tiles.py fields  [--states ...] [--parallel 3]  tippecanoe per state, then tile-join
  python s05_tiles.py summary                                H3 resolution 6 cells, summary.pmtiles
  python s05_tiles.py stats                                  stats.json
  python s05_tiles.py all

fields.pmtiles, layer `fields`, zoom 9 to 13 (overzoomed beyond): every scored 2024 polygon (analysis\\year=2024)
plus the abandoned 2020 polygons (analysis\\abandoned), with the attributes of the contract
(fid, area_ha, crop_2020, crop_2024, prod_2020, prod_2024, change, change_class, vigor_2020,
vigor_2024, decision, n_obs_2020, n_obs_2024, muni_code) and confidence. Null attributes are
left out of the feature, which is what tippecanoe does anyway.

The GeoJSON is streamed per state: each 100,000-row group of the GeoParquet is decoded with
shapely (WKB to GeoJSON geometry strings) and written as one feature per line to
tiles\\geojson\\<State>.geojsonl, so no state is held in memory as GeoJSON.

Tippecanoe runs in WSL (Ubuntu-22.04, tippecanoe 2.80) twice per state with its temporary
files on F:. Zoom 12 to 14: `-pk -pf` (no tile size limit, no feature limit), so no field is
dropped or merged at the zooms where fields are the map. Zoom 9 to 11:
`--coalesce-densest-as-needed -pf`, which merges the densest neighboring polygons into one
feature (the first feature's attributes) where a tile would exceed 500 KB, instead of dropping
them. `--drop-densest-as-needed` is not used. `-ab` detects shared borders so neighboring
fields simplify to the same edge, `-P` reads the newline-delimited input in parallel. The
per-state PMTiles are joined with tile-join -pk into tiles\\fields.pmtiles. Sizes and times are
written to tiles\\tiles_log.jsonl.

summary.pmtiles, layer `summary`, zoom 3 to 9: one hexagon per H3 cell, resolution 3 at zoom 3,
4 at zooms 4 to 5, 5 at zooms 6 to 7 and 6 at zooms 8 to 9 (property `res`); resolution 6 is (about
36 km²) with the SUMMARY_ATTR means and counts over the scored 2024 fields whose centroid is
in the cell (h3_6 from the metrics tables); mean_vigor_change is null. share_no_data is added.

stats.json: n_fields, area_ha and counts per change_class, decision, crop_2020 and crop_2024
for Brazil and per state (two-letter codes). The abandoned 2020 polygons are counted in
change_class.abandoned and decision.restore but not in n_fields or the crop counts.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed, ThreadPoolExecutor
from datetime import datetime

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s04_common as C  # noqa: E402

GEOJSON = os.path.join(C.TILES, "geojson")
STATE_TILES = os.path.join(C.TILES, "states")
TMP = os.path.join(C.TILES, "tmp")
TMP_WSL = "/tmp/tippecanoe"
OUT_WSL = "/tmp/tippecanoe_out"


def wsl_out(out):
    """Run a tippecanoe or tile-join command with its output on the WSL disk, then copy to F:.

    Writing a PMTiles file through the /mnt/f 9P mount is two orders of magnitude slower than
    writing it on the WSL ext4 disk (tile-join: 735 s for 578 MB on /mnt/f, 7.5 s for 173 MB on
    /tmp). `out` is the Windows path; the command is given the WSL path returned here."""
    return f"{OUT_WSL}/{os.path.basename(out)}"


def wsl_run(cmd, out):
    """Run cmd (a WSL command list writing to wsl_out(out)), copy the result to out, remove the WSL copy."""
    subprocess.run(WSL + ["mkdir", "-p", TMP_WSL, OUT_WSL], capture_output=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    tmp = wsl_out(out)
    if r.returncode == 0:
        c = subprocess.run(WSL + ["cp", "-f", tmp, wsl_path(out)], capture_output=True, text=True)
        if c.returncode != 0:
            r.returncode = c.returncode
            r.stderr += c.stderr
    subprocess.run(WSL + ["rm", "-f", tmp], capture_output=True)
    if r.returncode != 0 and os.path.exists(out):
        os.remove(out)
    return r
SIMPLIFY_DEG = 0.0001
LOG = os.path.join(C.TILES, "tiles_log.jsonl")
ATTRS = ["fid", "area_ha", "crop_2020", "crop_2024", "prod_2020", "prod_2024", "change", "change_class",
         "vigor_2020", "vigor_2024", "decision", "n_obs_2020", "n_obs_2024", "muni_code", "confidence"]
INT_ATTRS = {"fid", "crop_2020", "crop_2024", "vigor_2020", "vigor_2024", "n_obs_2020", "n_obs_2024", "muni_code"}
WSL = ["wsl", "-d", "Ubuntu-22.04", "--"]


def wsl_path(p):
    p = os.path.abspath(p)
    return "/mnt/" + p[0].lower() + p[2:].replace("\\", "/")


def log(rec):
    rec["time"] = datetime.now().isoformat(timespec="seconds")
    os.makedirs(C.TILES, exist_ok=True)
    with open(LOG, "a") as fh:
        fh.write(json.dumps(rec) + "\n")


# ---------------------------------------------------------------- geojson

def props_lines(df):
    """One JSON object string per row with the non-null attributes, numbers already rounded."""
    cols = [c for c in ATTRS if c in df.columns]
    recs = df[cols].to_dict("records")
    out = []
    dumps = json.dumps
    for r in recs:
        d = {}
        for k, v in r.items():
            if v is None or v is pd.NA or (isinstance(v, float) and v != v):
                continue
            if k in INT_ATTRS:
                d[k] = int(v)
            elif isinstance(v, (float, np.floating)):
                d[k] = round(float(v), 3)
            else:
                d[k] = str(v)
        out.append(dumps(d, separators=(",", ":")))
    return out


def write_geojsonl(state, force=False):
    import shapely
    t0 = time.time()
    os.makedirs(GEOJSON, exist_ok=True)
    out = os.path.join(GEOJSON, f"{state}.geojsonl")
    if os.path.exists(out) and not force:
        return {"state": state, "status": "exists"}
    srcs = [os.path.join(C.ANALYSIS, "year=2024", f"state={state}", "fields_scored.parquet"),
            os.path.join(C.ANALYSIS, "abandoned", f"state={state}.parquet")]
    n = 0
    with open(out + ".part", "w", encoding="utf-8", newline="\n") as fh:
        for src in srcs:
            if not os.path.exists(src):
                continue
            pf = pq.ParquetFile(src)
            cols = [c for c in ATTRS if c in pf.schema_arrow.names] + ["geometry"]
            for rg in range(pf.metadata.num_row_groups):
                df = pf.read_row_group(rg, columns=cols).to_pandas()
                geoms = shapely.from_wkb(df["geometry"].values)
                geoms = shapely.simplify(geoms, SIMPLIFY_DEG, preserve_topology=True)
                geoms = shapely.transform(geoms, lambda c: np.round(c, 5))
                gj = shapely.to_geojson(geoms)
                props = props_lines(df.drop(columns=["geometry"]))
                keep = ~shapely.is_empty(geoms)
                lines = [f'{{"type":"Feature","properties":{p},"geometry":{g}}}\n' for p, g, k in zip(props, gj, keep) if k]
                fh.writelines(lines)
                n += len(lines)
    os.replace(out + ".part", out)
    rec = {"step": "geojson", "state": state, "features": n, "bytes": os.path.getsize(out), "seconds": round(time.time() - t0, 1)}
    log(rec)
    return rec


# ---------------------------------------------------------------- tippecanoe

def run_tippecanoe(state, force=False):
    t0 = time.time()
    os.makedirs(STATE_TILES, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    src = os.path.join(GEOJSON, f"{state}.geojsonl")
    hi = os.path.join(STATE_TILES, f"{state}_z12_14.pmtiles")
    lo = os.path.join(STATE_TILES, f"{state}_z9_11.pmtiles")
    recs = []
    for out, args in ((hi, ["-Z12", "-z13", "-pk", "-pf"]),
                      (lo, ["-Z9", "-z11", "--coalesce-smallest-as-needed", "--drop-smallest-as-needed", "-pf"])):
        if os.path.exists(out) and not force:
            recs.append({"state": state, "out": os.path.basename(out), "status": "exists"})
            continue
        t1 = time.time()
        cmd = WSL + ["tippecanoe", "-o", wsl_out(out), "-f", "-l", "fields", "-n", "fields", "-ab", "-P", "-q",
                     "-t", TMP_WSL] + args + [wsl_path(src)]
        r = wsl_run(cmd, out)
        rec = {"step": "tippecanoe", "state": state, "out": os.path.basename(out), "returncode": r.returncode,
               "bytes": os.path.getsize(out) if os.path.exists(out) else None, "seconds": round(time.time() - t1, 1),
               "stderr_tail": r.stderr[-600:]}
        log(rec)
        recs.append(rec)
        if r.returncode != 0:
            break
    return {"state": state, "seconds": round(time.time() - t0, 1), "runs": recs}


def tile_join(states):
    t0 = time.time()
    out = os.path.join(C.TILES, "fields.pmtiles")
    inputs = []
    for s in states:
        for suffix in ("_z12_14", "_z9_11"):
            p = os.path.join(STATE_TILES, f"{s}{suffix}.pmtiles")
            if os.path.exists(p):
                inputs.append(wsl_path(p))
    cmd = WSL + ["tile-join", "-o", wsl_out(out), "-f", "-pk", "-n", "fields",
                 "-N", "Relative land productivity, Brazil 2020 to 2024, Trazo4 fields"] + inputs
    r = wsl_run(cmd, out)
    rec = {"step": "tile-join", "inputs": len(inputs), "returncode": r.returncode,
           "bytes": os.path.getsize(out) if os.path.exists(out) else None, "seconds": round(time.time() - t0, 1),
           "stderr_tail": r.stderr[-600:]}
    log(rec)
    return rec


# ---------------------------------------------------------------- summary

def build_summary(states, source="modis"):
    import h3
    t0 = time.time()
    frames = []
    for s in states:
        p = os.path.join(C.ANALYSIS, "year=2024", f"state={s}", "fields_scored.parquet")
        m = C.metrics_path(source, 2024, 2024, s)
        if not (os.path.exists(p) and os.path.exists(m)):
            continue
        df = pq.read_table(p, columns=["fid", "area_ha", "crop_2020", "crop_2024", "prod_2020", "prod_2024", "change",
                                       "change_class", "decision"]).to_pandas()
        h6 = pq.read_table(m, columns=["fid", "h3_6"]).to_pandas().set_index("fid")
        df = df.join(h6, on="fid")
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    for c in ("area_ha", "prod_2020", "prod_2024", "change"):
        df[c] = df[c].astype("float64")
    df["change_class"] = df["change_class"].astype(str)
    df["decision"] = df["decision"].astype(str)
    # One summary level per zoom band, so the zoomed-out map shows regions rather than a
    # sub-pixel salt and pepper of resolution 6 cells (145k cells at zoom 4 are under one pixel
    # each). Each level aggregates the fields directly, not the finer cells, so a share is the
    # share of fields in that cell. The levels share one tile layer and never overlap in zoom.
    base = df["h3_6"].astype("int64")
    uniq = pd.Index(base.unique())
    recs = []
    pm_inputs = []
    os.makedirs(GEOJSON, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    total_cells = 0
    for res, zmin, zmax in SUMMARY_LEVELS:
        if res == 6:
            key = base
        else:
            parent = {int(c): h3.str_to_int(h3.cell_to_parent(h3.int_to_str(int(c)), res)) for c in uniq}
            key = base.map(parent)
        out = summarize_cells(df, key)
        total_cells += len(out)
        src = os.path.join(GEOJSON, f"summary_r{res}.geojsonl")
        write_cells(out, src, res, h3)
        outp = os.path.join(TMP, f"summary_r{res}.pmtiles")
        cmd = WSL + ["tippecanoe", "-o", wsl_out(outp), "-f", "-l", "summary", "-n", "summary", f"-Z{zmin}", f"-z{zmax}",
                     "-pk", "-pf", "-ab", "-q", "-t", TMP_WSL, wsl_path(src)]
        r = wsl_run(cmd, outp)
        recs.append({"res": res, "cells": int(len(out)), "zooms": [zmin, zmax], "returncode": r.returncode,
                     "bytes": os.path.getsize(outp) if os.path.exists(outp) else None})
        if r.returncode != 0:
            rec = {"step": "summary", "returncode": r.returncode, "levels": recs, "stderr_tail": r.stderr[-400:],
                   "seconds": round(time.time() - t0, 1)}
            log(rec)
            return rec
        pm_inputs.append(wsl_path(outp))
    outp = os.path.join(C.TILES, "summary.pmtiles")
    cmd = WSL + ["tile-join", "-o", wsl_out(outp), "-f", "-pk", "-n", "summary",
                 "-N", "Relative land productivity, Brazil 2020 to 2024, H3 summary cells"] + pm_inputs
    r = wsl_run(cmd, outp)
    rec = {"step": "summary", "cells": total_cells, "levels": recs, "returncode": r.returncode,
           "bytes": os.path.getsize(outp) if os.path.exists(outp) else None, "seconds": round(time.time() - t0, 1),
           "stderr_tail": r.stderr[-400:]}
    log(rec)
    return rec


# H3 resolution per zoom band of the summary tiles. Cell widths: res 4 about 40 km, res 5 about
# 15 km, res 6 about 6 km. Resolution 3 (100 km) was tried at zoom 3 and dropped: it averages
# every cell to balanced and reads as a handful of giant hexagons, so zoom 3 keeps resolution 4.
SUMMARY_LEVELS = [(4, 3, 5), (5, 6, 7), (6, 8, 9)]


def summarize_cells(df, key):
    """Per-cell summary of the scored fields grouped by `key` (an H3 index per row)."""
    g = df.groupby(key.values)
    return pd.DataFrame({
        "n_fields": g.size(),
        "area_ha": g["area_ha"].sum().round(1),
        "mean_change": g["change"].mean().round(4),
        "share_decline": g["change_class"].apply(lambda s: s.isin(["decline", "large_decline"]).mean()).round(4),
        "share_gain": g["change_class"].apply(lambda s: s.isin(["gain", "large_gain"]).mean()).round(4),
        "share_no_data": g["change_class"].apply(lambda s: (s == "no_data").mean()).round(4),
        "mean_prod_2020": g["prod_2020"].mean().round(4),
        "mean_prod_2024": g["prod_2024"].mean().round(4),
        "dominant_crop_2020": g["crop_2020"].agg(lambda s: int(s.mode().iloc[0]) if s.notna().any() else None),
        "dominant_crop_2024": g["crop_2024"].agg(lambda s: int(s.mode().iloc[0])),
        "share_pasture": g["crop_2024"].apply(lambda s: (s == 15).mean()).round(4),
        "dominant_decision": g["decision"].agg(lambda s: s.mode().iloc[0]),
    })


def write_cells(out, src, res, h3):
    with open(src, "w", encoding="utf-8", newline="\n") as fh:
        for cell, row in out.iterrows():
            hx = h3.int_to_str(int(cell))
            ring = [[round(lng, 6), round(lat, 6)] for lat, lng in h3.cell_to_boundary(hx)]
            ring.append(ring[0])
            props = {"h3": hx, "res": res}
            for k, v in row.items():
                if v is None or (isinstance(v, float) and v != v):
                    continue
                props[k] = int(v) if k in ("n_fields", "dominant_crop_2020", "dominant_crop_2024") else (float(v) if isinstance(v, (float, np.floating)) else v)
            fh.write(json.dumps({"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [ring]}},
                                separators=(",", ":")) + "\n")


# ---------------------------------------------------------------- stats

def build_stats(states):
    uf = C.state_uf_map(2024)
    blank = lambda: {"n_fields": 0, "area_ha": 0.0, "change_class": {}, "decision": {}, "crop_2020": {}, "crop_2024": {}}  # noqa: E731

    def add(dst, counts, ab_counts):
        dst["n_fields"] += counts["n_fields"]
        dst["area_ha"] += counts["area_ha"]
        for key in ("change_class", "decision", "crop_2020", "crop_2024"):
            for k, v in counts[key].items():
                dst[key][k] = dst[key].get(k, 0) + v
        dst["change_class"]["abandoned"] = dst["change_class"].get("abandoned", 0) + ab_counts
        dst["decision"]["restore"] = dst["decision"].get("restore", 0) + ab_counts

    brazil = blank()
    per_state = {}
    for s in states:
        p = os.path.join(C.ANALYSIS, "year=2024", f"state={s}", "counts.json")
        if not os.path.exists(p):
            continue
        with open(p) as fh:
            counts = json.load(fh)
        st = blank()
        add(st, counts, counts.get("abandoned", 0))
        st["area_ha"] = round(st["area_ha"], 1)
        st["confidence_low"] = counts.get("confidence_low", 0)
        per_state[uf[s]] = st
        add(brazil, counts, counts.get("abandoned", 0))
        brazil["confidence_low"] = brazil.get("confidence_low", 0) + counts.get("confidence_low", 0)
    brazil["area_ha"] = round(brazil["area_ha"], 1)
    stats = {"placeholder": False, "generated": datetime.now().strftime("%Y-%m-%d"), "years": [2020, 2024],
             "source": "MODIS MOD13Q1 16-day NDVI, 250 m", "brazil": brazil, "states": per_state}
    os.makedirs(C.TILES, exist_ok=True)
    with open(os.path.join(C.TILES, "stats.json"), "w") as fh:
        json.dump(stats, fh, indent=1)
    return {"step": "stats", "states": len(per_state), "n_fields": brazil["n_fields"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["geojson", "fields", "summary", "stats", "all"])
    ap.add_argument("--states", nargs="*", default=None)
    ap.add_argument("--workers", type=int, default=3, help="GeoJSON writer processes")
    ap.add_argument("--parallel", type=int, default=3, help="tippecanoe runs at once")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--keep-geojson", action="store_true")
    args = ap.parse_args()
    states = args.states or [s for s in C.state_dirs(2024)
                             if os.path.exists(os.path.join(C.ANALYSIS, "year=2024", f"state={s}", "fields_scored.parquet"))]
    sizes = {s: os.path.getsize(C.fields_path(2024, s)) for s in states}
    states = sorted(states, key=lambda s: -sizes[s])
    t0 = time.time()
    if args.step in ("geojson", "all", "fields"):
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for f in as_completed([ex.submit(write_geojsonl, s, args.force) for s in states]):
                print(json.dumps(f.result()), flush=True)
    if args.step in ("fields", "all"):
        with ThreadPoolExecutor(max_workers=args.parallel) as ex:
            for f in as_completed([ex.submit(run_tippecanoe, s, args.force) for s in states]):
                print(json.dumps(f.result()), flush=True)
        print(json.dumps(tile_join(states)), flush=True)
        if not args.keep_geojson:
            for s in states:
                p = os.path.join(GEOJSON, f"{s}.geojsonl")
                if os.path.exists(p):
                    os.remove(p)
    if args.step in ("summary", "all"):
        print(json.dumps(build_summary(states)), flush=True)
    if args.step in ("stats", "all"):
        print(json.dumps(build_stats(states)), flush=True)
    print(f"done in {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
