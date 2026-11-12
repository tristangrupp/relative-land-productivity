"""Stage 3g worker: exactextract coverage weights for one extraction tile.

For a tile of the grid in F:\\relative-land-productivity-data\\grid\\grid.json (1024 x 1024
pixels, EPSG:4326, tile ids r<row>_c<col>) this module loads every prepared field of 2020 and
2024 whose bounding box touches the tile, for every state the tile index lists for that tile,
and computes the exactextract coverage fraction of each field in each of the 1,048,576 cells.
The result is one sparse matrix per tile, fields x cells, saved as

  F:\\relative-land-productivity-data\\weights\\s2\\<tile_id>.npz

with the arrays data, indices, indptr, shape (the scipy CSR parts) and, in row order, fid
(int64), year_layer (int16, 2020 or 2024), state (str), mbmode (int16) and area_ha
(float32). Row i of the matrix is field i of those arrays.

The weights do not depend on the imagery, so they are built once and reused for all 24
monthly composites. exactextract runs against an in-memory single-band raster that has the
tile's geotransform, so no raster file is needed.

Environment: this module needs exactextract, which only the wci_tools venv has:
  "E:\\Water\\water intelligence\\wci_tools\\.venv\\Scripts\\python.exe"
s03g_s2_fetch_reduce.py (ftwtools env) calls it as a subprocess for any tile whose weights
file is missing. It can also prebuild a state or tier ahead of the fetch:

  python s03g_weights.py build r64_c66 [r64_c67 ...]
  python s03g_weights.py state Mato_Grosso [--procs 4]
  python s03g_weights.py tier 1 [--procs 4]
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import time

import numpy as np

DATA = r"F:\relative-land-productivity-data"
GRID_JSON = os.path.join(DATA, "grid", "grid.json")
TILES_PARQUET = os.path.join(DATA, "grid", "tiles.parquet")
FIELDS_DIR = os.path.join(DATA, "fields")
WEIGHTS_DIR = os.path.join(DATA, "weights", "s2")
YEARS = (2020, 2024)
TILE = 1024
TIER_STATES = {
    1: ["Mato_Grosso", "Para", "Rondonia", "Acre", "Amazonas", "Roraima", "Amapa"],
    2: ["Mato_Grosso_Do_Sul", "Goias", "Tocantins", "Maranhao"],
}


def load_grid():
    with open(GRID_JSON) as fh:
        g = json.load(fh)
    assert g["tile_size_px"] == TILE
    return {"pixel": g["pixel_size_deg"], "x0": g["origin"][0], "y0": g["origin"][1],
            "tile_deg": g["tile_size_px"] * g["pixel_size_deg"]}


def parse_tile_id(tile_id):
    r, c = tile_id.split("_")
    return int(r[1:]), int(c[1:])


def tile_bounds(tile_id, grid=None):
    """(xmin, ymin, xmax, ymax) in degrees."""
    grid = grid or load_grid()
    r, c = parse_tile_id(tile_id)
    xmin = grid["x0"] + c * grid["tile_deg"]
    ymax = grid["y0"] - r * grid["tile_deg"]
    return (xmin, ymax - grid["tile_deg"], xmin + grid["tile_deg"], ymax)


def tile_transform(tile_id, grid=None):
    from rasterio.transform import Affine
    grid = grid or load_grid()
    xmin, _, _, ymax = tile_bounds(tile_id, grid)
    return Affine(grid["pixel"], 0, xmin, 0, -grid["pixel"], ymax)


def tile_states(tile_ids):
    """tile_id -> list of states, from the tile index."""
    import pyarrow.parquet as pq
    t = pq.read_table(TILES_PARQUET, columns=["tile_id", "states"]).to_pandas()
    t = t[t["tile_id"].isin(set(tile_ids))]
    return {tid: list(st) for tid, st in zip(t["tile_id"], t["states"])}


def tiles_for_states(states):
    """Tiles that hold fields of any of the states, ordered by field count descending."""
    import pyarrow.parquet as pq
    t = pq.read_table(TILES_PARQUET, columns=["tile_id", "states", "n_fields_2020", "n_fields_2024"]).to_pandas()
    want = set(states)
    t = t[t["states"].apply(lambda s: bool(want & set(s)))].copy()
    t["n"] = t["n_fields_2020"] + t["n_fields_2024"]
    return t.sort_values("n", ascending=False)["tile_id"].tolist()


def weights_path(tile_id):
    return os.path.join(WEIGHTS_DIR, f"{tile_id}.npz")


def load_fields(tile_id, states, grid):
    """GeoDataFrame of both years' fields of the given states touching the tile."""
    import geopandas as gpd
    import pandas as pd
    b = tile_bounds(tile_id, grid)
    parts = []
    for state in states:
        for year in YEARS:
            p = os.path.join(FIELDS_DIR, f"year={year}", f"state={state}", "fields.parquet")
            if not os.path.exists(p):
                continue
            gdf = gpd.read_parquet(p, columns=["fid", "mbmode", "area_ha", "geometry"], bbox=b)
            if len(gdf) == 0:
                continue
            gdf["year_layer"] = np.int16(year)
            gdf["state"] = state
            parts.append(gdf)
    if not parts:
        return None
    return pd.concat(parts, ignore_index=True)


