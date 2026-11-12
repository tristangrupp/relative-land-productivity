"""Stage 3b: monthly weather rasters for Brazil, January 2015 to December 2024. No Earth Engine.

Precipitation: CHIRPS v2.0 monthly, 0.05 degree, mm per month. Source order:
  1. the global monthly netCDF already on disk at D:\\moisture-tracking\\reference\\chirps
     (read only, never modified), when it holds the month;
  2. otherwise https://data.chc.ucsb.edu/products/CHIRPS/v2.0/global_monthly/tifs/
     chirps-v2.0.YYYY.MM.tif.gz, one file at a time with backoff, because the CHC server
     answers 429 to bursts.
Temperature: TerraClimate tmax and tmin (degrees C, 1/24 degree), from the Idaho THREDDS
  server's NetCDF subset service, one request per variable and year clipped to Brazil
  (about 22 MB each). The Planetary Computer terraclimate collection ends in 2021 and its
  era5-pds collection in 2020, so neither has 2024; the AWS era5-pds bucket refuses
  anonymous reads (403, checked 2026-11-12).

Output: F:\\relative-land-productivity-data\\weather\\<variable>\\<YYYY-MM>.tif, float32,
EPSG:4326, one band, clipped to the Brazil bbox (-74.0, -34.0, -34.0, 5.5) snapped outward
to each grid. variable is chirps, tmax or tmin. A file that exists is skipped.

Environment: E:\\Water\\water intelligence\\wci_tools\\.venv (netCDF4, rasterio, xarray).

Usage:  python s03b_weather.py [--years 2015 2024] [--verify]
"""
import argparse
import gzip
import io
import json
import os
import random
import sys
import time
import urllib.request
import warnings

warnings.filterwarnings("ignore")
import netCDF4
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.windows import from_bounds

OUT = r"F:\relative-land-productivity-data\weather"
BBOX = (-74.0, -34.0, -34.0, 5.5)
CHIRPS_NC = r"D:\moisture-tracking\reference\chirps\chirps-v2.0.monthly.nc"
CHIRPS_URL = "https://data.chc.ucsb.edu/products/CHIRPS/v2.0/global_monthly/tifs/chirps-v2.0.%d.%02d.tif.gz"
TC_NCSS = ("http://thredds.northwestknowledge.net:8080/thredds/ncss/TERRACLIMATE_ALL/data/"
           "TerraClimate_%s_%d.nc?var=%s&north=%s&west=%s&east=%s&south=%s&horizStride=1"
           "&time_start=%d-01-01T00:00:00Z&time_end=%d-12-31T00:00:00Z&accept=netcdf")
TC_POINT = ("http://thredds.northwestknowledge.net:8080/thredds/ncss/TERRACLIMATE_ALL/data/"
            "TerraClimate_%s_%d.nc?var=%s&latitude=%s&longitude=%s&time=%d-%02d-01T00:00:00Z&accept=csv")
UA = {"User-Agent": "relative-land-productivity-weather/1.0"}


def months(y0, y1):
    return [(y, m) for y in range(y0, y1 + 1) for m in range(1, 13)]


def path(var, y, m):
    return os.path.join(OUT, var, f"{y}-{m:02d}.tif")


def write_tif(p, arr, transform, nodata, tags):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".part"
    with rasterio.open(tmp, "w", driver="GTiff", width=arr.shape[1], height=arr.shape[0], count=1,
                       dtype="float32", crs="EPSG:4326", transform=transform, nodata=nodata,
                       compress="deflate") as ds:
        ds.write(arr.astype("float32"), 1)
        ds.update_tags(**tags)
    os.replace(tmp, p)


def get(url, tries=6, timeout=300):
    """GET with exponential backoff; 429 and 5xx wait longer."""
    delay = 10
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as ex:
            if ex.code == 404:
                raise
            last = f"HTTP {ex.code}"
        except Exception as ex:   # noqa: BLE001
            last = str(ex)[:100]
        time.sleep(delay)
        delay = min(delay * 2, 300)
    raise RuntimeError(f"{url}: {last}")


