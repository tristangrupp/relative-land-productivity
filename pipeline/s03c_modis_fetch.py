"""Stage 3c: fetch MODIS MOD13Q1 16-day NDVI tiles from the Planetary Computer.

Collection modis-13Q1-061 on the Planetary Computer STAC holds Terra (MOD13Q1) and Aqua
(MYD13Q1) composites eight days apart. This stage takes Terra only. Each agricultural year
(1 September to 31 August, "2020" is 2019-09-01 to 2020-08-31) is covered by 23 Terra
composites: the one that starts on day 241 of the year before (29 August, or 28 August in a
leap year) through the one that starts on day 225 of the year.

Only MODIS tiles that touch a prepared field are fetched. The tile footprints come from the
sinusoidal grid constants (sphere radius 6371007.181 m, 36 by 18 tiles of 1111950.5197 m,
4800 pixels of 231.656 m), densified and reprojected to EPSG:4326, and intersected with the
extraction tiles in grid\\tiles.parquet. The result is written once to
raw\\modis\\tiles_needed.json and reused by the weights and reduce stages.

For every composite and tile the assets 250m_16_days_NDVI, 250m_16_days_VI_Quality and
250m_16_days_pixel_reliability are downloaded as the GeoTIFFs the Planetary Computer serves,
on the native sinusoidal grid, to

  F:\\relative-land-productivity-data\\raw\\modis\\<YYYYDDD>\\<h##v##>_<asset>.tif

Three files at a time (--in-flight, threads; each thread signs its asset right before the
download), because a single stream got 0.14 to 0.44 MB/s of a link another project's
Sentinel-2 job holds at about 8 MB/s. The STAC item list of each composite is cached in <YYYYDDD>\\items.json
so a rerun does not search again. Assets are signed right before each download because the
SAS tokens expire after about 45 minutes. A download writes to <name>.part and resumes with
an HTTP Range request if the .part exists; it is renamed only when its size equals the
Content-Length, so a final file on disk is complete. A file that exists with the size the
manifest records is skipped without a network call. Failures retry with exponential backoff.
Every file is logged to raw\\modis\\fetch.log and raw\\modis\\manifest.jsonl with bytes and
seconds, and every ten files a line gives the measured rate and the projected finish time.

Order: agricultural year 2024 first, then 2020, composite by composite, tiles with more
field tiles first; tiles with fewer than 10 extraction tiles (h13v08, h12v12, h10v08) are
left for a last pass because each costs about 45 MB per composite for a handful of fields.

Environment: E:\\Water\\water intelligence\\wci_tools\\.venv (pystac_client, planetary_computer,
requests, pyproj, geopandas). No Earth Engine.

Usage:
  python s03c_modis_fetch.py                 fetch everything, resumable
  python s03c_modis_fetch.py --plan          list the composites and tiles, no download
  python s03c_modis_fetch.py --max-files 10  stop after ten downloads (rate measurement)
  python s03c_modis_fetch.py --years 2024    one agricultural year only
  python s03c_modis_fetch.py --in-flight 1   one file at a time
"""
import argparse
import concurrent.futures as cf
import json
import math
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

DATA = r"F:\relative-land-productivity-data"
RAW = os.path.join(DATA, "raw", "modis")
TILES_PARQUET = os.path.join(DATA, "grid", "tiles.parquet")
TILES_NEEDED = os.path.join(RAW, "tiles_needed.json")
MANIFEST = os.path.join(RAW, "manifest.jsonl")
LOG = os.path.join(RAW, "fetch.log")
MISSING = os.path.join(RAW, "missing.json")
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "modis-13Q1-061"
ASSETS = ["250m_16_days_NDVI", "250m_16_days_VI_Quality", "250m_16_days_pixel_reliability"]
YEARS = [2024, 2020]
MARGINAL_TILE_LIMIT = 10          # tiles touching fewer extraction tiles than this go last

# MODIS sinusoidal grid constants (MODIS Land tile grid, sphere of radius 6371007.181 m).
SINU_R = 6371007.181
TILE_M = 2 * math.pi * SINU_R / 36            # 1111950.5196666666 m
PIX_M = TILE_M / 4800                          # 231.65635826395825 m
X_MIN = -18 * TILE_M                           # -20015109.354 m
Y_MAX = 9 * TILE_M                             # 10007554.677 m
SINU_PROJ = "+proj=sinu +lon_0=0 +x_0=0 +y_0=0 +R=6371007.181 +units=m +no_defs"
CHUNK = 1 << 20
BBOX_BRAZIL = [-74.0, -34.0, -34.0, 5.5]


