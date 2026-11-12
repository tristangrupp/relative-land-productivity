"""Stage 3 prototype: Sentinel-2 NDVI composites from the Planetary Computer, tiled.

For one 1024 x 1024 pixel tile on the MapBiomas EPSG:4326 grid (pixel 0.000269494585236
degrees, about 30 m; origin and tile indexing from F:\\...\\grid\\grid.json) and one period:
search the Planetary Computer STAC collection sentinel-2-l2a, sign the assets, load B04,
B08 and SCL with odc.stac.load at the tile's geobox (resampling "average" for the bands so
the COG overviews are read, "nearest" for SCL), mask SCL classes 0, 1, 3, 8, 9, 10, 11,
compute NDVI (B08 - B04) / (B08 + B04), reduce the period by median and by max, and write

  F:\\relative-land-productivity-data\\raw\\s2\\<tile_id>\\<period>.tif        int16, 2 bands
      ndvi_med, ndvi_max as NDVI x 10000, nodata -32768
  F:\\relative-land-productivity-data\\raw\\s2\\<tile_id>\\<period>_count.tif  uint8, 1 band
      n_clear, the number of unmasked observations per pixel

A tile whose two files exist is skipped, so a run resumes. No Earth Engine.

Environment: C:\\Users\\grupp\\miniconda3\\envs\\ftwtools\\python.exe (odc.stac 0.5.3, dask,
pystac_client, planetary_computer, rasterio). The reduction to fields runs separately in
the wci_tools venv (s03_probe_reduce.py), which has exactextract.

Usage:
  python s03_ndvi_tiles.py probe                       timing probe on three sites
  python s03_ndvi_tiles.py one TILE_ID START END [--res 30] [--workers 4]
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import threading
import time
import warnings

warnings.filterwarnings("ignore")
import numpy as np
import odc.stac
import psutil
import planetary_computer as pc
import pystac_client
import rasterio
from odc.geo.geobox import GeoBox
from rasterio.transform import Affine

DATA = r"F:\relative-land-productivity-data"
RAW = os.path.join(DATA, "raw", "s2")
PROBE = os.path.join(DATA, "probe")
GRID_JSON = os.path.join(DATA, "grid", "grid.json")
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
BANDS = ["B04", "B08", "SCL"]
SCL_BAD = [0, 1, 3, 8, 9, 10, 11]   # nodata, saturated, cloud shadow, cloud med/high, cirrus, snow
NODATA = -32768
TILE = 1024

# Fallback grid if grid.json is missing: the fields agent's constants of 2026-11-12.
GRID = {"pixel": 0.000269494585236, "x0": -74.000248665368, "y0": 5.500114990081524}
if os.path.exists(GRID_JSON):
    with open(GRID_JSON) as _fh:
        _g = json.load(_fh)
    GRID = {"pixel": _g["pixel_size_deg"], "x0": _g["origin"][0], "y0": _g["origin"][1]}
    assert _g["tile_size_px"] == TILE

SITES = {
    "sorriso_mt": (-55.7, -12.5),      # soybean
    "paragominas_pa": (-47.5, -3.0),   # pasture
    "humaita_am": (-63.0, -7.5),       # Amazonas
}
PERIODS = {
    "2024-01m": ("2024-01-01", "2024-02-01"),    # monthly
    "2024-01a": ("2024-01-01", "2024-01-17"),    # 16-day
}
_print_lock = threading.Lock()


def step_for(res_m):
    return GRID["pixel"] * res_m / 30.0


def tile_id_for(lon, lat, res_m=30):
    step = step_for(res_m)
    c = int(np.floor((lon - GRID["x0"]) / step)) // TILE
    r = int(np.floor((GRID["y0"] - lat) / step)) // TILE
    return f"r{r}_c{c}"


def parse_tile_id(tile_id):
    r, c = tile_id.split("_")
    return int(r[1:]), int(c[1:])


def tile_geobox(tile_id, res_m=30):
    r, c = parse_tile_id(tile_id)
    step = step_for(res_m)
    ox = GRID["x0"] + c * TILE * step
    oy = GRID["y0"] - r * TILE * step
    return GeoBox((TILE, TILE), Affine(step, 0, ox, 0, -step, oy), "EPSG:4326")


def out_paths(tile_id, period, res_m):
    d = os.path.join(RAW if res_m == 30 else RAW + f"_{res_m}m", tile_id)
    return os.path.join(d, f"{period}.tif"), os.path.join(d, f"{period}_count.tif")


def search(gbox, start, end):
    cat = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)
    bb = gbox.boundingbox
    items = list(cat.search(collections=["sentinel-2-l2a"], bbox=[bb.left, bb.bottom, bb.right, bb.top],
                            datetime=f"{start}/{end}").items())
    return items


def boa_offsets(items, times):
    """Per solar day, 1000 if the scenes are processing baseline 04.00 or later, else 0."""
    by_day = {}
    for it in items:
        day = np.datetime64(it.datetime.date().isoformat())
        pb = str(it.properties.get("s2:processing_baseline", "00.00"))
        by_day.setdefault(day, []).append(1000 if pb >= "04.00" else 0)
    out = []
    for t in times:
        day = np.datetime64(str(t)[:10])
        offs = by_day.get(day, [0])
        out.append(1000 if sum(1 for o in offs if o) * 2 >= len(offs) else 0)
    return out


def fetch(tile_id, period, start, end, res_m=30, workers=4, tag=None):
    """Load, composite and write one tile. Returns a dict of measurements."""
    p_nd, p_n = out_paths(tile_id, period, res_m)
    if os.path.exists(p_nd) and os.path.exists(p_n):
        return {"status": "skip", "tile": tile_id, "period": period}
    t0 = time.time()
    gbox = tile_geobox(tile_id, res_m)
    items = search(gbox, start, end)
    t_search = time.time() - t0
    if not items:
        return {"status": "empty", "tile": tile_id, "period": period, "seconds": round(t_search, 1)}
    err = None
    net0 = psutil.net_io_counters().bytes_recv
    for attempt in range(4):
        try:
            # The SAS tokens in a search result expire; re-sign at fetch time.
            ds = odc.stac.load(items, bands=BANDS, geobox=gbox, groupby="solar_day",
                               chunks={"time": 1, "x": TILE, "y": TILE},
                               resampling={"B04": "average", "B08": "average", "SCL": "nearest"},
                               dtype="uint16", nodata=0, patch_url=pc.sign)
            ds = ds.compute(scheduler="threads", num_workers=workers)
            err = None
            break
        except Exception as ex:   # noqa: BLE001
            err = str(ex)[:200]
            time.sleep(3 * (attempt + 1))
    if err:
        return {"status": "fail", "tile": tile_id, "period": period, "error": err}
    t_load = time.time() - t0 - t_search
    net_bytes = psutil.net_io_counters().bytes_recv - net0   # machine-wide, so an upper bound
    scl = ds["SCL"].values
    clear = ~np.isin(scl, SCL_BAD) & (scl != 0)
    b4 = ds["B04"].values.astype("float32")
    b8 = ds["B08"].values.astype("float32")
    # Processing baseline 04.00 (25 January 2022) and later store L2A reflectance with a
    # +1000 offset (BOA_ADD_OFFSET = -1000). Earth Engine's harmonized collection removes
    # it; the Planetary Computer assets do not. Without the correction January 2024
    # soybean NDVI came out at 0.37 instead of about 0.8. Offsets are per solar day from
    # the items' s2:processing_baseline; a day with mixed baselines takes the majority.
    offsets = boa_offsets(items, ds["time"].values)
    for i, off in enumerate(offsets):
        if off:
            b4[i] = np.maximum(b4[i] - off, 0)
            b8[i] = np.maximum(b8[i] - off, 0)
    clear &= (b4 + b8) > 0
    with np.errstate(invalid="ignore", divide="ignore"):
        nd = (b8 - b4) / (b8 + b4)
    nd[~clear] = np.nan
    n_clear = clear.sum(axis=0).astype("uint8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        med = np.nanmedian(nd, axis=0)
        mx = np.nanmax(nd, axis=0)

    def q(a):
        o = np.full(a.shape, NODATA, dtype="int16")
        ok = np.isfinite(a)
        o[ok] = np.clip(np.round(a[ok] * 10000), -10000, 10000).astype("int16")
        return o

    os.makedirs(os.path.dirname(p_nd), exist_ok=True)
    prof = dict(driver="GTiff", width=TILE, height=TILE, crs="EPSG:4326", transform=gbox.affine,
                compress="deflate", predictor=2, tiled=True)
    tmp = p_nd + ".part"
    with rasterio.open(tmp, "w", count=2, dtype="int16", nodata=NODATA, **prof) as dst:
        dst.write(q(med), 1)
        dst.write(q(mx), 2)
        dst.descriptions = ["ndvi_med", "ndvi_max"]
        dst.update_tags(source="sentinel-2-l2a Planetary Computer", period=f"{start}/{end}",
                        scl_masked=",".join(map(str, SCL_BAD)), scenes=str(len(items)),
                        solar_days=str(scl.shape[0]), scale="NDVI x 10000",
                        boa_offset_days=",".join(str(o) for o in offsets))
    os.replace(tmp, p_nd)
    tmp = p_n + ".part"
    with rasterio.open(tmp, "w", count=1, dtype="uint8", nodata=None, **prof) as dst:
        dst.write(n_clear, 1)
        dst.descriptions = ["n_clear"]
    os.replace(tmp, p_n)
    total = time.time() - t0
    # Bytes read: odc.stac does not report. Each solar day reads three bands over the tile
    # from the COG overview nearest the output resolution (the 20 m overview for 30 m output,
    # the 20 m band itself for 20 m output), uint16, deflate about halves it on the wire.
    ovr_px = (TILE * res_m / 20.0) ** 2
    est_bytes = int(scl.shape[0] * 3 * ovr_px * 2 * 0.5)
    out = {"status": "ok", "tile": tile_id, "period": period, "res_m": res_m, "workers": workers,
           "seconds": round(total, 1), "seconds_search": round(t_search, 1),
           "seconds_load": round(t_load, 1), "scenes": len(items), "solar_days": int(scl.shape[0]),
           "est_bytes_read": est_bytes, "net_bytes_recv_machine": int(net_bytes), "disk_bytes": os.path.getsize(p_nd) + os.path.getsize(p_n),
           "zero_clear_share": round(float((n_clear == 0).mean()), 4),
           "mean_clear_obs": round(float(n_clear.mean()), 2),
           "ndvi_med_p50": None if not np.isfinite(med).any() else round(float(np.nanmedian(med)), 3),
           "tag": tag}
    with _print_lock:
        print(out, flush=True)
    return out


def run_batch(jobs, workers, label, results):
    """jobs: list of fetch kwargs. Returns a throughput record."""
    t0 = time.time()
    with cf.ThreadPoolExecutor(workers) as ex:
        out = list(ex.map(lambda kw: fetch(**kw), jobs))
    el = time.time() - t0
    n_ok = sum(1 for o in out if o["status"] == "ok")
    for o in out:
        o["batch"] = label
        results.append(o)
    rec = {"label": label, "parallel_tiles": workers, "n": len(jobs), "ok": n_ok,
           "seconds": round(el, 1), "tiles_per_min": round(n_ok / el * 60, 2) if el else 0,
           "mean_seconds_per_tile": round(float(np.mean([o["seconds"] for o in out if o["status"] == "ok"] or [0])), 1)}
    print(rec, flush=True)
    return rec


def probe():
    os.makedirs(PROBE, exist_ok=True)
    results, batches = [], []
    # 1. Serial: three sites, two periods, 30 m.
    for site, (lon, lat) in SITES.items():
        tid = tile_id_for(lon, lat)
        for pname, (s, e) in PERIODS.items():
            o = fetch(tid, pname, s, e, 30, workers=8, tag=site)
            o["batch"] = "serial"
            results.append(o)
    # 2. Sorriso at 20 m, monthly.
    tid20 = tile_id_for(*SITES["sorriso_mt"], 20)
    o = fetch(tid20, "2024-01m", *PERIODS["2024-01m"], res_m=20, workers=8, tag="sorriso_mt")
    o["batch"] = "serial_20m"
    results.append(o)
    # 3. Parallel tiles: fresh neighbors of the three sites, 30 m, monthly.
    ring4, ring8 = [], []
    for site, (lon, lat) in SITES.items():
        r0, c0 = parse_tile_id(tile_id_for(lon, lat))
        for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            ring4.append(f"r{r0 + dr}_c{c0 + dc}")
        for dr, dc in ((1, 1), (-1, -1), (1, -1), (-1, 1)):
            ring8.append(f"r{r0 + dr}_c{c0 + dc}")
    s, e = PERIODS["2024-01m"]
    jobs4 = [dict(tile_id=t, period="2024-01m", start=s, end=e, res_m=30, workers=2) for t in ring4[:4]]
    jobs8 = [dict(tile_id=t, period="2024-01m", start=s, end=e, res_m=30, workers=2)
             for t in (ring4[4:] + ring8)[:8]]
    batches.append(run_batch(jobs4, 4, "parallel4_30m_monthly", results))
    batches.append(run_batch(jobs8, 8, "parallel8_30m_monthly", results))
    with open(os.path.join(PROBE, "measurements_pc.json"), "w") as fh:
        json.dump({"grid": GRID, "results": results, "batches": batches}, fh, indent=1)
    print(f"done, {len(results)} tile loads", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["probe", "one"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--res", type=int, default=30)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    if a.cmd == "probe":
        probe()
    else:
        tid, s, e = a.args
        print(fetch(tid, f"{s}_{e}", s, e, a.res, a.workers))
