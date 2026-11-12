"""Stage 3g: Sentinel-2 monthly maximum NDVI per field, fetched and reduced tile by tile.

For every extraction tile (1024 x 1024 pixels of the MapBiomas grid, about 30 m, see
grid\\grid.json) and every month of the two agricultural years (2019-09 to 2020-08 and
2023-09 to 2024-08), this script

1. searches the Planetary Computer STAC collection sentinel-2-l2a once per tile and
   agricultural year, groups the items by solar day and month, drops the MGRS granules of a
   day that only repeat pixels another granule of the same day already covers (neighboring
   granules overlap by about 10 km, and every item read costs its whole window), scores
   each solar day by the share of the tile it covers times one minus its eo:cloud_cover,
   and keeps the three best days of the month (four when the three best all have cloud
   cover above 60 percent). With --min-days 2 the month stops at two days once the chance
   that a pixel was clear on at least one kept day reaches --target-clear (0.98);
2. signs the kept items at load time (planetary_computer.sign through odc.stac's patch_url;
   the SAS tokens last about 45 minutes, so signing at search time is not enough) and loads
   B04, B08 at the tile geobox with resampling "average" (this reads the 20 m overview of
   the 10 m bands) and SCL with "nearest", grouped by solar day;
3. subtracts the 1000 reflectance offset on processing baseline 04.00 and later, masks SCL
   0, 1, 3, 8, 9, 10, 11, drops NDVI below -0.2 and B08 below 0.01 reflectance, and takes
   the per-pixel maximum NDVI over the month and the count of clear observations;
4. reduces the two arrays to every field of both years that touches the tile with the
   exactextract coverage weights from s03g_weights.py (built once per tile, cached under
   weights\\s2\\<tile_id>.npz) as a sparse matrix product, and appends one row per field to
   extracted\\s2\\tiles\\<tile_id>.parquet with the columns

     fid, year_layer (2020 or 2024, the field layer), state, period (YYYY-MM),
     ndvi_max (coverage-weighted mean of the pixel monthly maximum over valid pixels),
     n_clear (coverage-weighted mean clear count), w_valid (coverage weight on valid
     pixels), w_total (coverage weight of the field inside the tile).

   The composite raster is never written unless --keep-rasters is set, so disk stays flat.

Resume is at tile-month granularity: the periods already in the tile parquet are skipped.
Progress goes to extracted\\s2\\progress.log, one line per tile-month with seconds and MB
read. MB is exact for this process: GDAL's HTTP reads go through a local counting CONNECT
proxy (CountingProxy below) and the bytes are shared equally among the loads in flight, so
other processes on the machine do not count.

Environment: C:\\Users\\grupp\\miniconda3\\envs\\ftwtools\\python.exe (odc.stac, dask,
pystac_client, planetary_computer, rasterio, scipy, pyarrow). Weights are built by the
wci_tools venv in a subprocess when missing. No Earth Engine.

Usage:
  python s03g_s2_fetch_reduce.py run --state Mato_Grosso [--state Para ...] | --tier 1 [2]
        | --tiles r64_c66 ... [--workers 4] [--threads 2] [--limit-tiles 20] [--months 2024-01 ...]
        [--days 3] [--min-days 2] [--target-clear 0.98] [--keep-rasters]
  python s03g_s2_fetch_reduce.py status [--state ...] [--tier ...]
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import subprocess
import sys
import threading
import time
import warnings

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
os.environ.setdefault("GDAL_HTTP_MULTIRANGE", "YES")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "6")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")
os.environ.setdefault("GDAL_INGESTED_BYTES_AT_OPEN", "65536")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.tiff")
os.environ.setdefault("VSI_CACHE", "TRUE")
os.environ.setdefault("GDAL_CACHEMAX", "512")
warnings.filterwarnings("ignore")

import numpy as np
import odc.stac
import pandas as pd
import planetary_computer as pc
import psutil
import pystac_client
import shapely
from odc.geo.geobox import GeoBox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s03g_weights as wts  # noqa: E402

DATA = wts.DATA
OUT_DIR = os.path.join(DATA, "extracted", "s2")
TILES_OUT = os.path.join(OUT_DIR, "tiles")
RAW_DIR = os.path.join(DATA, "raw", "s2")
PROGRESS = os.path.join(OUT_DIR, "progress.log")
WCI_PY = r"E:\Water\water intelligence\wci_tools\.venv\Scripts\python.exe"
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
BANDS = ["B04", "B08", "SCL"]
SCL_BAD = np.array([0, 1, 3, 8, 9, 10, 11])
TILE = wts.TILE
KEEP_DAYS = 3
KEEP_DAYS_CLOUDY = 4
MIN_DAYS = 3
TARGET_CLEAR = 0.98
CLOUDY_PCT = 60.0
MIN_DAY_COVERAGE = 0.05
MIN_GRANULE_GAIN = 0.01
AG_YEARS = {2020: ("2019-09-01", "2020-08-31"), 2024: ("2023-09-01", "2024-08-31")}

_log_lock = threading.Lock()
_cat_lock = threading.Lock()
_catalog = None


def periods_of(year):
    s, e = AG_YEARS[year]
    out, cur = [], pd.Timestamp(s)
    while cur <= pd.Timestamp(e):
        out.append(cur.strftime("%Y-%m"))
        cur += pd.offsets.MonthBegin(1)
    return out


ALL_PERIODS = periods_of(2020) + periods_of(2024)


def log(line):
    stamp = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with _log_lock:
        with open(PROGRESS, "a", encoding="utf-8") as fh:
            fh.write(f"{stamp} {line}\n")
        print(f"{stamp} {line}", flush=True)


class CountingProxy(threading.Thread):
    """A local HTTP CONNECT proxy that counts the bytes the COG reads pull down.

    GDAL is pointed at it with GDAL_HTTP_PROXY, so every range request of this process to
    the Planetary Computer blob storage is tunneled through here and the bytes coming back
    from the server are counted. psutil's per-process read_bytes misses socket reads on
    Windows (a 7.5 MB file read registered 1.4 MB in a test), and the machine-wide counter
    includes other projects' downloads, so this is the one exact per-process measure.
    Only GDAL traffic goes through it; the STAC and SAS requests go direct.
    """

    def __init__(self):
        super().__init__(daemon=True)
        import socket
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(64)
        self.port = self.sock.getsockname()[1]
        self.lock = threading.Lock()
        self.bytes_in = 0

    def run(self):
        while True:
            conn, _ = self.sock.accept()
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, client):
        import socket
        try:
            client.settimeout(60)
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = client.recv(4096)
                if not chunk:
                    client.close()
                    return
                head += chunk
            line = head.split(b"\r\n", 1)[0].decode("latin1")
            method, target = line.split(" ")[:2]
            if method != "CONNECT":
                client.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                client.close()
                return
            host, port = target.rsplit(":", 1)
            upstream = socket.create_connection((host, int(port)), timeout=60)
            client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        except Exception:  # noqa: BLE001
            client.close()
            return
        t = threading.Thread(target=self._pump, args=(client, upstream, False), daemon=True)
        t.start()
        self._pump(upstream, client, True)
        t.join(timeout=1)

    def _pump(self, src, dst, count):
        try:
            while True:
                data = src.recv(65536)
                if not data:
                    break
                if count:
                    with self.lock:
                        self.bytes_in += len(data)
                dst.sendall(data)
        except Exception:  # noqa: BLE001
            pass
        finally:
            for s_ in (src, dst):
                try:
                    s_.shutdown(2)
                except Exception:  # noqa: BLE001
                    pass


PROXY = CountingProxy()
PROXY.start()
os.environ["GDAL_HTTP_PROXY"] = f"127.0.0.1:{PROXY.port}"


class ByteMeter:
    """Shares the proxy's downloaded bytes among the loads in flight.

    Each delta between two samples is split equally among the loads active at that moment,
    so a tile-month's MB is a fair share, and the sum over a batch is exact.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.last = 0
        self.active = {}
        self.next_id = 0

    def read_total(self):
        with PROXY.lock:
            return PROXY.bytes_in

    def _tick(self):
        now = self.read_total()
        delta = now - self.last
        self.last = now
        if self.active:
            share = delta / len(self.active)
            for k in self.active:
                self.active[k] += share

    def begin(self):
        with self.lock:
            self._tick()
            k = self.next_id
            self.next_id += 1
            self.active[k] = 0.0
            return k

    def end(self, k):
        with self.lock:
            self._tick()
            return self.active.pop(k)