def composites_for_year(year):
    """The 23 Terra composite start dates of agricultural year `year`, as YYYYDDD strings."""
    out = [f"{year - 1}{d:03d}" for d in range(241, 354, 16)]      # 241 .. 353, 8 composites
    out += [f"{year}{d:03d}" for d in range(1, 226, 16)]             # 001 .. 225, 15 composites
    assert len(out) == 23
    return out


def doy_to_date(yyyyddd):
    return datetime(int(yyyyddd[:4]), 1, 1, tzinfo=timezone.utc) + timedelta(days=int(yyyyddd[4:]) - 1)


def tile_transform(h, v):
    """Affine of MODIS tile h, v on the sinusoidal grid (upper left origin, 4800 x 4800)."""
    from rasterio.transform import Affine
    return Affine(PIX_M, 0.0, X_MIN + h * TILE_M, 0.0, -PIX_M, Y_MAX - v * TILE_M)


def tile_footprint_4326(h, v, n=50):
    """Densified tile boundary reprojected to EPSG:4326, as a shapely Polygon."""
    import pyproj
    import shapely
    x0, y1 = X_MIN + h * TILE_M, Y_MAX - v * TILE_M
    x1, y0 = x0 + TILE_M, y1 - TILE_M
    xs = [x0 + (x1 - x0) * i / n for i in range(n + 1)]
    ys = [y0 + (y1 - y0) * i / n for i in range(n + 1)]
    ring = [(x, y0) for x in xs] + [(x1, y) for y in ys] + [(x, y1) for x in reversed(xs)] + [(x0, y) for y in reversed(ys)]
    tr = pyproj.Transformer.from_crs(pyproj.CRS.from_proj4(SINU_PROJ), "EPSG:4326", always_xy=True)
    lon, lat = tr.transform([p[0] for p in ring], [p[1] for p in ring])
    pts = [(a, b) for a, b in zip(lon, lat) if math.isfinite(a) and math.isfinite(b)]
    return shapely.Polygon(pts)


def tiles_needed(force=False):
    """MODIS tiles whose footprint intersects an extraction tile with fields, with counts."""
    if os.path.exists(TILES_NEEDED) and not force:
        with open(TILES_NEEDED) as fh:
            return json.load(fh)
    import geopandas as gpd
    import shapely
    tiles = gpd.read_parquet(TILES_PARQUET)
    sidx = tiles.sindex
    out = []
    for h in range(9, 16):
        for v in range(7, 13):
            fp = tile_footprint_4326(h, v)
            if fp.is_empty:
                continue
            cand = sidx.query(fp, predicate="intersects")
            if len(cand) == 0:
                continue
            sub = tiles.iloc[cand]
            states = sorted({s for lst in sub["states"] for s in lst})
            out.append({"hv": f"h{h:02d}v{v:02d}", "h": h, "v": v, "n_extraction_tiles": int(len(cand)),
                        "n_fields_2020": int(sub["n_fields_2020"].sum()), "n_fields_2024": int(sub["n_fields_2024"].sum()),
                        "min_tier": int(sub["tier"].min()), "states": states,
                        "bounds_4326": list(fp.bounds), "footprint_4326_wkt": shapely.to_wkt(fp, rounding_precision=5),
                        "marginal": bool(len(cand) < MARGINAL_TILE_LIMIT)})
    out.sort(key=lambda d: -d["n_extraction_tiles"])
    os.makedirs(RAW, exist_ok=True)
    with open(TILES_NEEDED, "w") as fh:
        json.dump({"written": datetime.now().isoformat(timespec="seconds"), "sinusoidal_proj4": SINU_PROJ,
                   "tile_m": TILE_M, "pixel_m": PIX_M, "x_min": X_MIN, "y_max": Y_MAX, "tiles": out}, fh, indent=1)
    return {"tiles": out}


def log(msg):
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def search_items(comp, catalog, hv_wanted):
    """Terra items of one composite over Brazil, cached as items.json in the composite folder."""
    d = os.path.join(RAW, comp)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "items.json")
    if os.path.exists(p):
        with open(p) as fh:
            return json.load(fh)
    start = doy_to_date(comp)
    rng = f"{start.strftime('%Y-%m-%d')}T00:00:00Z/{start.strftime('%Y-%m-%d')}T23:59:59Z"
    for attempt in range(6):
        try:
            items = list(catalog.search(collections=[COLLECTION], bbox=BBOX_BRAZIL, datetime=rng).items())
            break
        except Exception as ex:  # noqa: BLE001
            log(f"search {comp} failed ({ex}), retry {attempt + 1}")
            time.sleep(10 * (attempt + 1))
    else:
        raise RuntimeError(f"STAC search failed for {comp}")
    rec = {}
    for it in items:
        if not it.id.startswith(f"MOD13Q1.A{comp}."):
            continue
        hv = it.id.split(".")[2]
        if hv not in hv_wanted:
            continue
        rec[hv] = {"id": it.id, "assets": {k: it.assets[k].href for k in ASSETS if k in it.assets}}
    with open(p, "w") as fh:
        json.dump(rec, fh, indent=1)
    return rec


