"""Probe step 2: coverage weights and sparse reduction on one downloaded NDVI tile.

Reads the Planetary Computer tile pair written by s03_ndvi_tiles.py: <period>.tif (int16,
ndvi_med and ndvi_max) and <period>_count.tif (uint8, n_clear).

Builds exactextract coverage weights (cell index plus coverage fraction) for every field
inside the Sorriso tile, stores them as a sparse matrix, reduces the tile's three bands to
per-field coverage-weighted means with a sparse matrix product, and checks the product
against exactextract's own mean on 20 random fields. No Earth Engine calls.

Fields come from the fields agent's layer when it exists, else straight from the seamfix
parquet with a bbox filter on geom_bbox.

Usage:  python s03_probe_reduce.py [tile.tif]
"""
import json
import os
import sys
import time

import duckdb
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import scipy.sparse as sp
import shapely
from exactextract import exact_extract

DATA = r"F:\relative-land-productivity-data"
PROBE = os.path.join(DATA, "probe")
FIELDS_AGENT = os.path.join(DATA, "fields", "year=2024", "state=Mato_Grosso", "fields.parquet")
SEAMFIX = r"E:\trazo4_master_parquet_seamfix\country=Brazil\state=Mato_Grosso\year=2024\part-0.parquet"
NODATA = -32768
AG = [39, 15, 19, 41, 20, 40, 62, 21, 18, 46, 47, 48, 35, 9]


def load_fields(bounds):
    x0, y0, x1, y1 = bounds
    if os.path.exists(FIELDS_AGENT):
        # the fields agent's GeoParquet 1.1 layer: columns bbox (struct) and geometry (WKB)
        gdf = gpd.read_parquet(FIELDS_AGENT, columns=["fid", "area_ha", "mbmode", "crop_group", "geometry"],
                               bbox=(x0, y0, x1, y1))
        gdf = gdf[gdf["mbmode"].isin(AG)].reset_index(drop=True)
        gdf["geometry"] = shapely.make_valid(gdf.geometry.values)
        gdf = gdf[~gdf.geometry.is_empty].reset_index(drop=True)
        return gdf, FIELDS_AGENT
    src = SEAMFIX
    con = duckdb.connect()
    q = f"""
    SELECT fid, area_ha, mbmode, geom FROM read_parquet('{src}', hive_partitioning=false)
    WHERE geom_bbox.xmin < {x1} AND geom_bbox.xmax > {x0}
      AND geom_bbox.ymin < {y1} AND geom_bbox.ymax > {y0}
      AND mbmode IN ({",".join(map(str, AG))})
    """
    df = con.execute(q).df()
    geoms = shapely.from_wkb([bytes(b) for b in df["geom"].values])
    geoms = shapely.make_valid(geoms)
    gdf = gpd.GeoDataFrame(df.drop(columns="geom"), geometry=geoms, crs="EPSG:4326")
    # keep polygonal parts only (make_valid can return collections with lines)
    gdf["geometry"] = [shapely.ops.unary_union([g for g in getattr(geom, "geoms", [geom])
                                                if g.geom_type in ("Polygon", "MultiPolygon")])
                       if geom.geom_type == "GeometryCollection" else geom for geom in gdf.geometry]
    gdf = gdf[~gdf.geometry.is_empty].reset_index(drop=True)
    return gdf, src


def build_weights(tif, gdf):
    """CSR matrix (fields x cells) of coverage fractions, cells in row-major raster order."""
    t0 = time.time()
    with rasterio.open(tif) as src:
        ncell = src.width * src.height
    res = exact_extract(tif, gdf, ["cell_id", "coverage"], output="pandas", progress=False)
    # a 3-band raster gives band_1_cell_id, band_1_coverage, ...; the grid is the same for all
    cid_col = [c for c in res.columns if c.endswith("cell_id")][0]
    cov_col = [c for c in res.columns if c.endswith("coverage")][0]
    rows, cols, vals = [], [], []
    for i, (cid, cov) in enumerate(zip(res[cid_col], res[cov_col])):
        cid = np.asarray(cid, dtype=np.int64)
        cov = np.asarray(cov, dtype=np.float64)
        rows.append(np.full(cid.size, i, dtype=np.int64))
        cols.append(cid)
        vals.append(cov)
    W = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                      shape=(len(gdf), ncell))
    return W, time.time() - t0


def count_path(tif):
    return tif[:-4] + "_count.tif"


