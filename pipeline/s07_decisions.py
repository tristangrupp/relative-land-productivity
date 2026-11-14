"""Stage 7b: two-tier land use decisions, the area call per H3 resolution 6 cell first (resolution 5
where the 6 km cell is too thin) and the field call inside it second (methods/METHODS.md section 7,
pipeline/DECISIONS_V2.md, the 14 November 2026 entries of WORKLOG.md).

  python s07_decisions.py biome      IBGE biome per 2024 field -> analysis\\decisions\\biome\\<State>.parquet
  python s07_decisions.py native     native vegetation share around each 2024 field -> analysis\\decisions\\native\\<State>.parquet
  python s07_decisions.py national   cell_vs_nation and the plain change per H3 cell and class, resolutions 5 and 6
  python s07_decisions.py dist       distributions of the area term, to set the thresholds
  python s07_decisions.py area       area call per resolution 6 cell -> analysis\\decisions\\area_cells.parquet,
                                     area_cells_r5.parquet, data/summaries/area_cells.csv.gz
  python s07_decisions.py fields     field call per state, written into fields_scored.parquet and the abandoned layer
  python s07_decisions.py report     national, state and ecoregion counts, old against new cross table
  python s07_decisions.py lookup     docs/data/ecoregions.json for the site (names and Scale C context)
  python s07_decisions.py all

Run after s04_change.py and s06_ecoregion_peers.py score. Rerunning s04_change.py rewrites
fields_scored.parquet with the first-version decision only, so this stage must follow it.

Sources. analysis\\sources.json lists the states whose live tables come from Sentinel-2
(s09_swap_state_to_s2.py). For such a state the area tier reads the s2 seasonal integral
calibrated to the MODIS scale (metric_cal_<year> of analysis\\source=s2\\year=2024\\state=<S>\\
fields_scored.parquet, written by s08_s2_compare.py), falling back to MODIS for a peer class
with no calibration, and the recently converted rule reads the calibrated s2 r_eco_2024. Every
field row gets a `source` column (modis or s2).

Resolution. Since 14 November 2026 ("area map looks too homogenous") the area call is made per
H3 resolution 6 cell (about 6 km). A resolution 6 cell where neither group reaches the minimum
(one class with MIN_FIELDS valid fields) takes the call of its resolution 5 parent; area_level
records 6 or 5. The thresholds are in the national SD of cell medians at the cell's own
resolution, so the same -0.75 and -0.4 apply at both (METHODS.md 7.1 gives the cell shares).
pasture_only: pasture present, crops absent, and crop-class fields under PASTURE_ONLY_CROP_SHARE
of the cell's 2024 fields.

Native vegetation (14 November 2026). native_share_1km and native_share_250m: the share of
MapBiomas Collection 10 2024 pixels of native classes (NATIVE_CLASSES) in a band 1 km (250 m)
wide around the field's bounding box, from integral images of the 30 m map, so every field is
two rectangle sums. The band is around the bounding box, not the outline.

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
  none                no comparison possible: change_class no_data, a switched field with no 2024
                      value, or a newly cropped field with no 2024 ecoregion value (14 November 2026)
  low_confidence      (14 November 2026) the field's confidence is low (MODIS: under 6.25 ha or few
                      clear composites; s2: under 0.45 ha or few clear months): "too small to judge
                      yet". The call below is kept as decision_computed.
  abandon             the bare-soil rule of version 1 (below cell peers in both years, declining,
                      2024 integral under the 20th percentile of the class in the state)
  converted_below     newly cropped (not crop or pasture in 2020), 2024 below ecoregion peers (r_eco_2024 < -0.5)
  converted_ok        newly cropped, 2024 at or above ecoregion peers
  restore             the cell's area call is restore_area; or (14 November 2026) a same-crop field
                      that declined, in an area_declining cell that is pasture_only
  convert_cropland    inside the IBGE Amazon biome, a pasture field at or above its cell peers
                      (r_adj_2024 >= -0.5) in a good_land_underused cell: productive pasture on good
                      cropland, conversion of the already cleared pasture to crops possible
                      (assisted_regen is checked after restore and the area tier, so it can replace
                      restore; it is listed with restore_candidate below)
  improve_pasture     inside the Amazon biome, a pasture field below its cell peers in a
                      good_land_underused cell
  convert_pasture     outside the Amazon biome, a pasture field not above its cell peers in a
                      good_land_underused cell (improve or convert pasture)
  assisted_regen      (14 November 2026) a same-crop field below its cell peers and declining, or a
                      restore field, with regrowth on at least REGROWTH_T of its pixels
  restore_candidate   same crop, below cell peers in 2024, stable or declining, and the share of the
                      1 km band in native patches of LARGE_PATCH_HA or more at or above NATIVE_T
  improve_spare       the same, native share under NATIVE_T: improve yields, which spares land elsewhere
  switch_paid_off     crop group switched, 2024 at or above cell peers (r_adj_2024 >= -0.5)
  switch_failed       crop group switched, 2024 below cell peers
  improve_yields      same crop, declined against cell peers while at or above them, or below them and gaining
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
PASTURE_ONLY_CROP_SHARE = 0.05  # crop-class fields under this share of the cell's fields
AMAZON = 1        # IBGE CD_Bioma of Amazônia
BIOME_SHP = os.path.join(C.DATA, "raw", "biomes", "lm_bioma_250.shp")
BIOME_DEG = 0.0025
_MB = os.path.join(C.DATA, "raw", "mapbiomas")
MAPBIOMAS = {2024: os.path.join(_MB, "brazil_coverage_2024.tif"), 2020: os.path.join(_MB, "brazil_coverage_2020.tif"),
             2023: os.path.join(_MB, "mapbiomas_brazil_2023.tif")}
# Regrowth: anthropic in 2020 (the study's first year) and native in 2024, and native in 2023 too
# when the 2023 map is on disk. On 14 November 2026 the shared network link fell to about 60 KB/s
# (the Sentinel-2 extraction and the MODIS long-series download share it), so the 2023 map (1.18 GB)
# and the 2019, 2021 and 2022 maps were not fetched and the release uses 2020 and 2024 only.
ANTHRO_YEARS = (2020,)
NATIVE_CLASSES = [3, 4, 5, 6, 11, 12, 49, 50]
ANTHROPIC = [15, 18, 19, 20, 21, 35, 36, 39, 40, 41, 46, 47, 48, 62]  # pasture, agriculture, mosaic of uses
LARGE_PATCH_HA = 50.0
REGROWTH_T = 0.10  # set from the distribution, METHODS.md 7.3
NATIVE_BANDS = {"native_share_1km": 1000.0, "native_share_250m": 250.0}
NATIVE_T = 0.30   # set from the distribution, METHODS.md 7.3
SOURCES_JSON = os.path.join(C.ANALYSIS, "sources.json")
S2_ROOT = os.path.join(C.ANALYSIS, "source=s2")

AREA = ["restore_area", "good_land_underused", "system_misfit", "area_declining", "area_fine", "none"]
DECISIONS = ["restore", "assisted_regen", "restore_candidate", "converted_below", "converted_ok", "convert_cropland", "improve_pasture",
             "convert_pasture", "switch_paid_off", "switch_failed", "improve_spare", "improve_yields", "intensify", "keep",
             "abandon", "abandoned_outline", "low_confidence", "none"]
SOURCES = ["modis", "s2"]
DECISIONS_V1 = ["restore", "switch_crop", "change_pattern", "abandon", "intensify", "improve_yields", "keep", "none"]
TRENDS = ["declining", "steady", "gaining", "unknown"]
FRONTIER = ["Madeira-Tapajós moist forests", "Xingu-Tocantins-Araguaia moist forests", "Mato Grosso tropical dry forests",
            "Tocantins/Pindare moist forests", "Tapajós-Xingu moist forests", "Purus-Madeira moist forests",
            "Southwest Amazon moist forests"]


def log(**kw):
    kw["t"] = datetime.now().isoformat(timespec="seconds")
    print(json.dumps(kw, ensure_ascii=False, default=str), flush=True)


# ----------------------------------------------------------------------------- sources, biomes, native vegetation

def sources():
    """State -> record of the swap ({"source": "s2", "change_scale": k, ...}); absent states are MODIS."""
    if not os.path.exists(SOURCES_JSON):
        return {}
    with open(SOURCES_JSON) as fh:
        return json.load(fh)


def source_of(state):
    return sources().get(state, {}).get("source", "modis")


def s2_table(state, cols):
    return read(os.path.join(S2_ROOT, "year=2024", f"state={state}", "fields_scored.parquet"), cols)


def s2_calibrated(state):
    """Per agricultural year, the peer classes the s2 calibration of the state covers."""
    cal = pd.read_csv(os.path.join(S2_ROOT, "decisions", f"calibration_{state}.csv"))
    cal = cal[cal["slope"].notna()]
    return {ay: set(cal.loc[cal["ay"] == ay, "peer_cls"].astype(int)) for ay in (2020, 2024)}


def biome(states):
    """IBGE biome (2019, 1:250,000, CD_Bioma 1 to 6) of each 2024 field centroid, from a raster of
    BIOME_DEG degrees; a centroid outside every biome polygon (coast, islands) takes 0."""
    import rasterio.features
    from rasterio.transform import from_origin
    import geopandas as gpd
    t0 = time.time()
    g = gpd.read_file(BIOME_SHP).to_crs(4326)
    west, north = -74.5, 5.5
    w, h = int(round(46.0 / BIOME_DEG)), int(round(40.0 / BIOME_DEG))
    tr = from_origin(west, north, BIOME_DEG, BIOME_DEG)
    ras = rasterio.features.rasterize(((geom, int(c)) for geom, c in zip(g.geometry, g["CD_Bioma"])),
                                      out_shape=(h, w), transform=tr, fill=0, dtype="uint8")
    os.makedirs(os.path.join(OUT, "biome"), exist_ok=True)
    tot = {}
    for s in states:
        m = read(C.metrics_path(SOURCE, 2024, 2024, s), ["fid", "lon", "lat"])
        col = np.clip(((m["lon"].values - west) / BIOME_DEG).astype(np.int64), 0, w - 1)
        row = np.clip(((north - m["lat"].values) / BIOME_DEG).astype(np.int64), 0, h - 1)
        b = ras[row, col]
        pd.DataFrame({"fid": m["fid"].values, "biome": b.astype(np.int8)}).to_parquet(os.path.join(OUT, "biome", f"{s}.parquet"), index=False)
        for k, v in pd.Series(b).value_counts().items():
            tot[int(k)] = tot.get(int(k), 0) + int(v)
    log(step="biome", fields_by_biome=tot, seconds=round(time.time() - t0))


def load_biome(state, fid):
    b = read(os.path.join(OUT, "biome", f"{state}.parquet"), ["fid", "biome"])
    assert np.array_equal(b["fid"].values, fid), "biome fid order differs"
    return b["biome"].values.astype(np.int8)


def native_state(state, strip=2048, halo=128):
    """Native vegetation, patch size and regrowth around and inside each 2024 field of one state.

    The MapBiomas Collection 10 maps (2024 and 2020 from the extraction grid, 2023 from source.coop,
    all on the same 30 m grid) are read in windows: the state's fields are sorted by
    the middle row of their bounding box and cut into strips of `strip` rows; each window covers
    the strip's bounding boxes grown by `halo` pixels. Per window:
      native      class in NATIVE_CLASSES (2024)
      patch       8-connected component of native pixels (scipy.ndimage.label); its area is
                  counted inside the window only, so a patch that leaves the window is capped there
      large       native pixel of a patch of at least LARGE_PATCH_HA
      regrowth    native in 2024 (and in 2023 when that map is on disk; not in this release) and an
                  anthropic class (ANTHROPIC) in 2020
    and per field, with the band of NATIVE_BANDS around the bounding box:
      native_share_1km, native_share_250m   native share of observed pixels in the band
      native_share_1km_large                the same counting only large patches
      largest_patch_ha_1km                  area of the largest patch with a pixel in the box grown by 1 km
      regrowth_share_1km                    regrowth share in the 1 km band
      regrowth_share_in                     regrowth share of the pixels whose centers fall inside the
                                            2024 outline (rasterized in the window); NaN when none does"""
    import rasterio
    import rasterio.features
    import shapely
    from rasterio.windows import Window
    from scipy import ndimage
    t0 = time.time()
    tab = pq.read_table(C.fields_path(2024, state), columns=["fid", "bbox", "geometry"])
    fid = tab.column("fid").to_numpy()
    bb = pd.DataFrame(tab.column("bbox").to_pylist())
    geom_col = tab.column("geometry").cast(pa.large_binary())
    srcs = {y: rasterio.open(p) for y, p in MAPBIOMAS.items() if os.path.exists(p)}
    s24 = srcs[2024]
    T = s24.transform
    H, W = s24.height, s24.width
    px = abs(T.e)
    r0 = np.clip(np.floor((T.f - bb["ymax"].values) / px).astype(np.int64), 0, H - 1)
    r1 = np.clip(np.ceil((T.f - bb["ymin"].values) / px).astype(np.int64), r0 + 1, H)
    c0 = np.clip(np.floor((bb["xmin"].values - T.c) / T.a).astype(np.int64), 0, W - 1)
    c1 = np.clip(np.ceil((bb["xmax"].values - T.c) / T.a).astype(np.int64), c0 + 1, W)
    lat = 0.5 * (bb["ymin"].values + bb["ymax"].values)
    m_row = 111320.0 * px
    m_col = 111320.0 * T.a * np.cos(np.radians(lat))
    n = len(fid)
    cols = ["native_share_1km", "native_share_250m", "native_share_1km_large", "largest_patch_ha_1km",
            "regrowth_share_1km", "regrowth_share_in"]
    out = {k: np.full(n, np.nan, dtype=np.float32) for k in cols}
    mid = (r0 + r1) // 2
    order = np.argsort(mid, kind="stable")
    smid = mid[order]
    edges = np.arange(int(smid.min()) // strip * strip, int(smid.max()) + strip + 1, strip)
    bounds = np.searchsorted(smid, edges)
    nat_lut = np.zeros(256, dtype=bool)
    nat_lut[NATIVE_CLASSES] = True
    ant_lut = np.zeros(256, dtype=bool)
    ant_lut[ANTHROPIC] = True
    eight = np.ones((3, 3), dtype=bool)

    def integral(mask):
        S = np.zeros((mask.shape[0] + 1, mask.shape[1] + 1), dtype=np.int32)
        np.cumsum(np.cumsum(mask, axis=0, dtype=np.int32), axis=1, dtype=np.int32, out=S[1:, 1:])
        return S

    def rect(S, a0, a1, b0, b1):
        return (S[a1, b1] - S[a0, b1] - S[a1, b0] + S[a0, b0]).astype(np.float64)

    for i in range(len(bounds) - 1):
        idx = order[bounds[i]:bounds[i + 1]]
        if len(idx) == 0:
            continue
        drm = int(np.ceil(1000.0 / m_row))
        dcm = np.ceil(1000.0 / m_col[idx]).astype(np.int64)
        wr0 = max(0, int(r0[idx].min()) - drm - halo)
        wr1 = min(H, int(r1[idx].max()) + drm + halo)
        wc0 = max(0, int((c0[idx] - dcm).min()) - halo)
        wc1 = min(W, int((c1[idx] + dcm).max()) + halo)
        win = Window(wc0, wr0, wc1 - wc0, wr1 - wr0)
        a24 = srcs[2024].read(1, window=win)
        nat = nat_lut[a24]
        obs = a24 > 0
        del a24
        if 2023 in srcs:
            reg = nat & nat_lut[srcs[2023].read(1, window=win)]
        else:
            reg = nat.copy()
        anth = np.zeros_like(nat)
        for y in ANTHRO_YEARS:
            anth |= ant_lut[srcs[y].read(1, window=win)]
        reg &= anth
        del anth
        lab, nlab = ndimage.label(nat, structure=eight)
        wlat = T.f - (wr0 + wr1) / 2 * px
        px_ha = (m_row * 111320.0 * T.a * np.cos(np.radians(wlat))) / 1e4
        pha = (np.bincount(lab.ravel(), minlength=nlab + 1) * px_ha).astype(np.float32)
        pha[0] = 0
        parea = pha[lab]
        del lab
        large = parea >= LARGE_PATCH_HA
        II = {"nat": integral(nat), "obs": integral(obs), "large": integral(large), "reg": integral(reg)}
        del nat, obs, large
        R0, R1 = r0[idx] - wr0, r1[idx] - wr0
        C0, C1 = c0[idx] - wc0, c1[idx] - wc0
        hh, ww = wr1 - wr0, wc1 - wc0
        for name, d in (("1km", 1000.0), ("250m", 250.0)):
            dr = int(np.ceil(d / m_row))
            dc = np.ceil(d / m_col[idx]).astype(np.int64)
            g0, g1 = np.clip(R0 - dr, 0, hh), np.clip(R1 + dr, 0, hh)
            h0, h1 = np.clip(C0 - dc, 0, ww), np.clip(C1 + dc, 0, ww)
            obs_b = rect(II["obs"], g0, g1, h0, h1) - rect(II["obs"], R0, R1, C0, C1)
            with np.errstate(invalid="ignore", divide="ignore"):
                ok = obs_b > 0
                nat_b = rect(II["nat"], g0, g1, h0, h1) - rect(II["nat"], R0, R1, C0, C1)
                out[f"native_share_{name}"][idx] = np.where(ok, nat_b / obs_b, np.nan)
                if name == "1km":
                    lg_b = rect(II["large"], g0, g1, h0, h1) - rect(II["large"], R0, R1, C0, C1)
                    rg_b = rect(II["reg"], g0, g1, h0, h1) - rect(II["reg"], R0, R1, C0, C1)
                    out["native_share_1km_large"][idx] = np.where(ok, lg_b / obs_b, np.nan)
                    out["regrowth_share_1km"][idx] = np.where(ok, rg_b / obs_b, np.nan)
                    G = (g0, g1, h0, h1)
        # largest patch with a pixel in the box grown by 1 km
        lp = out["largest_patch_ha_1km"]
        g0, g1, h0, h1 = G
        for j, a0, a1, b0, b1 in zip(idx.tolist(), g0.tolist(), g1.tolist(), h0.tolist(), h1.tolist()):
            lp[j] = parea[a0:a1, b0:b1].max()
        del parea
        # regrowth inside the outline: the strip's outlines rasterized into the window
        geoms = shapely.from_wkb(geom_col.take(pa.array(idx)).to_numpy(zero_copy_only=False))
        wt = rasterio.windows.transform(win, T)
        flab = rasterio.features.rasterize(zip(geoms, range(1, len(idx) + 1)), out_shape=(hh, ww), transform=wt,
                                           fill=0, dtype="int32")
        regm = (II["reg"][1:, 1:] - II["reg"][:-1, 1:] - II["reg"][1:, :-1] + II["reg"][:-1, :-1]).astype(bool)
        tot = np.bincount(flab.ravel(), minlength=len(idx) + 1)
        rin = np.bincount(flab.ravel(), weights=regm.ravel(), minlength=len(idx) + 1)
        with np.errstate(invalid="ignore", divide="ignore"):
            out["regrowth_share_in"][idx] = np.where(tot[1:] > 0, rin[1:] / tot[1:], np.nan)
        del II, flab, regm, geoms
    res = pd.DataFrame({"fid": fid, **{k: np.round(v, 4) for k, v in out.items()}})
    res.to_parquet(os.path.join(OUT, "native", f"{state}.parquet"), index=False)
    return {"state": state, "fields": int(n), "strips": int(len(bounds) - 1), "seconds": round(time.time() - t0)}


def native(states, workers=2):
    from concurrent.futures import ProcessPoolExecutor, as_completed
    os.environ.setdefault("GDAL_NUM_THREADS", "4")
    t0 = time.time()
    os.makedirs(os.path.join(OUT, "native"), exist_ok=True)
    sizes = {s: os.path.getsize(C.fields_path(2024, s)) for s in states}
    todo = sorted(states, key=lambda s: -sizes[s])
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(native_state, s): s for s in todo}
        for f in as_completed(futs):
            log(step="native", **f.result())
    d = pd.concat([read(os.path.join(OUT, "native", f"{s}.parquet"), ["native_share_1km", "native_share_1km_large",
                   "largest_patch_ha_1km", "regrowth_share_in", "regrowth_share_1km"]) for s in states])
    q = {c: {str(p): round(float(d[c].quantile(p)), 4) for p in (0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99)} for c in d.columns}
    with open(os.path.join(OUT, "native", "quantiles.json"), "w") as fh:
        json.dump(q, fh, indent=1)
    log(step="native", fields=int(len(d)), quantiles=q, seconds=round(time.time() - t0))


NATIVE_COLS = ["native_share_1km", "native_share_250m", "native_share_1km_large", "largest_patch_ha_1km",
               "regrowth_share_1km", "regrowth_share_in"]


def load_native(state, fid):
    n = read(os.path.join(OUT, "native", f"{state}.parquet"), ["fid"] + NATIVE_COLS)
    assert np.array_equal(n["fid"].values, fid), "native fid order differs"
    return n


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
    src = sources()
    for ay in (2020, 2024):
        parts = []
        for s in states:
            m = read(C.metrics_path(SOURCE, 2024, ay, s), ["fid", "peer_cls", "h3_5", "h3_6"])
            r = read(C.relative_path(SOURCE, 2024, ay, s), ["fid", "valid", "metric_adj"])
            assert np.array_equal(m["fid"].values, r["fid"].values), "relative table order differs"
            cls = m["peer_cls"].values.astype(np.int16)
            valid = r["valid"].values.astype(bool)
            val = r["metric_adj"].values.astype(np.float32)
            if src.get(s, {}).get("source") == "s2":
                t = s2_table(s, ["fid", f"valid_{ay}", f"metric_cal_{ay}", f"peer_cls_{ay}"])
                assert np.array_equal(t["fid"].values, m["fid"].values), "s2 table order differs"
                covered = np.isin(t[f"peer_cls_{ay}"].values, list(s2_calibrated(s)[ay]))
                cls = np.where(covered, t[f"peer_cls_{ay}"].values, cls).astype(np.int16)
                valid = np.where(covered, t[f"valid_{ay}"].values.astype(bool), valid)
                val = np.where(covered, t[f"metric_cal_{ay}"].values, val).astype(np.float32)
                log(step="national", state=s, ay=ay, source="s2", fields_s2=int(covered.sum()), fields_modis_fallback=int((~covered).sum()))
            parts.append(pd.DataFrame({"cls": cls, "h3_5": m["h3_5"].values, "h3_6": m["h3_6"].values, "valid": valid, "m": val}))
        frames[ay] = pd.concat(parts, ignore_index=True)
        log(step="national", ay=ay, rows=len(frames[ay]), seconds=round(time.time() - t0))
    # every cell holding 2024 fields, with its field counts by group (pasture_only and the fallback)
    f24 = frames[2024]
    grp = group_of(f24["cls"].values)
    for res in levels:
        cc = pd.DataFrame({"cell": f24[f"h3_{res}"].values, "crops": grp == "crops", "pasture": grp == "pasture"}) \
            .groupby("cell").agg(n_fields=("crops", "size"), n_crops=("crops", "sum"), n_pasture=("pasture", "sum")).reset_index()
        cc.to_parquet(os.path.join(OUT, f"cell_counts_r{res}.parquet"), index=False)
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


def area_table(res):
    """Pooled national terms and the area call per cell at one resolution, over every cell holding 2024 fields."""
    n = load_nation(res)
    t = pool(n, "crops", "v24", "change").join(pool(n, "pasture", "v24", "change"), how="outer") \
        .join(pool(n, "mosaic", "v24", "change"), how="outer").join(frontier(n), how="outer")
    for c in ("crops_level", "pasture_level", "crops_change", "pasture_change", "crops_n", "pasture_n",
              "mosaic_level", "mosaic_change"):
        if c not in t:
            t[c] = np.nan
    t["area_decision"] = area_call(t)
    cnt = pd.read_parquet(os.path.join(OUT, f"cell_counts_r{res}.parquet")).set_index("cell")
    t = t.join(cnt, how="outer")
    t["area_decision"] = t["area_decision"].fillna("none")
    with np.errstate(invalid="ignore", divide="ignore"):
        crop_share = (t["n_crops"].fillna(0) / t["n_fields"]).values
    t["pasture_only"] = (np.isfinite(t["pasture_level"].values) & ~np.isfinite(t["crops_level"].values)
                         & (np.nan_to_num(crop_share, nan=1.0) < PASTURE_ONLY_CROP_SHARE))
    # area score: the field-weighted 2024 level of crops and pasture against Brazil
    w_c = t["crops_n"].fillna(0).values
    w_p = t["pasture_n"].fillna(0).values
    num = np.nan_to_num(t["crops_level"].values) * w_c + np.nan_to_num(t["pasture_level"].values) * w_p
    with np.errstate(invalid="ignore", divide="ignore"):
        t["area_score"] = np.where(w_c + w_p > 0, num / np.maximum(w_c + w_p, 1), np.nan)
    t.index.name = "cell"
    return t


def build_area():
    """Area call per H3 resolution 6 cell on the national reference, the resolution 5 call where the
    6 km cell has no group; the ecoregion terms of the resolution 5 parent ride along as context."""
    import h3
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    t5 = area_table(5)
    e = load_cells()
    t5 = t5.join(pool(e, "crops", "cell_vs_eco_2024", "change", "eco_"), how="outer") \
        .join(pool(e, "pasture", "cell_vs_eco_2024", "change", "eco_"), how="outer")
    dom = e.groupby(["cell", "eco_id"])["n_2024"].sum().reset_index().sort_values("n_2024").drop_duplicates("cell", keep="last")
    t5 = t5.join(dom.set_index("cell")["eco_id"])
    eco = pd.read_csv(ECO_CSV)
    allrow = eco[eco["peer_cls"] == "all"].set_index("eco_id")
    t5["eco_scale_c_change"] = t5["eco_id"].map(allrow["scale_c_change"])
    t5["eco_plain_change_pct"] = t5["eco_id"].map(allrow["plain_change_pct"])
    t5["eco_trend"] = trend(t5["eco_scale_c_change"].values)
    t5["area_decision"] = t5["area_decision"].fillna("none")
    t5["pasture_only"] = t5["pasture_only"].fillna(False).astype(bool)
    t5.index.name = "cell"
    t5.reset_index().to_parquet(os.path.join(OUT, "area_cells_r5.parquet"), index=False)

    t6 = area_table(6)
    t6 = t6[t6["n_fields"].fillna(0) > 0]
    cells6 = t6.index.values.astype(np.int64)
    par = np.array([h3.str_to_int(h3.cell_to_parent(h3.int_to_str(int(c)), 5)) for c in cells6], dtype=np.int64)
    own = t6["area_decision"].values != "none"
    out = pd.DataFrame({"cell": cells6, "parent": par, "area_level": np.where(own, 6, 5).astype(np.int8)})
    p5 = t5.reindex(par)
    for c in ("crops_level", "pasture_level", "crops_change", "pasture_change", "mosaic_level", "mosaic_change",
              "crops_n", "pasture_n", "area_score"):
        out[c] = np.where(own, t6[c].values, p5[c].values)
    out["area_decision"] = np.where(own, t6["area_decision"].values, p5["area_decision"].fillna("none").values)
    out["pasture_only"] = np.where(own, t6["pasture_only"].values, p5["pasture_only"].fillna(False).values).astype(bool)
    for c in ("nat_change", "nat_pct_change"):
        out[c] = np.where(np.isfinite(t6[c].values), t6[c].values, p5[c].values)
    for c in ("eco_crops_level", "eco_pasture_level", "eco_crops_change", "eco_pasture_change", "eco_id",
              "eco_scale_c_change", "eco_plain_change_pct", "eco_trend"):
        out[c] = p5[c].values
    out["n_fields"] = t6["n_fields"].values.astype(np.int32)
    out.to_parquet(os.path.join(OUT, "area_cells.parquet"), index=False)
    csv = out.copy()
    csv.insert(0, "h3_6", [h3.int_to_str(int(x)) for x in csv["cell"]])
    csv["h3_5"] = [h3.int_to_str(int(x)) for x in csv["parent"]]
    csv.drop(columns=["cell", "parent"]).to_csv(os.path.join(C.SUMMARIES, "area_cells.csv.gz"), index=False, float_format="%.3f")
    vc = out["area_decision"].value_counts()
    fv = out.groupby("area_decision")["n_fields"].sum()
    log(step="area", r6_cells=int(len(out)), own_r6=int(own.sum()), from_r5=int((~own).sum()),
        fields_own_r6=int(out.loc[own, "n_fields"].sum()), fields_from_r5=int(out.loc[~own, "n_fields"].sum()),
        cells={k: int(vc.get(k, 0)) for k in AREA}, fields={k: int(fv.get(k, 0)) for k in AREA},
        pasture_only_declining_cells=int((out["pasture_only"] & (out["area_decision"] == "area_declining")).sum()),
        r5_cells=t5["area_decision"].value_counts().to_dict(), seconds=round(time.time() - t0))
    return out


def area_lookup():
    a = pd.read_parquet(os.path.join(OUT, "area_cells.parquet")).set_index("cell")
    a5 = pd.read_parquet(os.path.join(OUT, "area_cells_r5.parquet")).set_index("cell")
    return a, a5


def map_area(cell6, cell5, a, a5):
    """Area call, level and pasture_only per field from its resolution 6 cell; the resolution 5 table
    for a cell absent at resolution 6 (a 2020 outline whose cell holds no 2024 field)."""
    call = pd.Series(cell6).map(a["area_decision"]).values.astype(object)
    lvl = pd.Series(cell6).map(a["area_level"]).values.astype(float)
    po = pd.Series(cell6).map(a["pasture_only"]).values.astype(object)
    miss = pd.isna(call)
    if miss.any():
        call[miss] = pd.Series(cell5[miss]).map(a5["area_decision"]).fillna("none").values
        lvl[miss] = 5
        po[miss] = pd.Series(cell5[miss]).map(a5["pasture_only"]).fillna(False).values
    return call, np.nan_to_num(lvl, nan=5).astype(np.int8), pd.Series(po).fillna(False).values.astype(bool)


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
                                  "share_below": round(float((lv < -LEVEL_T).mean()), 4),
                                  "share_declining": round(float((ch < -CHANGE_T).mean()), 4),
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


def field_call(cc, dec_v1, r24, r_eco24, crop24, area, pasture_only, biome, native_large, regrow_in, conf_low):
    """Returns (decision, decision_computed): the second is the call before the low-confidence rule."""
    n = len(cc)
    out = np.full(n, "none", dtype=object)
    level_below = r24 < -FIELD_LEVEL
    level_above = r24 > FIELD_LEVEL
    has24 = np.isfinite(r24)
    same = np.isin(cc, ["large_decline", "decline", "stable", "gain", "large_gain"])
    declining = np.isin(cc, ["large_decline", "decline"])
    gaining = np.isin(cc, ["gain", "large_gain"])
    # same crop
    out[same & ~declining & ~level_below & ~level_above] = "intensify"
    out[same & ~declining & level_above] = "keep"
    out[same & (declining | level_below)] = "improve_yields"
    # below same-crop neighbors and not gaining: restore candidate next to native vegetation,
    # else improve yields, which spares land elsewhere (14 November 2026)
    bt = same & level_below & ~gaining & np.isfinite(native_large)
    out[bt & (native_large >= NATIVE_T)] = "restore_candidate"
    out[bt & (native_large < NATIVE_T)] = "improve_spare"
    # switched
    sw = cc == "crop_switched"
    out[sw & has24 & ~level_below] = "switch_paid_off"
    out[sw & has24 & level_below] = "switch_failed"
    # area tier: pasture in good land underused; inside the Amazon biome conversion is suggested
    # only for productive pasture (at or above its cell peers), and only of land already cleared
    gp = (same | (sw & has24)) & (area == "good_land_underused") & (crop24 == PASTURE)
    amazon = biome == AMAZON
    out[gp & ~amazon & ~level_above] = "convert_pasture"
    out[gp & amazon & ~level_below] = "convert_cropland"
    out[gp & amazon & level_below] = "improve_pasture"
    out[(same | (sw & has24)) & (area == "restore_area")] = "restore"
    # declining fields in a declining pasture-only area (14 November 2026)
    out[same & declining & (area == "area_declining") & pasture_only] = "restore"
    # native vegetation already returning inside a field below its neighbors and declining, or a
    # restore field: assisted natural regeneration instead of active restoration (14 November 2026)
    regrowing = np.nan_to_num(regrow_in, nan=0.0) >= REGROWTH_T
    out[regrowing & ((same & level_below & declining) | (out == "restore"))] = "assisted_regen"
    # recently converted, against ecoregion peers; no 2024 measurement means no data
    nc = cc == "newly_cropped"
    out[nc] = "converted_ok"
    out[nc & (r_eco24 < -FIELD_LEVEL)] = "converted_below"
    out[nc & ~np.isfinite(r_eco24)] = "none"
    # bare-soil rule of version 1
    out[dec_v1 == "abandon"] = "abandon"
    computed = out.copy()
    out[conf_low & (out != "none")] = "low_confidence"
    return out, computed


def fields_state(state, a, a5, eco_cls):
    t0 = time.time()
    src = source_of(state)
    p = os.path.join(C.ANALYSIS, "year=2024", f"state={state}", "fields_scored.parquet")
    tab = pq.read_table(p)
    df_cols = tab.schema.names
    if "source" in df_cols:
        live = set(tab.column("source").to_pandas().astype(str).unique())
        assert live == {src}, f"{state}: live table source {live} differs from sources.json ({src})"
    dec_v1 = (tab.column("decision_v1") if "decision_v1" in df_cols else tab.column("decision")).to_pandas().astype(str).values
    cc = tab.column("change_class").to_pandas().astype(str).values
    r24 = tab.column("r_adj_2024").to_numpy(zero_copy_only=False).astype(np.float32)
    crop24 = tab.column("crop_2024").to_numpy(zero_copy_only=False).astype(np.int16)
    conf_low = tab.column("confidence").to_pandas().astype(str).values == "low"
    fid = tab.column("fid").to_numpy()
    m = read(C.metrics_path(SOURCE, 2024, 2024, state), ["fid", "h3_5", "h3_6"])
    e = read(os.path.join(ECO, "fields", f"{state}.parquet"), ["fid", "eco_id", "peer_cls_2024", "r_eco_2024"])
    assert np.array_equal(m["fid"].values, fid) and np.array_equal(e["fid"].values, fid), "fid order differs"
    cell = m["h3_5"].values.astype(np.int64)
    cell6 = m["h3_6"].values.astype(np.int64)
    area, area_level, pasture_only = map_area(cell6, cell, a, a5)
    r_eco24 = e["r_eco_2024"].values.astype(np.float32)
    if src == "s2":
        t2 = s2_table(state, ["fid", "r_eco_2024"])
        assert np.array_equal(t2["fid"].values, fid), "s2 table order differs"
        r_eco24 = t2["r_eco_2024"].values.astype(np.float32)
    peer24 = e["peer_cls_2024"].values.astype(np.int64)
    bio = load_biome(state, fid)
    nat = load_native(state, fid)
    n1 = nat["native_share_1km"].values.astype(np.float32)
    dec, dec_c = field_call(cc, dec_v1, r24, r_eco24, crop24, area, pasture_only, bio,
                            nat["native_share_1km_large"].values.astype(np.float32),
                            nat["regrowth_share_in"].values.astype(np.float32), conf_low)
    sc = eco_cls.reindex(pd.MultiIndex.from_arrays([e["eco_id"].values.astype(np.int64), peer24])).values
    tr = trend(sc)
    drop = ("decision", "decision_v1", "decision_computed", "area_decision", "area_level", "eco_id", "eco_trend",
            "biome", "source") + tuple(NATIVE_COLS)
    keep = [c for c in df_cols if c not in drop]
    cols = {}
    for c in keep:
        cols[c] = tab.column(c)
        if c == "change_class":
            cols["decision"] = pa.array(pd.Categorical(dec, categories=DECISIONS))
            cols["decision_computed"] = pa.array(pd.Categorical(dec_c, categories=DECISIONS))
            cols["area_decision"] = pa.array(pd.Categorical(area, categories=AREA))
            cols["area_level"] = pa.array(area_level)
            cols["decision_v1"] = pa.array(pd.Categorical(dec_v1, categories=DECISIONS_V1))
            cols["eco_id"] = pa.array(e["eco_id"].values.astype(np.int32))
            cols["eco_trend"] = pa.array(pd.Categorical(tr, categories=TRENDS))
            cols["biome"] = pa.array(bio)
            cols["source"] = pa.array(pd.Categorical([src] * len(fid), categories=SOURCES))
            for k in NATIVE_COLS:
                cols[k] = pa.array(np.round(nat[k].values, 3 if k != "largest_patch_ha_1km" else 0).astype(np.float32))
    out = pa.table(cols)
    meta = dict(tab.schema.metadata or {})
    meta[b"s07_decisions"] = json.dumps({"state": state, "source": src, "level_t": LEVEL_T, "change_t": CHANGE_T, "eco_t": ECO_T,
                                         "area_resolution": 6, "pasture_only_crop_share": PASTURE_ONLY_CROP_SHARE,
                                         "native_t": NATIVE_T, "written": datetime.now().isoformat(timespec="seconds")}).encode()
    out = out.replace_schema_metadata(meta)
    pq.write_table(out, p + ".part", compression="zstd", row_group_size=100_000)
    del tab, out, cols
    os.replace(p + ".part", p)

    # abandoned 2020 outlines
    ab_p = os.path.join(C.ANALYSIS, "abandoned", f"state={state}.parquet")
    ab_area = {}
    if os.path.exists(ab_p):
        at = pq.read_table(ab_p)
        afid = at.column("fid").to_numpy()
        m20 = read(C.metrics_path(SOURCE, 2020, 2020, state), ["fid", "h3_5", "h3_6"]).set_index("fid")
        e20 = read(os.path.join(C.ANALYSIS, "weather_refit", "field_eco_2020", f"{state}.parquet"), ["fid", "eco_id"]).set_index("fid")
        acell = m20["h3_5"].reindex(afid).fillna(0).values.astype(np.int64)
        acell6 = m20["h3_6"].reindex(afid).fillna(0).values.astype(np.int64)
        aarea, alevel, _ = map_area(acell6, acell, a, a5)
        asrc = (at.column("source").to_pandas().astype(str).values if "source" in at.schema.names
                else np.array(["modis"] * len(afid), dtype=object))
        aeco = e20["eco_id"].reindex(afid).fillna(0).values.astype(np.int32)
        acrop20 = at.column("crop_2020").to_numpy(zero_copy_only=False).astype(np.int64)
        apeer = np.where(acrop20 == 41, 19, acrop20)
        atr = trend(eco_cls.reindex(pd.MultiIndex.from_arrays([aeco.astype(np.int64), apeer])).values)
        akeep = [c for c in at.schema.names if c not in drop]
        av1 = (at.column("decision_v1") if "decision_v1" in at.schema.names else at.column("decision")).to_pandas().astype(str).values
        acols = {}
        for c in akeep:
            acols[c] = at.column(c)
            if c == "change_class":
                acols["decision"] = pa.array(pd.Categorical(["abandoned_outline"] * len(afid), categories=DECISIONS))
                acols["area_decision"] = pa.array(pd.Categorical(aarea, categories=AREA))
                acols["area_level"] = pa.array(alevel)
                acols["decision_v1"] = pa.array(pd.Categorical(av1, categories=DECISIONS_V1))
                acols["eco_id"] = pa.array(aeco)
                acols["eco_trend"] = pa.array(pd.Categorical(atr, categories=TRENDS))
                acols["source"] = pa.array(pd.Categorical(asrc, categories=SOURCES))
        aout = pa.table(acols).replace_schema_metadata(at.schema.metadata)
        pq.write_table(aout, ab_p + ".part", compression="zstd", row_group_size=100_000)
        os.replace(ab_p + ".part", ab_p)
        ab_area = {k: int(v) for k, v in pd.Series(aarea).value_counts().items()}

    cp = os.path.join(os.path.dirname(p), "counts.json")
    with open(cp) as fh:
        counts = json.load(fh)
    counts["decision"] = {k: int(v) for k, v in pd.Series(dec).value_counts().items()}
    counts["decision_computed"] = {k: int(v) for k, v in pd.Series(dec_c).value_counts().items()}
    counts["decision_v1"] = {k: int(v) for k, v in pd.Series(dec_v1).value_counts().items()}
    counts["area_decision"] = {k: int(v) for k, v in pd.Series(area).value_counts().items()}
    counts["area_decision_abandoned"] = ab_area
    counts["area_level"] = {str(int(k)): int(v) for k, v in pd.Series(area_level).value_counts().items()}
    counts["eco_trend"] = {k: int(v) for k, v in pd.Series(tr).value_counts().items()}
    counts["source"] = src
    with open(cp, "w") as fh:
        json.dump(counts, fh, indent=1)
    slim = pd.DataFrame({"fid": fid, "state": state, "cell": cell, "cell6": cell6, "eco_id": e["eco_id"].values.astype(np.int32),
                         "decision": dec, "decision_computed": dec_c, "decision_v1": dec_v1, "area_decision": area,
                         "area_level": area_level, "pasture_only": pasture_only, "change_class": cc, "crop_2024": crop24,
                         "biome": bio, "source": src, "confidence_low": conf_low, "r_eco_nan": ~np.isfinite(r_eco24),
                         "r_adj_2024": r24, **{k: nat[k].values for k in NATIVE_COLS}})
    os.makedirs(os.path.join(OUT, "fields"), exist_ok=True)
    slim.to_parquet(os.path.join(OUT, "fields", f"{state}.parquet"), index=False)
    return {"state": state, "source": src, "rows": int(len(fid)), "low_confidence": int((dec == "low_confidence").sum()),
            "abandoned": int(sum(ab_area.values())), "seconds": round(time.time() - t0, 1)}


def fields(states):
    a, a5 = area_lookup()
    eco_cls = eco_lookup()
    for s in states:
        log(step="fields", **fields_state(s, a, a5, eco_cls))


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
    nat["decision_computed"] = df["decision_computed"].value_counts().reindex(DECISIONS, fill_value=0).to_dict()
    nat["area_level_cells"] = {str(int(k)): int(v) for k, v in cells["area_level"].value_counts().items()}
    nat["area_level_fields"] = {str(int(k)): int(v) for k, v in df["area_level"].value_counts().items()}
    nat["source_fields"] = {str(k): int(v) for k, v in df["source"].value_counts().items()}
    nat["recently_converted_unmeasured_to_none"] = int(((df["change_class"] == "newly_cropped") & df["r_eco_nan"]).sum())
    po = (df["decision_computed"] == "restore") & (df["area_decision"] == "area_declining")
    nat["restore_pasture_only_declining_computed"] = int(po.sum())
    nat["restore_pasture_only_declining_shown"] = int((po & (df["decision"] == "restore")).sum())
    amz = df["biome"] == AMAZON
    nat["amazon"] = {"fields": int(amz.sum()),
                     "decision_computed": df.loc[amz, "decision_computed"].value_counts().reindex(DECISIONS, fill_value=0).to_dict(),
                     "decision": df.loc[amz, "decision"].value_counts().reindex(DECISIONS, fill_value=0).to_dict()}
    nat["biome_fields"] = {str(int(k)): int(v) for k, v in df["biome"].value_counts().items()}
    nat["low_confidence_by_state"] = df[df["decision"] == "low_confidence"]["uf"].value_counts().to_dict()
    bt = df["decision_computed"].isin(["restore_candidate", "improve_spare"])
    nat["below_not_gaining"] = {"fields": int(bt.sum()),
                                "native_1km_large_q": {str(q): round(float(df.loc[bt, "native_share_1km_large"].quantile(q)), 4) for q in (0.25, 0.5, 0.75, 0.9)},
                                "all_fields_native_1km_large_q": {str(q): round(float(df["native_share_1km_large"].quantile(q)), 4) for q in (0.25, 0.5, 0.75, 0.9)}}
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
                              "decision_computed": fr["decision_computed"].value_counts().reindex(DECISIONS, fill_value=0).to_dict(),
                              "restore_pasture_only_declining_computed": int(((fr["decision_computed"] == "restore") & (fr["area_decision"] == "area_declining")).sum()),
                              "restore_pasture_only_declining_shown": int(((fr["decision"] == "restore") & (fr["area_decision"] == "area_declining")).sum()),
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
    ap.add_argument("step", choices=["biome", "native", "national", "dist", "area", "fields", "report", "lookup", "all"])
    ap.add_argument("--states", nargs="*", default=None)
    args = ap.parse_args()
    states = args.states or C.state_dirs(2024)
    have = lambda sub: all(os.path.exists(os.path.join(OUT, sub, f"{s}.parquet")) for s in states)  # noqa: E731
    if args.step == "biome" or (args.step == "all" and not have("biome")):
        biome(states)
    if args.step == "native" or (args.step == "all" and not have("native")):
        native(states)
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
