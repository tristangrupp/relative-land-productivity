"""CAR property parcels and Forest Code legal reserve indicators per field (stage s10).

User decision of 14 November 2026: use the CAR rural property parcels to see whether a field
sits in a property with a Forest Code deficit, so that a restore candidate inside a property
that owes restoration is a stronger case. The output is attributes per field. It is not a
restoration plan and it is not a legal finding. Report: pipeline/CAR_FOREST_CODE.md.

Source: the source.coop cadastral catalog, collection brazil-car-area-imovel (user choice of 14
Nov), downloaded once to raw\\car\\brazil_car_area_imovel.parquet (GeoParquet 1.1, EPSG:4326,
8,453,552 rows, 16 July 2026). The quarantine sidecar of 2 corrupt geometries is not used.

Steps:
  split     one pass over the national file, one parquet per state code (analysis\\car\\raw)
  parcels   per state: dedupe cod_imovel, repair geometry, equal-area area, biome and Legal
            Amazon under the parcel's interior point, legal reserve requirement, MapBiomas 2024
            native share (exactextract), deficit (analysis\\car\\parcels)
  fields    per field state: largest-overlap join of 2024 fields to parcels (analysis\\car)
  summary   data/summaries/car_forest_code_by_state.csv
  all       every step

Privacy: cod_imovel identifies landholders. It is kept only in the local tables under
analysis\\car and never goes into tiles, S3, the repo or the summaries.

Run with E:\\Water\\water intelligence\\wci_tools\\.venv\\Scripts\\python.exe.
"""
import argparse
import gc
import glob
import json
import os
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import shapely
from pyproj import Transformer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s04_common as C  # noqa: E402

DATA = C.DATA
RAW_CAR = os.path.join(DATA, "raw", "car", "brazil_car_area_imovel.parquet")
BIOMES = os.path.join(DATA, "raw", "biomes", "lm_bioma_250.shp")
LEGAL_AMAZON = os.path.join(DATA, "raw", "legal_amazon", "Limites_Amazonia_Legal_2024.shp")
COVERAGE = os.path.join(DATA, "raw", "mapbiomas", "brazil_coverage_2024.tif")
NATIVE90 = os.path.join(DATA, "analysis", "car", "native_2024_90m.tif")  # built by the nativemask step
OUT = os.environ.get("CAR_OUT", os.path.join(C.ANALYSIS, "car"))  # CAR_OUT only for test runs
OUT_RAW = os.path.join(OUT, "raw")
OUT_PARCELS = os.path.join(OUT, "parcels")
SUMMARY_CSV = os.environ.get("CAR_SUMMARY", os.path.join(C.SUMMARIES, "car_forest_code_by_state.csv"))
ECO_FIELDS = os.path.join(C.ANALYSIS, "ecoregions", "fields")

# IBGE Albers equal-area conic for Brazil (SIRGAS 2000 / GRS80). Areas only.
ALBERS = ("+proj=aea +lat_0=-12 +lon_0=-54 +lat_1=-2 +lat_2=-22 +x_0=5000000 +y_0=10000000 "
          "+ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs")
TO_ALBERS = Transformer.from_crs("EPSG:4326", ALBERS, always_xy=True)

NATIVE = [3, 4, 5, 6, 11, 12, 49, 50]  # MapBiomas Collection 10 native vegetation classes
REGISTERED = ("AT", "PE")  # active and pending; CA (canceled) and SU (suspended) reported apart
MIN_OVERLAP = 0.20  # parcels covering under 20 percent of a field are ignored
SMALL_MODULES = 4.0  # Law 12.651/2012 art. 67: properties up to 4 fiscal modules on 22 July 2008
FRONTIER = ["Madeira-Tapajós moist forests", "Xingu-Tocantins-Araguaia moist forests", "Mato Grosso tropical dry forests",
            "Tocantins/Pindare moist forests", "Tapajós-Xingu moist forests", "Purus-Madeira moist forests",
            "Southwest Amazon moist forests"]  # same list as s07_decisions.py