def load_manifest():
    done = {}
    if os.path.exists(MANIFEST):
        with open(MANIFEST) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                    done[r["path"]] = r
                except json.JSONDecodeError:
                    pass
    return done


def head_size(url):
    r = requests.head(url, timeout=60)
    r.raise_for_status()
    return int(r.headers["Content-Length"])


def download(href, dest, sign):
    """Download one asset with resume; returns (bytes_received, seconds, total_size)."""
    import planetary_computer as pc
    part = dest + ".part"
    got = 0
    t0 = time.time()
    delay = 5
    last_err = None
    for attempt in range(10):
        try:
            url = pc.sign(href) if sign else href
            have = os.path.getsize(part) if os.path.exists(part) else 0
            headers = {"Range": f"bytes={have}-"} if have else {}
            with requests.get(url, headers=headers, stream=True, timeout=(30, 180)) as r:
                if r.status_code == 416:            # the .part already holds everything
                    total = head_size(url)
                    if have == total:
                        os.replace(part, dest)
                        return got, time.time() - t0, total
                    os.remove(part)
                    have = 0
                    continue
                r.raise_for_status()
                if r.status_code == 206:
                    total = int(r.headers["Content-Range"].split("/")[-1])
                    mode = "ab"
                else:
                    total = int(r.headers["Content-Length"])
                    mode = "wb"
                    have = 0
                with open(part, mode) as fh:
                    for chunk in r.iter_content(CHUNK):
                        fh.write(chunk)
                        got += len(chunk)
            size = os.path.getsize(part)
            if size != total:
                raise IOError(f"size {size} != {total} after download")
            os.replace(part, dest)
            return got, time.time() - t0, total
        except Exception as ex:  # noqa: BLE001
            last_err = str(ex)[:200]
            log(f"  retry {attempt + 1} after {delay}s: {os.path.basename(dest)}: {last_err}")
            time.sleep(delay)
            delay = min(delay * 2, 300)
    raise RuntimeError(f"gave up on {dest}: {last_err}")