# ---------------------------------------------------------------- CHIRPS
def chirps_window():
    """Pixel window of BBOX on the CHIRPS 0.05 degree grid (origin -180, 50)."""
    s = 0.05
    c0 = int(np.floor((BBOX[0] + 180) / s + 1e-9)); c1 = int(np.ceil((BBOX[2] + 180) / s - 1e-9))
    r0 = int(np.floor((50 - BBOX[3]) / s + 1e-9)); r1 = int(np.ceil((50 - BBOX[1]) / s - 1e-9))
    return r0, r1, c0, c1, Affine(s, 0, -180 + c0 * s, 0, -s, 50 - r0 * s)


class ChirpsNC:
    """The local global monthly netCDF, if present. Latitude ascending from -50, lon from -180."""

    def __init__(self):
        self.ds = None
        if os.path.exists(CHIRPS_NC):
            try:
                self.ds = netCDF4.Dataset(CHIRPS_NC)
            except OSError as ex:
                # the 5.35 GB copy on D: fails with "NetCDF: HDF error" (incomplete file)
                print("local CHIRPS netCDF unreadable:", str(ex)[:80], flush=True)
                return
            t = self.ds.variables["time"]
            d = netCDF4.num2date(t[:], t.units)
            self.idx = {(x.year, x.month): i for i, x in enumerate(d)}
            self.lat = self.ds.variables["latitude"][:]
            self.lon = self.ds.variables["longitude"][:]

    def has(self, y, m):
        return self.ds is not None and (y, m) in self.idx

    def read(self, y, m):
        r0, r1, c0, c1, tr = chirps_window()
        # netCDF rows run south to north; raster rows run north to south
        lat_top = 50 - r0 * 0.05
        lat_bot = 50 - r1 * 0.05
        j = np.where((self.lat > lat_bot) & (self.lat < lat_top))[0]
        i = np.where((self.lon > -180 + c0 * 0.05) & (self.lon < -180 + c1 * 0.05))[0]
        a = self.ds.variables["precip"][self.idx[(y, m)], j.min():j.max() + 1, i.min():i.max() + 1]
        a = np.ma.filled(a.astype("float64"), np.nan)[::-1, :]
        a[a < 0] = np.nan
        return a, tr


def chirps_month(y, m, nc):
    p = path("chirps", y, m)
    if os.path.exists(p):
        return "skip"
    if nc.has(y, m):
        a, tr = nc.read(y, m)
        src = "local netCDF " + CHIRPS_NC
    else:
        blob = get(CHIRPS_URL % (y, m))
        raw = gzip.GzipFile(fileobj=io.BytesIO(blob)).read()
        with rasterio.MemoryFile(raw) as mem, mem.open() as ds:
            win = from_bounds(*chirps_bounds(), transform=ds.transform)
            a = ds.read(1, window=win).astype("float64")
            nod = ds.nodata if ds.nodata is not None else -9999.0
            a[(a == nod) | (a < 0)] = np.nan
            tr = ds.window_transform(win)
        src = CHIRPS_URL % (y, m)
        time.sleep(2)   # pace the CHC server
    a = np.where(np.isfinite(a), a, -9999.0)
    write_tif(p, a, tr, -9999.0, {"source": src, "variable": "precipitation", "units": "mm per month",
                                   "product": "CHIRPS v2.0 monthly", "month": f"{y}-{m:02d}"})
    return src


def chirps_bounds():
    r0, r1, c0, c1, tr = chirps_window()
    return (-180 + c0 * 0.05, 50 - r1 * 0.05, -180 + c1 * 0.05, 50 - r0 * 0.05)


# ---------------------------------------------------------------- TerraClimate
def tc_year(var, y):
    paths = {m: path(var, y, m) for m in range(1, 13)}
    if all(os.path.exists(p) for p in paths.values()):
        return "skip"
    url = TC_NCSS % (var, y, var, BBOX[3] + 0.05, BBOX[0] - 0.05, BBOX[2] + 0.05, BBOX[1] - 0.05, y, y)
    blob = get(url, timeout=600)
    ds = netCDF4.Dataset("inmemory.nc", memory=blob)
    lat = ds.variables["lat"][:]
    lon = ds.variables["lon"][:]
    v = ds.variables[var]
    a = np.ma.filled(v[:].astype("float64"), np.nan)      # netCDF4 applies scale_factor
    t = ds.variables["time"]
    d = netCDF4.num2date(t[:], t.units)
    assert a.shape[0] == 12 and all(x.year == y for x in d), (a.shape, d[0], d[-1])
    step = float(abs(lat[1] - lat[0]))
    if lat[0] < lat[-1]:     # make rows run north to south
        a = a[:, ::-1, :]
        lat = lat[::-1]
    tr = Affine(step, 0, float(lon[0]) - step / 2, 0, -step, float(lat[0]) + step / 2)
    for i, x in enumerate(d):
        arr = np.where(np.isfinite(a[i]), a[i], -9999.0)
        write_tif(paths[x.month], arr, tr, -9999.0,
                  {"source": url.split("?")[0], "variable": var, "units": "degrees C",
                   "product": "TerraClimate", "month": f"{y}-{x.month:02d}"})
    return url.split("?")[0]