METER = ByteMeter()


_PROC = psutil.Process()


def rss_gb():
    """Resident memory of this process (all tile workers are threads in it), GB."""
    return _PROC.memory_info().rss / 1e9


def catalog():
    global _catalog
    with _cat_lock:
        if _catalog is None:
            _catalog = pystac_client.Client.open(STAC)
        return _catalog


def tile_geobox(tile_id, grid):
    return GeoBox((TILE, TILE), wts.tile_transform(tile_id, grid), "EPSG:4326")


def search_year(tile_id, year, grid):
    """All sentinel-2-l2a items over the tile in one agricultural year."""
    b = wts.tile_bounds(tile_id, grid)
    s, e = AG_YEARS[year]
    for attempt in range(5):
        try:
            return list(catalog().search(collections=["sentinel-2-l2a"], bbox=list(b),
                                         datetime=f"{s}T00:00:00Z/{e}T23:59:59Z", limit=400).items())
        except Exception as ex:  # noqa: BLE001
            err = str(ex)[:200]
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"STAC search failed for {tile_id} {year}: {err}")


def choose_days(items, tile_box):
    """Group a month's items by solar day and keep the least cloudy days.

    Score of a day = covered share of the tile x (1 - area-weighted cloud cover / 100),
    the expected clear share of the tile. Days are taken in score order. At most KEEP_DAYS
    are kept, or KEEP_DAYS_CLOUDY when the KEEP_DAYS best all have cloud cover above
    CLOUDY_PCT. With MIN_DAYS below KEEP_DAYS the list stops early once at least MIN_DAYS
    days are kept and the chance that a pixel was clear on at least one of them,
    1 - product(1 - score), reaches TARGET_CLEAR. A day covering under MIN_DAY_COVERAGE of
    the tile is dropped. Returns (kept items, kept day records, all day records).
    """
    days = {}
    for it in items:
        day = it.datetime.date().isoformat()
        days.setdefault(day, []).append(it)
    tile_area = tile_box.area
    recs = []
    for day, its in days.items():
        cand = []
        for it in its:
            inter = shapely.geometry.shape(it.geometry).intersection(tile_box)
            if not inter.is_empty:
                cand.append((inter.area, inter, it))
        if not cand:
            continue
        # Neighboring MGRS granules of one orbit overlap by about 10 km and hold the same
        # pixels there, and each item read costs its whole window over the tile. Keep the
        # fewest granules that cover the day's footprint: largest first, add one only when
        # it adds at least MIN_GRANULE_GAIN of the tile.
        cand.sort(key=lambda c: -c[0])
        full = shapely.union_all([c[1] for c in cand]).area
        union, chosen, cc, areas = None, [], [], []
        for area, inter, it in cand:
            new = inter if union is None else union.union(inter)
            gain = new.area - (0.0 if union is None else union.area)
            if chosen and gain < MIN_GRANULE_GAIN * tile_area:
                continue
            union, chosen = new, chosen + [it]
            cc.append(float(it.properties.get("eo:cloud_cover", 100.0)))
            areas.append(area)
            if union.area >= 0.995 * full:
                break
        cov = union.area / tile_area
        if cov < MIN_DAY_COVERAGE:
            continue
        cloud = float(np.average(cc, weights=areas))
        recs.append({"day": day, "items": chosen, "coverage": round(cov, 3), "cloud": round(cloud, 1),
                     "score": cov * (1 - cloud / 100.0), "granules_all": len(cand)})
    recs.sort(key=lambda r: -r["score"])
    k = KEEP_DAYS
    if len(recs) >= KEEP_DAYS and all(r["cloud"] > CLOUDY_PCT for r in recs[:KEEP_DAYS]):
        k = KEEP_DAYS_CLOUDY
    kept, miss = [], 1.0
    for r in recs[:k]:
        kept.append(r)
        miss *= 1 - r["score"]
        if len(kept) >= MIN_DAYS and 1 - miss >= TARGET_CLEAR:
            break
    kept.sort(key=lambda r: r["day"])
    kept_items = [it for r in kept for it in r["items"]]
    return kept_items, kept, recs