def reduce_tile(tif, W):
    """Per-field coverage-weighted mean of ndvi_med, ndvi_max (as NDVI) and n_clear."""
    t0 = time.time()
    with rasterio.open(tif) as src:
        a = src.read()
    with rasterio.open(count_path(tif)) as src:
        a = np.concatenate([a, src.read().astype("int16")])
    out = {}
    for b, name in enumerate(["ndvi_med", "ndvi_max"]):
        v = a[b].reshape(-1).astype(np.float64)
        valid = (v != NODATA).astype(np.float64)
        num = W @ (np.where(valid > 0, v, 0.0) / 10000.0)
        den = W @ valid
        with np.errstate(invalid="ignore", divide="ignore"):
            out[name] = np.where(den > 0, num / den, np.nan)
        out[name + "_valid_frac"] = den / np.asarray(W.sum(axis=1)).ravel()
    n = a[2].reshape(-1).astype(np.float64)
    out["n_clear"] = (W @ n) / np.asarray(W.sum(axis=1)).ravel()
    return pd.DataFrame(out), time.time() - t0


def check(tif, gdf, red, k=20, seed=0):
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(gdf), size=k, replace=False)
    sub = gdf.iloc[idx]
    with rasterio.open(tif) as src:
        pass
    ref = exact_extract(tif, sub, ["mean"], output="pandas", progress=False)
    refn = exact_extract(count_path(tif), sub, ["mean"], output="pandas", progress=False)
    # exactextract returns one column per band: band_1_mean, band_2_mean
    cols = [c for c in ref.columns if c.endswith("_mean")]
    d_med = np.abs(ref[cols[0]].values / 10000.0 - red["ndvi_med"].values[idx])
    d_max = np.abs(ref[cols[1]].values / 10000.0 - red["ndvi_max"].values[idx])
    d_n = np.abs(refn["mean"].values - red["n_clear"].values[idx])
    return {"fields_checked": int(k), "max_abs_diff_ndvi_med": float(np.nanmax(d_med)),
            "max_abs_diff_ndvi_max": float(np.nanmax(d_max)),
            "max_abs_diff_n_clear": float(np.nanmax(d_n)),
            "all_within_1e-6": bool(np.nanmax(d_med) < 1e-6 and np.nanmax(d_max) < 1e-6 and np.nanmax(d_n) < 1e-6),
            "ref_columns": cols}


def main():
    tif = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DATA, "raw", "s2", "r64_c66", "2024-01m.tif")
    with rasterio.open(tif) as src:
        bounds = tuple(src.bounds)
        shape = (src.height, src.width)
    t0 = time.time()
    gdf, src_path = load_fields(bounds)
    t_load = time.time() - t0
    print(f"{len(gdf)} agricultural fields touch the tile, loaded from {src_path} in {t_load:.1f} s", flush=True)
    W, t_w = build_weights(tif, gdf)
    print(f"weights: {W.shape}, {W.nnz} nonzeros, {t_w:.1f} s", flush=True)
    tag = os.path.splitext(os.path.basename(tif))[0]
    tile = os.path.basename(os.path.dirname(tif))
    sp.save_npz(os.path.join(PROBE, f"weights_{tile}.npz"), W)
    gdf.drop(columns="geometry").assign(row=np.arange(len(gdf))).to_parquet(
        os.path.join(PROBE, f"weights_{tile}_fields.parquet"))
    red, t_r = reduce_tile(tif, W)
    print(f"reduction of 3 bands: {t_r:.3f} s", flush=True)
    red.insert(0, "fid", gdf["fid"].values)
    red.to_parquet(os.path.join(PROBE, f"reduced_{tile}_{tag}.parquet"))
    chk = check(tif, gdf, red)
    print("check vs exactextract mean:", chk, flush=True)
    summary = {
        "tile": tif, "tile_shape": shape, "fields": int(len(gdf)), "fields_source": src_path,
        "seconds_load_fields": round(t_load, 2), "seconds_weights": round(t_w, 2),
        "weights_nnz": int(W.nnz), "seconds_reduce_3_bands": round(t_r, 3),
        "ndvi_med_mean_over_fields": float(np.nanmean(red["ndvi_med"])),
        "fields_with_no_valid_pixel": int(np.isnan(red["ndvi_med"]).sum()),
        "check": chk,
    }
    with open(os.path.join(PROBE, f"reduce_summary_{tile}.json"), "w") as fh:
        json.dump(summary, fh, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
