"""Shared paths, class tables and helpers for the s04 and s05 stages.

Paths follow the folder contract in BRIEF.md. Everything the analyze agent writes lives under
F:\\relative-land-productivity-data\\analysis\\ except the tiles, which go to tiles\\.
"""
import os

import numpy as np

DATA = r"F:\relative-land-productivity-data"
FIELDS = os.path.join(DATA, "fields")
EXTRACTED = os.path.join(DATA, "extracted")
WEATHER = os.path.join(DATA, "weather")
ANALYSIS = os.path.join(DATA, "analysis")
METRICS = os.path.join(ANALYSIS, "metrics")
RELATIVE = os.path.join(ANALYSIS, "relative")
XYEAR = os.path.join(ANALYSIS, "modis_xyear")
TILES = os.path.join(DATA, "tiles")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALENDAR = os.path.join(REPO, "data", "calendars", "class_window_lookup.csv")
SUMMARIES = os.path.join(REPO, "data", "summaries")

AG_YEARS = [2020, 2024]
POLY_YEARS = [2020, 2024]

# MapBiomas Collection 10 agricultural classes the prepared fields hold (s01_prepare_fields.py).
AG_CLASSES = [39, 15, 19, 41, 20, 40, 62, 21, 18, 46, 47, 48, 35, 9]

# Class to crop group. 19 and 41 share one group (temporary crop), so a field that moves
# between them is not a crop switch, and the peer class for the relative metric is the group.
CROP_GROUP = {39: "soybean", 15: "pasture", 19: "temporary_crop", 41: "temporary_crop", 20: "sugarcane",
              40: "rice", 62: "cotton", 21: "mosaic", 9: "forest_plantation", 18: "agriculture",
              46: "coffee", 47: "citrus", 48: "perennial", 35: "oil_palm"}

# Peer class key per MapBiomas class: the class itself, except that 19 and 41 pool.
PEER_CLASS = {c: (19 if c in (19, 41) else c) for c in AG_CLASSES}

# Classes with no bare month, METHODS.md section 4: the baseline is the 5th percentile of the
# class in the state and year instead of the field's own annual minimum. Forest plantation (9)
# is added to the six the methods list because a plantation has no bare month either.
PERENNIAL = {20, 46, 47, 48, 35, 15, 9}

# Month order of the agricultural year: September is position 0, August is 11.
def month_pos(m):
    return (int(m) - 9) % 12


def state_dirs(year):
    d = os.path.join(FIELDS, f"year={year}")
    return sorted(s[len("state="):] for s in os.listdir(d) if s.startswith("state="))


def fields_path(year, state):
    return os.path.join(FIELDS, f"year={year}", f"state={state}", "fields.parquet")


def classes_path(year, state):
    return os.path.join(EXTRACTED, "mapbiomas", f"year={year}", f"state={state}", "classes.parquet")


def ndvi_path(source, polys, ay, state, root=None):
    """The per-field NDVI series table for a source, polygon year and agricultural year."""
    if source == "modis":
        if root:
            return os.path.join(root, f"year={polys}", f"state={state}", "ndvi_16day.parquet")
        if polys == ay:
            return os.path.join(EXTRACTED, "modis", f"year={polys}", f"state={state}", "ndvi_16day.parquet")
        return os.path.join(XYEAR, f"year={polys}", f"state={state}", "ndvi_16day.parquet")
    if source == "s2":
        base = root or os.path.join(EXTRACTED, "s2")
        return os.path.join(base, f"year={polys}", f"state={state}", "ndvi_monthly.parquet")
    raise ValueError(source)


def metrics_path(source, polys, ay, state):
    return os.path.join(METRICS, f"source={source}", f"polys={polys}", f"ay={ay}", f"{state}.parquet")


def relative_path(source, polys, ay, state):
    return os.path.join(RELATIVE, f"source={source}", f"polys={polys}", f"ay={ay}", f"{state}.parquet")


def state_uf_map(year=2024):
    """Folder name to two-letter UF, read from the first row of each prepared fields table."""
    import pyarrow.parquet as pq
    out = {}
    for s in state_dirs(year):
        pf = pq.ParquetFile(fields_path(year, s))
        out[s] = pf.read_row_group(0, columns=["state_uf"]).column(0)[0].as_py()
    return out


def load_windows():
    """(uf, class) to (start_month, end_month). Classes 9 and 18 are not in the table and take the full year."""
    import pandas as pd
    df = pd.read_csv(CALENDAR)
    win = {(r.state, int(r.mapbiomas_class)): (int(r.window_start_month), int(r.window_end_month)) for r in df.itertuples()}
    for uf in df["state"].unique():
        for c in (9, 18):
            win.setdefault((uf, c), (9, 8))
    return win


def muni_to_int(series):
    """Seven digit IBGE geocode strings to int64; anything else becomes -1."""
    import pandas as pd
    v = pd.to_numeric(series, errors="coerce")
    return v.fillna(-1).astype(np.int64).values


def h3_cells(lat, lon, res=6):
    """H3 cell index per point as int64, for one resolution."""
    import h3.api.basic_int as h3i
    f = h3i.latlng_to_cell
    out = np.empty(len(lat), dtype=np.int64)
    for i in range(len(lat)):
        out[i] = f(float(lat[i]), float(lon[i]), res)
    return out


def h3_parent(cells, res):
    import h3.api.basic_int as h3i
    f = h3i.cell_to_parent
    out = np.empty(len(cells), dtype=np.int64)
    for i in range(len(cells)):
        out[i] = f(int(cells[i]), res)
    return out


def mad_sd(x):
    """1.4826 times the median absolute deviation, the robust standard deviation of METHODS.md."""
    med = np.nanmedian(x)
    return 1.4826 * np.nanmedian(np.abs(x - med))