# ---------------------------------------------------------------- verification
def verify(seed=0):
    """A few pixel values on disk against the source, independently fetched."""
    rng = random.Random(seed)
    rows = []
    # CHIRPS: download one month's global tif.gz and compare 4 pixels with the clipped file.
    y, m = 2024, 6
    blob = get(CHIRPS_URL % (y, m))
    raw = gzip.GzipFile(fileobj=io.BytesIO(blob)).read()
    with rasterio.MemoryFile(raw) as mem, mem.open() as g, rasterio.open(path("chirps", y, m)) as d:
        for _ in range(4):
            lon, lat = rng.uniform(-70, -40), rng.uniform(-28, 2)
            vg = float(g.read(1, window=rasterio.windows.Window(*g.index(lon, lat)[::-1], 1, 1))[0, 0])
            vd = float(d.read(1, window=rasterio.windows.Window(*d.index(lon, lat)[::-1], 1, 1))[0, 0])
            rows.append({"var": "chirps", "month": f"{y}-{m:02d}", "lon": round(lon, 4), "lat": round(lat, 4),
                         "disk": vd, "source": vg, "abs_diff": abs(vd - vg)})
    # TerraClimate: the server's point service for 4 pixels, tmax and tmin, one month.
    for var in ("tmax", "tmin"):
        with rasterio.open(path(var, y, m)) as d:
            for _ in range(2):
                lon, lat = rng.uniform(-70, -40), rng.uniform(-28, 2)
                r, c = d.index(lon, lat)
                cx, cy = d.xy(r, c)
                csv = get(TC_POINT % (var, y, var, cy, cx, y, m)).decode()
                # The point service returns the packed int16, not the scaled value: the
                # variables have scale_factor 0.01 and add_offset -99 (read from the full
                # 2024 files on 2026-11-12), so 13500 means 36.0 degrees C.
                sv = float(csv.strip().splitlines()[-1].split(",")[-1]) * 0.01 - 99.0
                vd = float(d.read(1, window=rasterio.windows.Window(c, r, 1, 1))[0, 0])
                rows.append({"var": var, "month": f"{y}-{m:02d}", "lon": round(cx, 4), "lat": round(cy, 4),
                             "disk": vd, "source": sv, "abs_diff": abs(vd - sv)})
                time.sleep(1)
    for r in rows:
        print(r, flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs=2, type=int, default=[2015, 2024])
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    log = {"chirps": {}, "terraclimate": {}, "verify": []}
    nc = ChirpsNC()
    print("local CHIRPS netCDF:", "present" if nc.ds is not None else "absent", flush=True)
    t0 = time.time()
    for y, m in months(*a.years):
        try:
            log["chirps"][f"{y}-{m:02d}"] = chirps_month(y, m, nc)
        except Exception as ex:   # noqa: BLE001
            log["chirps"][f"{y}-{m:02d}"] = f"FAIL {str(ex)[:120]}"
            print("chirps", y, m, "failed:", str(ex)[:120], flush=True)
    print(f"chirps done in {time.time() - t0:.0f} s", flush=True)
    for var in ("tmax", "tmin"):
        for y in range(a.years[0], a.years[1] + 1):
            t1 = time.time()
            try:
                log["terraclimate"][f"{var}_{y}"] = tc_year(var, y)
            except Exception as ex:   # noqa: BLE001
                log["terraclimate"][f"{var}_{y}"] = f"FAIL {str(ex)[:120]}"
            print(var, y, log["terraclimate"][f"{var}_{y}"][:60], f"{time.time() - t1:.0f} s", flush=True)
    if a.verify:
        log["verify"] = verify()
    with open(os.path.join(OUT, "download_log.json"), "w") as fh:
        json.dump(log, fh, indent=1)


if __name__ == "__main__":
    sys.exit(main())