def build(tile_id, force=False, grid=None):
    """Build and save the weights of one tile. Returns a small record."""
    import rasterio
    import scipy.sparse as sp
    from exactextract import exact_extract
    from rasterio.io import MemoryFile

    out = weights_path(tile_id)
    if os.path.exists(out) and not force:
        return {"tile": tile_id, "status": "exists"}
    t0 = time.time()
    grid = grid or load_grid()
    states = tile_states([tile_id]).get(tile_id, [])
    gdf = load_fields(tile_id, states, grid)
    ncell = TILE * TILE
    if gdf is None or len(gdf) == 0:
        W = sp.csr_matrix((0, ncell))
        meta = {"fid": np.zeros(0, np.int64), "year_layer": np.zeros(0, np.int16),
                "state": np.array([], dtype="U32"), "mbmode": np.zeros(0, np.int16),
                "area_ha": np.zeros(0, np.float32)}
    else:
        tr = tile_transform(tile_id, grid)
        with MemoryFile() as mf:
            with mf.open(driver="GTiff", width=TILE, height=TILE, count=1, dtype="uint8",
                         crs="EPSG:4326", transform=tr) as ds:
                ds.write(np.zeros((1, TILE, TILE), dtype="uint8"))
            with mf.open() as ds:
                res = exact_extract(ds, gdf[["geometry"]], ["cell_id", "coverage"],
                                    output="pandas", progress=False)
        rows, cols, vals = [], [], []
        for i, (cid, cov) in enumerate(zip(res["cell_id"], res["coverage"])):
            cid = np.asarray(cid, dtype=np.int64)
            if cid.size == 0:
                continue
            rows.append(np.full(cid.size, i, dtype=np.int64))
            cols.append(cid)
            vals.append(np.asarray(cov, dtype=np.float64))
        if rows:
            W = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                              shape=(len(gdf), ncell))
        else:
            W = sp.csr_matrix((len(gdf), ncell))
        meta = {"fid": gdf["fid"].values.astype(np.int64),
                "year_layer": gdf["year_layer"].values.astype(np.int16),
                "state": gdf["state"].values.astype("U32"),
                "mbmode": gdf["mbmode"].values.astype(np.int16),
                "area_ha": gdf["area_ha"].values.astype(np.float32)}
    os.makedirs(WEIGHTS_DIR, exist_ok=True)
    tmp = out[:-4] + f".part{os.getpid()}.npz"
    np.savez_compressed(tmp, data=W.data.astype(np.float32), indices=W.indices.astype(np.int32),
                        indptr=W.indptr.astype(np.int64), shape=np.array(W.shape, dtype=np.int64),
                        **meta)
    os.replace(tmp, out)
    return {"tile": tile_id, "status": "ok", "fields": int(W.shape[0]), "nnz": int(W.nnz),
            "states": states, "seconds": round(time.time() - t0, 1)}


def load_weights(tile_id):
    """(W as scipy CSR float64, dict of the row arrays). Raises FileNotFoundError."""
    import scipy.sparse as sp
    z = np.load(weights_path(tile_id), allow_pickle=False)
    shape = tuple(int(v) for v in z["shape"])
    W = sp.csr_matrix((z["data"].astype(np.float64), z["indices"], z["indptr"]), shape=shape)
    meta = {k: z[k] for k in ("fid", "year_layer", "state", "mbmode", "area_ha")}
    return W, meta


def _build_one(args):
    tile_id, force = args
    try:
        return build(tile_id, force)
    except Exception as ex:  # noqa: BLE001
        return {"tile": tile_id, "status": "fail", "error": str(ex)[:300]}


def build_many(tile_ids, procs=4, force=False):
    t0 = time.time()
    todo = [t for t in tile_ids if force or not os.path.exists(weights_path(t))]
    print(f"{len(tile_ids)} tiles, {len(todo)} to build, {procs} processes", flush=True)
    n_ok = n_fail = 0
    with cf.ProcessPoolExecutor(procs) as ex:
        for rec in ex.map(_build_one, [(t, force) for t in todo]):
            if rec["status"] == "ok":
                n_ok += 1
            elif rec["status"] == "fail":
                n_fail += 1
            print(rec, flush=True)
    print(f"built {n_ok}, failed {n_fail}, {time.time() - t0:.0f} s", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "state", "tier"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.cmd == "build":
        for tid in a.args:
            print(json.dumps(build(tid, a.force)), flush=True)
    elif a.cmd == "state":
        build_many(tiles_for_states(a.args), a.procs, a.force)
    else:
        states = []
        for t in a.args:
            states += TIER_STATES[int(t)]
        build_many(tiles_for_states(states), a.procs, a.force)


if __name__ == "__main__":
    main()