def boa_offsets(items, times):
    """Per solar day, 1000 when the day's scenes are processing baseline 04.00 or later.

    L2A reflectance has a +1000 offset from baseline 04.00 (25 January 2022). The Planetary
    Computer keeps it in the assets; without this correction January 2024 soybean NDVI near
    Sorriso came out at 0.37 instead of 0.68 in the probe. A day with mixed baselines takes
    the majority.
    """
    by_day = {}
    for it in items:
        day = str(it.datetime.date())
        pb = str(it.properties.get("s2:processing_baseline", "00.00"))
        by_day.setdefault(day, []).append(1000 if pb >= "04.00" else 0)
    out = []
    for t in times:
        offs = by_day.get(str(t)[:10], [0])
        out.append(1000 if sum(1 for o in offs if o) * 2 >= len(offs) else 0)
    return out


def load_month(items, gbox, threads):
    """Load the kept items and return (ndvi_max float32 with NaN, n_clear uint8)."""
    err = None
    for attempt in range(3):
        try:
            ds = odc.stac.load(items, bands=BANDS, geobox=gbox, groupby="solar_day",
                               chunks={"time": 1, "x": TILE, "y": TILE},
                               resampling={"B04": "average", "B08": "average", "SCL": "nearest"},
                               dtype="uint16", nodata=0, patch_url=pc.sign)
            ds = ds.compute(scheduler="threads", num_workers=threads)
            err = None
            break
        except Exception as ex:  # noqa: BLE001
            err = str(ex)[:200]
            time.sleep(5 * (attempt + 1))
    if err:
        raise RuntimeError(err)
    scl = ds["SCL"].values
    clear = ~np.isin(scl, SCL_BAD)
    b4 = ds["B04"].values.astype("float32")
    b8 = ds["B08"].values.astype("float32")
    for i, off in enumerate(boa_offsets(items, ds["time"].values)):
        if off:
            b4[i] = np.maximum(b4[i] - off, 0)
            b8[i] = np.maximum(b8[i] - off, 0)
    clear &= (b4 + b8) > 0
    clear &= b8 >= 100  # B08 below 0.01 reflectance is shadow or residual cloud
    with np.errstate(invalid="ignore", divide="ignore"):
        nd = (b8 - b4) / (b8 + b4)
    clear &= nd >= -0.2
    nd[~clear] = np.nan
    n_clear = clear.sum(axis=0).astype("uint8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mx = np.nanmax(nd, axis=0).astype("float32")
    return mx, n_clear, int(scl.shape[0])


def reduce_fields(W, mx, n_clear):
    """Coverage-weighted field means. Returns dict of arrays, one value per weights row."""
    v = mx.reshape(-1).astype(np.float64)
    valid = np.isfinite(v)
    num = W @ np.where(valid, v, 0.0)
    den = W @ valid.astype(np.float64)
    wsum = np.asarray(W.sum(axis=1)).ravel()
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = np.where(den > 0, num / den, np.nan)
        ncl = np.where(wsum > 0, (W @ n_clear.reshape(-1).astype(np.float64)) / wsum, np.nan)
    return {"ndvi_max": ndvi.astype(np.float32), "n_clear": ncl.astype(np.float32),
            "w_valid": den.astype(np.float32), "w_total": wsum.astype(np.float32)}


def write_raster(tile_id, period, gbox, mx, n_clear):
    import rasterio
    d = os.path.join(RAW_DIR, tile_id)
    os.makedirs(d, exist_ok=True)
    prof = dict(driver="GTiff", width=TILE, height=TILE, crs="EPSG:4326", transform=gbox.affine,
                compress="deflate", predictor=2, tiled=True)
    q = np.full(mx.shape, -32768, dtype="int16")
    ok = np.isfinite(mx)
    q[ok] = np.clip(np.round(mx[ok] * 10000), -10000, 10000).astype("int16")
    p = os.path.join(d, f"{period}.tif")
    with rasterio.open(p + ".part", "w", count=1, dtype="int16", nodata=-32768, **prof) as dst:
        dst.write(q, 1)
        dst.descriptions = ["ndvi_max"]
    os.replace(p + ".part", p)
    p = os.path.join(d, f"{period}_count.tif")
    with rasterio.open(p + ".part", "w", count=1, dtype="uint8", **prof) as dst:
        dst.write(n_clear, 1)
    os.replace(p + ".part", p)


def tile_out_path(tile_id):
    return os.path.join(TILES_OUT, f"{tile_id}.parquet")


def done_periods(tile_id):
    p = tile_out_path(tile_id)
    if not os.path.exists(p):
        return set()
    try:
        return set(pd.read_parquet(p, columns=["period"])["period"].unique())
    except Exception:  # noqa: BLE001
        return set()


def append_rows(tile_id, df):
    p = tile_out_path(tile_id)
    os.makedirs(TILES_OUT, exist_ok=True)
    if os.path.exists(p):
        old = pd.read_parquet(p)
        df = pd.concat([old[~old["period"].isin(set(df["period"]))], df], ignore_index=True)
    tmp = p + ".part"
    df.to_parquet(tmp, index=False, compression="zstd")
    os.replace(tmp, p)


def ensure_weights(tile_id):
    p = wts.weights_path(tile_id)
    if os.path.exists(p):
        return "cached"
    t0 = time.time()
    r = subprocess.run([WCI_PY, os.path.join(os.path.dirname(os.path.abspath(__file__)), "s03g_weights.py"),
                        "build", tile_id], capture_output=True, text=True, timeout=1800)
    if r.returncode != 0 or not os.path.exists(p):
        raise RuntimeError(f"weights build failed: {r.stderr[-400:]}")
    return f"built {time.time() - t0:.0f}s"


def process_tile(tile_id, periods, grid, threads, keep_rasters):
    """Fetch and reduce every pending month of one tile. Returns (ok, fail, skipped)."""
    t_tile = time.time()
    try:
        how = ensure_weights(tile_id)
        W, meta = wts.load_weights(tile_id)
    except Exception as ex:  # noqa: BLE001
        log(f"tile={tile_id} status=weights_fail err={str(ex)[:200]!r}")
        return 0, len(periods), 0
    nf = W.shape[0]
    done = done_periods(tile_id)
    todo = [p for p in periods if p not in done]
    if not todo:
        log(f"TILE_DONE tile={tile_id} months=0 skipped={len(periods)} fields={nf} s=0.0")
        return 0, 0, len(periods)
    gbox = tile_geobox(tile_id, grid)
    tile_box = shapely.box(*wts.tile_bounds(tile_id, grid))
    base = pd.DataFrame({"fid": meta["fid"], "year_layer": meta["year_layer"],
                         "state": meta["state"].astype(str)})
    years_needed = sorted({y for y in AG_YEARS if any(p in periods_of(y) for p in todo)})
    n_ok = n_fail = 0
    for year in years_needed:
        t0 = time.time()
        try:
            items = search_year(tile_id, year, grid)
        except Exception as ex:  # noqa: BLE001
            log(f"tile={tile_id} year={year} status=search_fail err={str(ex)[:200]!r}")
            n_fail += sum(1 for p in todo if p in periods_of(year))
            continue
        t_search = time.time() - t0
        by_month = {}
        for it in items:
            by_month.setdefault(it.datetime.strftime("%Y-%m"), []).append(it)
        log(f"tile={tile_id} year={year} status=search items={len(items)} s={t_search:.1f} weights={how}")
        for period in [p for p in todo if p in periods_of(year)]:
            t0 = time.time()
            month_items = by_month.get(period, [])
            kept, recs, all_recs = choose_days(month_items, tile_box)
            n_days = len(all_recs)
            allcloud = ",".join(f"{r['cloud']:.0f}" for r in all_recs[:8])
            mb = 0.0
            if not kept:
                out = base.copy()
                out["period"] = period
                out["ndvi_max"] = np.float32(np.nan)
                out["n_clear"] = np.float32(0)
                out["w_valid"] = np.float32(0)
                out["w_total"] = np.asarray(W.sum(axis=1)).ravel().astype(np.float32)
                append_rows(tile_id, out)
                log(f"tile={tile_id} period={period} status=empty days=0 of=0 items={len(month_items)} "
                    f"fields={nf} s={time.time() - t0:.1f} mb=0.0")
                n_ok += 1
                continue
            k = METER.begin()
            try:
                mx, n_clear, n_loaded = load_month(kept, gbox, threads)
            except Exception as ex:  # noqa: BLE001
                METER.end(k)
                log(f"tile={tile_id} period={period} status=fail days={len(recs)} of={n_days} "
                    f"s={time.time() - t0:.1f} err={str(ex)[:160]!r}")
                n_fail += 1
                continue
            mb = METER.end(k) / 1e6
            red = reduce_fields(W, mx, n_clear)
            out = base.copy()
            out["period"] = period
            for c, v in red.items():
                out[c] = v
            append_rows(tile_id, out)
            if keep_rasters:
                write_raster(tile_id, period, gbox, mx, n_clear)
            del mx, n_clear
            clouds = ",".join(f"{r['cloud']:.0f}" for r in recs)
            covs = ",".join(f"{r['coverage']:.2f}" for r in recs)
            share_valid = float(np.mean(red["w_valid"] / np.maximum(red["w_total"], 1e-9) >= 0.5)) if nf else 0.0
            gr_all = sum(r["granules_all"] for r in recs)
            log(f"tile={tile_id} period={period} status=ok days={n_loaded} of={n_days} items={len(kept)} of_items={gr_all} "
                f"cloud={clouds} cov={covs} allcloud={allcloud} fields={nf} valid_share={share_valid:.2f} "
                f"ndvi_p50={np.nanmedian(red['ndvi_max']) if nf else float('nan'):.3f} "
                f"s={time.time() - t0:.1f} mb={mb:.1f} rss_gb={rss_gb():.2f}")
            n_ok += 1
    log(f"TILE_DONE tile={tile_id} months={n_ok} failed={n_fail} skipped={len(done)} fields={nf} "
        f"s={time.time() - t_tile:.1f}")
    return n_ok, n_fail, len(done)


def select_tiles(states, tiers):
    """Tiles in run order: state by state as listed, each tile once."""
    order = list(states or [])
    for t in tiers or []:
        order += wts.TIER_STATES[int(t)]
    seen, out = set(), []
    for st in order:
        for tid in wts.tiles_for_states([st]):
            if tid not in seen:
                seen.add(tid)
                out.append((st, tid))
    return out


def run(a):
    os.makedirs(OUT_DIR, exist_ok=True)
    grid = wts.load_grid()
    odc.stac.configure_rio(cloud_defaults=True, GDAL_HTTP_MAX_RETRY=6, GDAL_HTTP_RETRY_DELAY=2,
                           GDAL_HTTP_PROXY=os.environ["GDAL_HTTP_PROXY"])
    tiles = [("explicit", t) for t in a.tiles] if a.tiles else select_tiles(a.state, a.tier)
    if a.limit_tiles:
        tiles = tiles[:a.limit_tiles]
    periods = a.months or ALL_PERIODS
    bad = [p for p in periods if p not in ALL_PERIODS]
    if bad:
        sys.exit(f"months outside the two agricultural years: {bad}")
    states = ",".join(dict.fromkeys(st for st, _ in tiles))
    log(f"RUN_START tiles={len(tiles)} months={len(periods)} workers={a.workers} threads={a.threads} "
        f"days={KEEP_DAYS} min_days={MIN_DAYS} target_clear={TARGET_CLEAR} states={states} pid={os.getpid()}")
    t0 = time.time()
    tot_ok = tot_fail = tot_skip = 0
    io0 = METER.read_total()
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(process_tile, tid, periods, grid, a.threads, a.keep_rasters): tid for _, tid in tiles}
        for f in cf.as_completed(futs):
            try:
                ok, fail, skip = f.result()
            except Exception as ex_:  # noqa: BLE001
                log(f"tile={futs[f]} status=tile_fail err={str(ex_)[:200]!r}")
                ok, fail, skip = 0, len(periods), 0
            tot_ok += ok
            tot_fail += fail
            tot_skip += skip
    el = time.time() - t0
    mb = (METER.read_total() - io0) / 1e6
    log(f"RUN_END tiles={len(tiles)} tile_months_ok={tot_ok} failed={tot_fail} skipped={tot_skip} "
        f"s={el:.0f} mb={mb:.0f} tile_months_per_min={tot_ok / el * 60 if el else 0:.2f} "
        f"mb_per_tile_month={mb / tot_ok if tot_ok else 0:.1f} mb_per_s={mb / el if el else 0:.2f} "
        f"peak_rss_gb={_PROC.memory_info().peak_wset / 1e9:.2f}")