def build_queue(years, needed):
    """(composite, hv, asset, href-lookup-key) in download order."""
    main = [t["hv"] for t in needed if not t["marginal"]]
    marginal = [t["hv"] for t in needed if t["marginal"]]
    q = []
    for group in (main, marginal):
        for year in years:
            for comp in composites_for_year(year):
                for hv in group:
                    for a in ASSETS:
                        q.append((comp, hv, a))
    return q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, nargs="*", default=YEARS)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--max-files", type=int, default=0)
    ap.add_argument("--recompute-tiles", action="store_true")
    ap.add_argument("--in-flight", type=int, default=3, help="files downloaded at the same time")
    args = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    needed = tiles_needed(force=args.recompute_tiles)["tiles"]
    queue = build_queue(args.years, needed)
    comps = sorted({c for c, _, _ in queue})
    if args.plan:
        print(f"{len(needed)} MODIS tiles, {len(comps)} composites, {len(queue)} files")
        for t in needed:
            print(t["hv"], t["n_extraction_tiles"], "extraction tiles", "marginal" if t["marginal"] else "", t["states"])
        print(comps)
        return
    import pystac_client
    catalog = pystac_client.Client.open(STAC)
    hv_wanted = {t["hv"] for t in needed}
    manifest = load_manifest()
    missing = {}
    if os.path.exists(MISSING):
        with open(MISSING) as fh:
            missing = json.load(fh)
    items = {}
    t_start = time.time()
    n_done = n_skip = 0
    bytes_done = 0.0
    secs_active = 0.0
    size_seen = {}                      # (hv, asset) -> list of sizes, for the projection
    lock = threading.Lock()
    log(f"start: {len(queue)} files queued, {len(manifest)} already in manifest, {args.in_flight} in flight")

    def work(i, comp, hv, asset):
        """Resolve the item, skip or download one file. Runs in a worker thread."""
        dest = os.path.join(RAW, comp, f"{hv}_{asset}.tif")
        rel = os.path.relpath(dest, RAW)
        if os.path.exists(dest) and (rel in manifest and manifest[rel]["bytes"] == os.path.getsize(dest)):
            return ("skip", i, rel, os.path.getsize(dest), 0.0, 0, comp, hv, asset, None)
        with lock:
            if comp not in items:
                items[comp] = search_items(comp, catalog, hv_wanted)
                absent = sorted(hv_wanted - set(items[comp]))
                if absent:
                    missing[comp] = absent
                    with open(MISSING, "w") as fh:
                        json.dump(missing, fh, indent=1)
                    log(f"{comp}: no Terra item for {absent}")
            rec = items[comp].get(hv)
        if rec is None or asset not in rec["assets"]:
            return ("absent", i, rel, 0, 0.0, 0, comp, hv, asset, None)
        if os.path.exists(dest):
            # on disk but not in the manifest: check the size against the server once
            try:
                total = head_size(__import__("planetary_computer").sign(rec["assets"][asset]))
            except Exception as ex:  # noqa: BLE001
                log(f"head failed for {rel}: {ex}")
                total = -1
            if os.path.getsize(dest) == total:
                return ("verified", i, rel, total, 0.0, 0, comp, hv, asset, rec["id"])
            os.remove(dest)
        got, secs, total = download(rec["assets"][asset], dest, sign=True)
        return ("ok", i, rel, total, secs, got, comp, hv, asset, rec["id"])

    def handle(res):
        nonlocal n_done, n_skip, bytes_done, secs_active
        status, i, rel, total, secs, got, comp, hv, asset, item_id = res
        if status == "absent":
            return
        size_seen.setdefault((hv, asset), []).append(total)
        if status == "skip":
            n_skip += 1
            return
        if status == "verified":
            with open(MANIFEST, "a") as fh:
                fh.write(json.dumps({"path": rel, "bytes": total, "seconds": None, "when": None, "id": item_id}) + "\n")
            manifest[rel] = {"bytes": total}
            n_skip += 1
            return
        n_done += 1
        bytes_done += got
        secs_active += secs
        with open(MANIFEST, "a") as fh:
            fh.write(json.dumps({"path": rel, "bytes": total, "received": got, "seconds": round(secs, 2),
                                 "when": datetime.now().isoformat(timespec="seconds"), "id": item_id}) + "\n")
        manifest[rel] = {"bytes": total}
        log(f"{rel} {total} bytes {secs:.1f} s {got / max(secs, 1e-6) / 1e6:.2f} MB/s")
        if n_done % 10 == 0:
            wall = time.time() - t_start
            rate = bytes_done / max(wall, 1e-6)          # wall-clock rate: files overlap in flight
            remaining = queue[i + 1:]
            est = 0.0
            glob_mean = {a: sum(sz for (hv2, a2), ss in size_seen.items() if a2 == a for sz in ss) /
                         max(1, sum(len(ss) for (hv2, a2), ss in size_seen.items() if a2 == a)) for a in ASSETS}
            for c2, hv2, a2 in remaining:
                d2 = os.path.relpath(os.path.join(RAW, c2, f"{hv2}_{a2}.tif"), RAW)
                if d2 in manifest:
                    continue
                ss = size_seen.get((hv2, a2))
                est += (sum(ss) / len(ss)) if ss else glob_mean.get(a2, 0.0)
            eta = datetime.now() + timedelta(seconds=est / max(rate, 1e-6))
            log(f"progress: {n_done} files, {bytes_done / 1e9:.2f} GB in {wall / 3600:.2f} h wall "
                f"({rate / 1e6:.2f} MB/s aggregate), {len(remaining)} files left, about {est / 1e9:.1f} GB, "
                f"projected finish {eta.strftime('%Y-%m-%d %H:%M')}")

    stop = False
    with cf.ThreadPoolExecutor(max_workers=args.in_flight) as ex:
        pending = {}
        for i, (comp, hv, asset) in enumerate(queue):
            if stop:
                break
            while len(pending) >= args.in_flight:
                done, _ = cf.wait(list(pending), return_when=cf.FIRST_COMPLETED)
                for f in done:
                    pending.pop(f)
                    handle(f.result())
                    if args.max_files and n_done >= args.max_files:
                        stop = True
            if stop:
                break
            pending[ex.submit(work, i, comp, hv, asset)] = i
        for f in cf.as_completed(list(pending)):
            handle(f.result())
    if stop:
        log(f"stopping after {n_done} files (--max-files)")
    log(f"end: {n_done} downloaded, {n_skip} skipped, {bytes_done / 1e9:.2f} GB, "
        f"{(time.time() - t_start) / 3600:.2f} h wall, missing composites: {json.dumps(missing)}")


if __name__ == "__main__":
    main()