def log(**kw):
    kw["t"] = datetime.now().isoformat(timespec="seconds")
    print(json.dumps(kw, ensure_ascii=False, default=str), flush=True)


def state_uf_map():
    """Field state folder name to two-letter code, read from the fields themselves."""
    m = {}
    for s in C.state_dirs(2024):
        t = pq.read_table(C.fields_path(2024, s), columns=["state_uf"]).slice(0, 1)
        m[s] = t.column("state_uf")[0].as_py()
    return m


def to_albers(geoms):
    return shapely.transform(geoms, lambda xy: np.column_stack(TO_ALBERS.transform(xy[:, 0], xy[:, 1])))


def polygonal(geoms):
    """Repair invalid geometries and keep only their polygon parts."""
    bad = ~shapely.is_valid(geoms)
    if bad.any():
        fixed = shapely.make_valid(geoms[bad])
        out = []
        for g in fixed:
            if g is None:
                out.append(None)
            elif g.geom_type in ("Polygon", "MultiPolygon"):
                out.append(g)
            else:
                parts = [p for p in shapely.get_parts(g) if p.geom_type in ("Polygon", "MultiPolygon")]
                out.append(shapely.union_all(parts) if parts else None)
        geoms = geoms.copy()
        geoms[bad] = np.array(out, dtype=object)
    return geoms, int(bad.sum())


# ---------------------------------------------------------------- split

def step_split():
    os.makedirs(OUT_RAW, exist_ok=True)
    pf = pq.ParquetFile(RAW_CAR)
    cols = ["cod_imovel", "ind_status", "ind_tipo", "des_condic", "mod_fiscal", "num_area", "cod_estado",
            "dat_criaca", "dat_atuali", "bbox", "geometry"]
    writers, counts = {}, {}
    t0 = time.time()
    for rg in range(pf.num_row_groups):
        t = pf.read_row_group(rg, columns=cols)
        st = t.column("cod_estado").to_numpy(zero_copy_only=False)
        for uf in np.unique(st):
            sub = t.filter(pa.array(st == uf))
            if uf not in writers:
                writers[uf] = pq.ParquetWriter(os.path.join(OUT_RAW, f"{uf}.parquet"), sub.schema, compression="zstd")
            writers[uf].write_table(sub)
            counts[uf] = counts.get(uf, 0) + sub.num_rows
        if rg % 20 == 0:
            log(step="split", row_group=rg, of=pf.num_row_groups, s=round(time.time() - t0))
    for w in writers.values():
        w.close()
    log(step="split", done=True, rows=sum(counts.values()), states=counts)


# ---------------------------------------------------------------- parcels

_zones = None


def zones():
    """Biome and Legal Amazon polygons in EPSG:4326 (SIRGAS 2000 and WGS 84 differ by under 1 m here)."""
    global _zones
    if _zones is None:
        import geopandas as gpd
        b = gpd.read_file(BIOMES).to_crs(4326)
        la = gpd.read_file(LEGAL_AMAZON).to_crs(4326)
        _zones = (b, shapely.union_all(la.geometry.values))
        shapely.prepare(_zones[1])
    return _zones


def lr_requirement(biome, in_la):
    """Law 12.651/2012 art. 12, screened by the biome under the property's interior point.

    Inside the Legal Amazon: 80 percent in forest (here: Amazon biome), 35 percent in Cerrado
    (Cerrado biome), 20 percent in general fields (here: any other biome, mainly Pantanal).
    Outside the Legal Amazon: 20 percent.
    """
    req = np.full(len(biome), 0.20)
    req[in_la & (biome == "Amazônia")] = 0.80
    req[in_la & (biome == "Cerrado")] = 0.35
    return req