def status(a):
    tiles = select_tiles(a.state, a.tier) if (a.state or a.tier) else [(s, t) for s in wts.TIER_STATES[1] + wts.TIER_STATES[2]
                                                                     for t in wts.tiles_for_states([s])]
    rows = []
    for st, tid in tiles:
        n = len(done_periods(tid))
        rows.append((st, tid, n))
    df = pd.DataFrame(rows, columns=["state", "tile_id", "months_done"]).drop_duplicates("tile_id")
    g = df.groupby("state", sort=False).agg(tiles=("tile_id", "count"),
                                            tiles_complete=("months_done", lambda s: int((s >= len(ALL_PERIODS)).sum())),
                                            tiles_started=("months_done", lambda s: int((s > 0).sum())),
                                            tile_months_done=("months_done", "sum"))
    g["tile_months_total"] = g["tiles"] * len(ALL_PERIODS)
    print(g.to_string())
    print(f"total tiles {len(df)}, complete {(df.months_done >= len(ALL_PERIODS)).sum()}, "
          f"tile-months done {df.months_done.sum()} of {len(df) * len(ALL_PERIODS)}")


def main():
    global KEEP_DAYS, KEEP_DAYS_CLOUDY
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "status"])
    ap.add_argument("--state", action="append", help="state folder name, repeatable, run order")
    ap.add_argument("--tier", action="append", type=int, help="1 or 2, repeatable")
    ap.add_argument("--workers", type=int, default=4, help="tiles in flight")
    ap.add_argument("--threads", type=int, default=2, help="dask threads per tile load")
    ap.add_argument("--limit-tiles", type=int, default=0)
    ap.add_argument("--tiles", nargs="*", help="explicit tile ids instead of --state or --tier")
    ap.add_argument("--months", nargs="*", help="YYYY-MM subset, default all 24")
    ap.add_argument("--keep-rasters", action="store_true")
    ap.add_argument("--days", type=int, default=3, help="solar days kept per month, default 3")
    ap.add_argument("--min-days", type=int, default=0,
                    help="stop early at this many days once --target-clear is reached; default = --days")
    ap.add_argument("--target-clear", type=float, default=0.98)
    a = ap.parse_args()
    global MIN_DAYS, TARGET_CLEAR
    KEEP_DAYS = a.days
    MIN_DAYS = a.min_days or a.days
    TARGET_CLEAR = a.target_clear
    KEEP_DAYS_CLOUDY = a.days + 1
    if a.cmd == "run":
        if not (a.state or a.tier or a.tiles):
            sys.exit("give --state or --tier")
        run(a)
    else:
        status(a)


if __name__ == "__main__":
    main()