def step_nativemask(block=3072):
    """Two-band 90 m raster from the 30 m MapBiomas 2024 map: band 1 counts native pixels and
    band 2 counts pixels with data (class not 0) in each 3 by 3 block, 0 to 9. A property-level
    share needs no 30 m detail, and the 90 m raster has 9 times fewer cells for exactextract."""
    import rasterio
    from rasterio.windows import Window
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    lut = np.zeros(256, dtype=np.uint8)
    lut[NATIVE] = 1
    with rasterio.open(COVERAGE) as src:
        H, W = src.height // 3, src.width // 3
        prof = dict(driver="GTiff", width=W, height=H, count=2, dtype="uint8", crs=src.crs,
                    transform=src.transform * src.transform.scale(3, 3), tiled=True, blockxsize=512,
                    blockysize=512, compress="deflate", predictor=2, BIGTIFF="YES")
        tmp = NATIVE90 + ".part"
        with rasterio.open(tmp, "w", **prof) as dst:
            for r0 in range(0, H, block // 3):
                h = min(block // 3, H - r0)
                a = src.read(1, window=Window(0, r0 * 3, W * 3, h * 3))
                nat = lut[a].reshape(h, 3, W, 3).sum(axis=(1, 3), dtype=np.uint8)
                val = (a > 0).reshape(h, 3, W, 3).sum(axis=(1, 3), dtype=np.uint8)
                dst.write(nat, 1, window=Window(0, r0, W, h))
                dst.write(val, 2, window=Window(0, r0, W, h))
                log(step="nativemask", row=r0 + h, of=H, s=round(time.time() - t0))
    os.replace(tmp, NATIVE90)


def native_share(geoms_wgs, ids, uf, chunk=5_000):
    """Share of MapBiomas 2024 native vegetation inside each parcel: coverage-weighted sums of
    the 90 m native and data counts (exactextract), native over data. Parcels go in chunks in
    spatial order (Hilbert-like sort of interior points) with a progress line per chunk."""
    import geopandas as gpd
    from exactextract import exact_extract
    order = np.argsort(shapely.get_x(shapely.centroid(geoms_wgs)).round(1) * 1e4 + shapely.get_y(shapely.centroid(geoms_wgs)))
    nat = np.full(len(ids), np.nan)
    val = np.full(len(ids), np.nan)
    failed = []
    t0 = time.time()

    def run(sel):
        """exactextract on one set of parcels; on an allocation error, split it in halves down to
        single parcels, so one bad geometry costs only its own value (reported in the log)."""
        gdf = gpd.GeoDataFrame({"i": sel}, geometry=geoms_wgs[sel], crs=4326)
        try:
            res = exact_extract(NATIVE90, gdf, ["sum"], include_cols=["i"], output="pandas",
                                max_cells_in_memory=4_000_000)
        except (MemoryError, RuntimeError) as e:
            if len(sel) == 1:
                failed.append(int(sel[0]))
                log(step="native_share", uf=uf, parcel_failed=int(ids[sel[0]]), error=repr(e)[:120])
                return
            h = len(sel) // 2
            run(sel[:h])
            run(sel[h:])
            return
        nat[res["i"].values] = res["band_1_sum"].values
        val[res["i"].values] = res["band_2_sum"].values

    for k in range(0, len(order), chunk):
        run(order[k:k + chunk])
        log(step="native_share", uf=uf, done=min(k + chunk, len(order)), of=len(order), failed=len(failed),
            s=round(time.time() - t0))
    valid_frac = val / 9.0  # mean data count per 90 m cell, 0 to 1 (not used in the share)

    share = np.where(val > 0, nat / np.where(val > 0, val, 1), np.nan)
    return pd.Series(share, index=ids), pd.Series(valid_frac, index=ids)


def step_parcels(uf):
    os.makedirs(OUT_PARCELS, exist_ok=True)
    t0 = time.time()
    t = pq.read_table(os.path.join(OUT_RAW, f"{uf}.parquet"))
    df = t.drop([c for c in ("geometry", "bbox") if c in t.column_names]).to_pandas()
    geoms = shapely.from_wkb(t.column("geometry").to_numpy(zero_copy_only=False))
    n_rows = len(df)
    # Duplicates of cod_imovel: keep the row updated last (dat_atuali), so each property counts once.
    upd = pd.to_datetime(df["dat_atuali"], errors="coerce", format="%d/%m/%Y")
    order = np.lexsort((-np.arange(n_rows), upd.fillna(pd.Timestamp(0)).values.astype("int64")))[::-1]
    keep = ~pd.Series(df["cod_imovel"].values[order]).duplicated().values
    idx = np.sort(order[keep])
    df = df.iloc[idx].reset_index(drop=True)
    geoms = geoms[idx]
    n_dupes = n_rows - len(df)
    geoms, n_repaired = polygonal(geoms)
    # Repeated consecutive vertices made exactextract 0.3 hang forever on some valid parcels
    # (Mato Grosso parcel 77412 of the raw file, 16 Nov 2026); removing them changes no area.
    geoms = shapely.remove_repeated_points(geoms)
    ok = ~(shapely.is_missing(geoms) | shapely.is_empty(geoms))
    df = df[ok].reset_index(drop=True)
    geoms = geoms[ok]
    df["area_ha"] = shapely.area(to_albers(geoms)) / 1e4
    pts = shapely.point_on_surface(geoms)
    b, la = zones()
    log(step="parcels", uf=uf, stage="area and interior points", s=round(time.time() - t0))
    biome = np.full(len(df), None, dtype=object)
    for name, poly in zip(b["Bioma"].values, b.geometry.values):
        shapely.prepare(poly)  # prepared polygons: the biome outlines have hundreds of thousands of vertices
        biome[shapely.contains_xy(poly, shapely.get_x(pts), shapely.get_y(pts)) & (biome == None)] = name  # noqa: E711
    df["biome"] = biome
    df["in_legal_amazon"] = shapely.intersects(la, pts)
    df["lr_required_share"] = lr_requirement(df["biome"].values, df["in_legal_amazon"].values)
    log(step="parcels", uf=uf, rows=n_rows, dupes=n_dupes, repaired=n_repaired, dropped_empty=int((~ok).sum()),
        s=round(time.time() - t0))
    df["pid"] = np.arange(len(df))
    ns, _ = native_share(geoms, df["pid"].values, uf)
    df["native_share_property"] = ns.reindex(df["pid"].values).values
    df["lr_deficit_share"] = df["lr_required_share"] - df["native_share_property"]
    df["lr_deficit_ha"] = df["lr_deficit_share"] * df["area_ha"]
    df["small_property"] = df["mod_fiscal"] <= SMALL_MODULES
    bx = shapely.bounds(geoms)
    df["xmin"], df["ymin"], df["xmax"], df["ymax"] = bx[:, 0], bx[:, 1], bx[:, 2], bx[:, 3]
    df["geometry"] = shapely.to_wkb(geoms)
    df["cod_estado"] = uf
    df.to_parquet(os.path.join(OUT_PARCELS, f"{uf}.parquet"), index=False, compression="zstd")
    log(step="parcels", uf=uf, written=len(df), native_na=int(df["native_share_property"].isna().sum()),
        s=round(time.time() - t0))


# ---------------------------------------------------------------- fields

PARCEL_COLS = ["pid", "cod_estado", "xmin", "ymin", "xmax", "ymax", "cod_imovel", "ind_status", "ind_tipo", "mod_fiscal", "area_ha",
               "biome", "in_legal_amazon", "lr_required_share", "native_share_property", "lr_deficit_share",
               "lr_deficit_ha", "small_property", "geometry"]


def load_parcels(bounds):
    xmin, ymin, xmax, ymax = bounds
    flt = [("xmin", "<=", xmax), ("xmax", ">=", xmin), ("ymin", "<=", ymax), ("ymax", ">=", ymin)]
    parts = []
    for p in sorted(glob.glob(os.path.join(OUT_PARCELS, "*.parquet"))):
        t = pq.read_table(p, columns=PARCEL_COLS, filters=flt)
        if t.num_rows:
            parts.append(t.to_pandas())
    return pd.concat(parts, ignore_index=True)


def join_chunk(fg_alb, f_area, par, pg_alb, tree):
    fi, pj = tree.query(fg_alb, predicate="intersects")
    inter = np.empty(len(fi))
    step = 200_000
    for k in range(0, len(fi), step):
        a = fg_alb[fi[k:k + step]]
        bgeom = pg_alb[pj[k:k + step]]
        try:
            inter[k:k + step] = shapely.area(shapely.intersection(a, bgeom, grid_size=None))
        except shapely.errors.GEOSException:
            for m in range(len(a)):
                try:
                    inter[k + m] = shapely.intersection(a[m], bgeom[m]).area
                except shapely.errors.GEOSException:
                    inter[k + m] = shapely.intersection(shapely.make_valid(a[m]), shapely.make_valid(bgeom[m])).area
    pairs = pd.DataFrame({"fi": fi, "pj": pj, "share": inter / f_area[fi]})
    return pairs[pairs["share"] >= MIN_OVERLAP]


def step_fields(state, chunk=400_000):
    """Fields in strips sorted by longitude, so each strip decodes only the parcels near it.
    Parcel geometries stay as WKB until a strip needs them, which bounds memory on large states."""
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    ft = pq.read_table(C.fields_path(2024, state), columns=["fid", "geometry", "centroid_lon"])
    lon = ft.column("centroid_lon").to_numpy()
    forder = np.argsort(lon, kind="stable")
    fid_all = ft.column("fid").to_numpy()
    fwkb_all = ft.column("geometry").to_numpy(zero_copy_only=False)
    del ft
    meta = pq.read_table(C.fields_path(2024, state), columns=["bbox"]).column("bbox").combine_chunks()
    fb = np.column_stack([meta.field(k).to_numpy() for k in ("xmin", "ymin", "xmax", "ymax")])
    del meta
    par_all = load_parcels((fb[:, 0].min(), fb[:, 1].min(), fb[:, 2].max(), fb[:, 3].max()))
    log(step="fields", state=state, parcels_in_state_box=len(par_all), s=round(time.time() - t0))
    outs = []
    for k in range(0, len(forder), chunk):
        idx = forder[k:k + chunk]
        bx = fb[idx]
        m = ((par_all["xmin"].values <= bx[:, 2].max()) & (par_all["xmax"].values >= bx[:, 0].min())
             & (par_all["ymin"].values <= bx[:, 3].max()) & (par_all["ymax"].values >= bx[:, 1].min()))
        par = par_all[m].reset_index(drop=True)
        pg_alb = to_albers(shapely.from_wkb(par["geometry"].values))
        par = par.drop(columns="geometry")
        tree = shapely.STRtree(pg_alb)
        reg = par["ind_status"].isin(REGISTERED).values
        fid = fid_all[idx]
        fg_alb = to_albers(shapely.from_wkb(fwkb_all[idx]))
        f_area = shapely.area(fg_alb)
        pairs = join_chunk(fg_alb, f_area, par, pg_alb, tree)
        pairs["reg"] = reg[pairs["pj"].values]
        n_reg = pairs[pairs["reg"]].groupby("fi").size()
        pairs = pairs.sort_values(["fi", "reg", "share"], ascending=[True, False, False])
        best = pairs.drop_duplicates("fi")
        o = pd.DataFrame({"fid": fid})
        o["car_overlap_count"] = n_reg.reindex(np.arange(len(fid)), fill_value=0).values.astype("int16")
        o["car_overlap_share"] = np.nan
        o.loc[best["fi"].values, "car_overlap_share"] = best["share"].values
        pj = np.full(len(fid), -1)
        pj[best["fi"].values] = best["pj"].values
        has = pj >= 0
        sel = par.iloc[pj[has]].reset_index(drop=True)
        for col_out, col_in in [("car_cod", "cod_imovel"), ("car_status", "ind_status"), ("car_type", "ind_tipo"),
                                ("car_area_ha", "area_ha"), ("car_fiscal_modules", "mod_fiscal"),
                                ("car_biome", "biome"), ("car_in_legal_amazon", "in_legal_amazon"),
                                ("lr_required_share", "lr_required_share"),
                                ("native_share_property", "native_share_property"),
                                ("lr_deficit_ha", "lr_deficit_ha"), ("lr_deficit_share", "lr_deficit_share"),
                                ("small_property", "small_property")]:
            v = sel[col_in].values
            arr = np.full(len(fid), None if v.dtype in (object, bool) else np.nan,
                          dtype=object if v.dtype in (object, bool) else "float64")
            arr[has] = v
            o[col_out] = arr
        # Canceled or suspended parcels: status and code only, no Forest Code indicators.
        nonreg = has.copy()
        nonreg[has] = ~np.isin(sel["ind_status"].values, REGISTERED)
        for col in ["car_area_ha", "car_fiscal_modules", "lr_required_share", "native_share_property",
                    "lr_deficit_ha", "lr_deficit_share"]:
            o.loc[nonreg, col] = np.nan
        o.loc[nonreg, "small_property"] = None
        outs.append(o)
        log(step="fields", state=state, done=min(k + chunk, len(forder)), of=len(forder), parcels=len(par),
            matched=int(has.sum()), s=round(time.time() - t0))
        del fg_alb, pairs, best, sel, pg_alb, tree, par
        gc.collect()
    out = pd.concat(outs, ignore_index=True).sort_values("fid").reset_index(drop=True)
    out["small_property"] = out["small_property"].astype("boolean")
    out["car_in_legal_amazon"] = out["car_in_legal_amazon"].astype("boolean")
    path = os.path.join(OUT, f"state={state}.parquet")
    out.to_parquet(path, index=False, compression="zstd")
    log(step="fields", state=state, fields=len(out), in_registered=int(out["car_status"].isin(REGISTERED).sum()),
        written=path, s=round(time.time() - t0))


# ---------------------------------------------------------------- summary

def summarize(df, eco_frontier=None):
    reg = df["car_status"].isin(REGISTERED)
    d = df[reg]
    deficit = d["lr_deficit_ha"] > 0
    large = d["small_property"].astype("boolean").fillna(True) == False  # noqa: E712
    big_def = deficit & large
    props = d.drop_duplicates("car_cod")
    pdef = props["lr_deficit_ha"] > 0
    plarge = props["small_property"].astype("boolean").fillna(True) == False  # noqa: E712
    r = {
        "n_fields": len(df),
        "share_fields_in_registered_parcel": reg.mean(),
        "share_fields_only_in_canceled_or_suspended": df["car_status"].isin(["CA", "SU"]).mean(),
        "share_fields_no_parcel": df["car_status"].isna().mean(),
        "share_fields_overlap_2plus": (df["car_overlap_count"] >= 2).mean(),
        "median_overlap_share": d["car_overlap_share"].median(),
        "share_fields_in_lr_deficit_property": (reg & (df["lr_deficit_ha"] > 0)).mean(),
        "share_fields_in_lr_deficit_property_over_4_modules": big_def.sum() / len(df) if len(df) else np.nan,
        "share_registered_fields_in_lr_deficit_property": deficit.mean() if len(d) else np.nan,
        "n_properties_touched": len(props),
        "n_properties_in_deficit": int(pdef.sum()),
        "lr_deficit_ha_properties": props.loc[pdef, "lr_deficit_ha"].sum(),
        "lr_deficit_ha_properties_over_4_modules": props.loc[pdef & plarge, "lr_deficit_ha"].sum(),
        "median_native_share_property": props["native_share_property"].median(),
    }
    return r


def step_summary():
    ecos = pd.read_csv(os.path.join(C.SUMMARIES, "ecoregions.csv"), usecols=["eco_id", "eco_name"]).drop_duplicates()
    front_ids = set(ecos.loc[ecos["eco_name"].isin(FRONTIER), "eco_id"])
    rows, allf = [], []
    for state in C.state_dirs(2024):
        p = os.path.join(OUT, f"state={state}.parquet")
        if not os.path.exists(p):
            continue
        df = pd.read_parquet(p, columns=["fid", "car_cod", "car_status", "car_overlap_count", "car_overlap_share",
                                         "lr_deficit_ha", "native_share_property", "small_property"])
        e = os.path.join(ECO_FIELDS, f"{state}.parquet")
        if os.path.exists(e):
            df = df.merge(pd.read_parquet(e, columns=["fid", "eco_id"]), on="fid", how="left")
        else:
            df["eco_id"] = np.nan
        r = summarize(df)
        r["state"] = state
        rows.append(r)
        allf.append(df)
    alld = pd.concat(allf, ignore_index=True)
    nat = summarize(alld)
    nat["state"] = "Brazil"
    rows.append(nat)
    fr = summarize(alld[alld["eco_id"].isin(front_ids)])
    fr["state"] = "Amazon frontier (7 ecoregions)"
    rows.append(fr)
    out = pd.DataFrame(rows)
    out.insert(1, "publication", "publishable (user, 14 Nov 2026); no cod_imovel")
    out = out[["state"] + [c for c in out.columns if c != "state"]]
    out.to_csv(SUMMARY_CSV, index=False, float_format="%.4f")
    log(step="summary", written=SUMMARY_CSV, rows=len(out))
    # Status mix of the parcels themselves, for the report.
    st = []
    for p in sorted(glob.glob(os.path.join(OUT_PARCELS, "*.parquet"))):
        t = pd.read_parquet(p, columns=["cod_estado", "ind_status", "area_ha", "lr_deficit_ha", "small_property",
                                        "in_legal_amazon", "native_share_property"])
        st.append(t)
    st = pd.concat(st, ignore_index=True)
    g = st.groupby("ind_status").agg(n=("area_ha", "size"), area_ha=("area_ha", "sum"))
    log(step="summary", parcel_status=g.reset_index().to_dict("records"))
    regp = st[st["ind_status"].isin(REGISTERED)]
    log(step="summary", registered_parcels=len(regp),
        in_deficit=int((regp["lr_deficit_ha"] > 0).sum()),
        deficit_ha=float(regp.loc[regp["lr_deficit_ha"] > 0, "lr_deficit_ha"].sum()),
        deficit_ha_over_4=float(regp.loc[(regp["lr_deficit_ha"] > 0) & (regp["small_property"] == False), "lr_deficit_ha"].sum()))  # noqa: E712


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["split", "nativemask", "parcels", "fields", "summary", "all"])
    ap.add_argument("--uf", nargs="*", help="state codes for parcels (default all)")
    ap.add_argument("--state", nargs="*", help="field state folder names for fields (default all)")
    a = ap.parse_args()
    if a.step in ("split", "all"):
        step_split()
    if a.step == "nativemask" or (a.step == "all" and not os.path.exists(NATIVE90)):
        step_nativemask()
    if a.step in ("parcels", "all"):
        ufs = a.uf or sorted(os.path.basename(p)[:-8] for p in glob.glob(os.path.join(OUT_RAW, "*.parquet")))
        for uf in ufs:
            if a.step == "all" and os.path.exists(os.path.join(OUT_PARCELS, f"{uf}.parquet")):
                continue
            step_parcels(uf)
            gc.collect()
    if a.step in ("fields", "all"):
        states = a.state or C.state_dirs(2024)
        for s in states:
            if a.step == "all" and os.path.exists(os.path.join(OUT, f"state={s}.parquet")):
                continue
            step_fields(s)
            gc.collect()
    if a.step in ("summary", "all"):
        step_summary()


if __name__ == "__main__":
    main()
