"""Stage 1: prepare the Brazil field boundaries for 2020 and 2024.

Reads the seamfix Trazo4 part file for one state and one year, keeps the rows whose modal
MapBiomas class is agricultural, repairs the geometries, assigns an IBGE municipality from the
polygon centroid, and writes one GeoParquet 1.1 file with a bbox covering per state and year.

Input:  E:\\trazo4_master_parquet_seamfix\\country=Brazil\\state=<State>\\year=<YYYY>\\part-0.parquet
Output: F:\\relative-land-productivity-data\\fields\\year=<YYYY>\\state=<State>\\fields.parquet
Logs:   F:\\relative-land-productivity-data\\fields\\logs\\<YYYY>_<State>.json, one per task, and
        F:\\relative-land-productivity-data\\fields\\logs\\summary.csv rebuilt after every run.

Municipalities come from GADM 4.1 level 2 for Brazil, on disk at
D:\\WRI\\LATAM admin units\\gadm41_BRA_shp\\gadm41_BRA_2.shp. Its CC_2 column holds the seven
digit IBGE geocode for all 5,572 rows. A centroid that falls in no municipality polygon of its
state (coast, state border, rivers) takes the nearest one; the log counts those rows.

Geometry rules, from BRIEF.md: run shapely.make_valid on every invalid geometry, keep only the
polygonal part of a GeometryCollection, promote Polygon to MultiPolygon, drop empties. The log
counts rows whose geometry was invalid before make_valid, which is the set make_valid changed.

Memory: the part files use 100,000-row row groups. Each row group is processed on its own and
the results are held as Arrow tables, so a worker holds one row group of shapely objects at a
time plus the WKB of the finished rows. Four workers fit on this machine.

Usage:
  python pipeline/s01_prepare_fields.py                 all states, 2020 and 2024, 4 workers
  python pipeline/s01_prepare_fields.py --state Para --year 2024
  python pipeline/s01_prepare_fields.py --workers 6 --force

Existing outputs are skipped unless --force is given.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import shapely
from shapely import STRtree

SRC_ROOT = Path(r"E:\trazo4_master_parquet_seamfix\country=Brazil")
DATA_ROOT = Path(r"F:\relative-land-productivity-data")
FIELDS_ROOT = DATA_ROOT / "fields"
LOG_ROOT = FIELDS_ROOT / "logs"
GADM_PATH = Path(r"D:\WRI\LATAM admin units\gadm41_BRA_shp\gadm41_BRA_2.shp")

YEARS = (2020, 2024)
ROW_GROUP_SIZE = 100_000

# MapBiomas Collection 10 classes that count as agricultural, with the crop group each maps to.
CROP_GROUP = {
    39: "soybean",
    15: "pasture",
    19: "temporary_crop",
    41: "temporary_crop",
    20: "sugarcane",
    40: "rice",
    62: "cotton",
    21: "mosaic",
    9: "forest_plantation",
    18: "agriculture",
    46: "coffee",
    47: "citrus",
    48: "perennial",
    35: "oil_palm",
}
AG_CODES = np.array(sorted(CROP_GROUP), dtype=np.int16)

# Folder name under the seamfix root, UF code, GADM NAME_1.
STATES = {
    "Acre": ("AC", "Acre"),
    "Alagoas": ("AL", "Alagoas"),
    "Amapa": ("AP", "Amapá"),
    "Amazonas": ("AM", "Amazonas"),
    "Bahia": ("BA", "Bahia"),
    "Ceara": ("CE", "Ceará"),
    "Distrito_Federal": ("DF", "Distrito Federal"),
    "Espirito_Santo": ("ES", "Espírito Santo"),
    "Goias": ("GO", "Goiás"),
    "Maranhao": ("MA", "Maranhão"),
    "Mato_Grosso": ("MT", "Mato Grosso"),
    "Mato_Grosso_Do_Sul": ("MS", "Mato Grosso do Sul"),
    "Minas_Gerais": ("MG", "Minas Gerais"),
    "Para": ("PA", "Pará"),
    "Paraiba": ("PB", "Paraíba"),
    "Parana": ("PR", "Paraná"),
    "Pernambuco": ("PE", "Pernambuco"),
    "Piaui": ("PI", "Piauí"),
    "Rio_Grande_Do_Norte": ("RN", "Rio Grande do Norte"),
    "Rio_Grande_do_Sul": ("RS", "Rio Grande do Sul"),
    "Rio_de_Janeiro": ("RJ", "Rio de Janeiro"),
    "Rondonia": ("RO", "Rondônia"),
    "Roraima": ("RR", "Roraima"),
    "Santa_Catarina": ("SC", "Santa Catarina"),
    "Sao_Paulo": ("SP", "São Paulo"),
    "Sergipe": ("SE", "Sergipe"),
    "Tocantins": ("TO", "Tocantins"),
}

# Priority order from BRIEF.md. Tier 3 is every other state.
TIER = {
    "Mato_Grosso": 1, "Para": 1, "Amazonas": 1, "Acre": 1, "Rondonia": 1, "Roraima": 1, "Amapa": 1,
    "Mato_Grosso_Do_Sul": 2, "Goias": 2, "Tocantins": 2, "Maranhao": 2,
}

READ_COLUMNS = ["fid", "layer", "area_ha", "mbmode", "hansen_loss_year", "hansen_loss_frac", "geom"]

OUT_SCHEMA = pa.schema([
    ("fid", pa.int64()),
    ("layer", pa.string()),
    ("area_ha", pa.float64()),
    ("mbmode", pa.int16()),
    ("crop_group", pa.string()),
    ("hansen_loss_year", pa.int16()),
    ("hansen_loss_frac", pa.float64()),
    ("muni_code", pa.string()),
    ("state_uf", pa.string()),
    ("centroid_lon", pa.float64()),
    ("centroid_lat", pa.float64()),
    ("bbox", pa.struct([
        ("xmin", pa.float64()), ("ymin", pa.float64()), ("xmax", pa.float64()), ("ymax", pa.float64()),
    ])),
    ("geometry", pa.binary()),
])


def src_path(state: str, year: int) -> Path:
    return SRC_ROOT / f"state={state}" / f"year={year}" / "part-0.parquet"


def out_path(state: str, year: int) -> Path:
    return FIELDS_ROOT / f"year={year}" / f"state={state}" / "fields.parquet"


def log_path(state: str, year: int) -> Path:
    return LOG_ROOT / f"{year}_{state}.json"


def load_municipalities(state: str):
    """Return (STRtree, codes array) for the municipalities of one state."""
    import geopandas as gpd

    name_1 = STATES[state][1]
    gdf = gpd.read_file(GADM_PATH, where=f"NAME_1 = '{name_1}'")
    if gdf.empty:
        raise RuntimeError(f"no GADM municipalities for {state} ({name_1})")
    geoms = gdf.geometry.values
    tree = STRtree(geoms)
    return tree, gdf["CC_2"].to_numpy(dtype=object)


def polygonal_part(geom):
    """The polygonal content of a geometry, or an empty polygon."""
    if geom is None:
        return shapely.Polygon()
    t = geom.geom_type
    if t in ("Polygon", "MultiPolygon"):
        return geom
    if t == "GeometryCollection":
        polys = []
        for part in geom.geoms:
            if part.geom_type == "Polygon":
                polys.append(part)
            elif part.geom_type == "MultiPolygon":
                polys.extend(part.geoms)
        if not polys:
            return shapely.Polygon()
        return shapely.MultiPolygon(polys)
    return shapely.Polygon()


def repair(geoms: np.ndarray) -> tuple[np.ndarray, int, int]:
    """make_valid the invalid geometries, keep polygonal parts, promote to MultiPolygon.

    Returns (geometries, n_invalid, n_collection_trimmed).
    """
    invalid = ~shapely.is_valid(geoms)
    n_invalid = int(invalid.sum())
    n_trimmed = 0
    if n_invalid:
        fixed = shapely.make_valid(geoms[invalid])
        types = shapely.get_type_id(fixed)
        # type ids: 3 Polygon, 6 MultiPolygon, 7 GeometryCollection
        not_poly = (types != 3) & (types != 6)
        if not_poly.any():
            n_trimmed = int(not_poly.sum())
            fixed[not_poly] = [polygonal_part(g) for g in fixed[not_poly]]
        geoms = geoms.copy()
        geoms[invalid] = fixed
    is_single = shapely.get_type_id(geoms) == 3
    if is_single.any():
        singles = geoms[is_single]
        geoms = geoms.copy()
        geoms[is_single] = shapely.multipolygons(singles, indices=np.arange(len(singles)))
    return geoms, n_invalid, n_trimmed


def process_row_group(table: pa.Table, state_uf: str, muni_tree, muni_codes, stats: dict) -> pa.Table | None:
    mbmode = table.column("mbmode").to_numpy()
    keep = np.isin(mbmode, AG_CODES)
    stats["rows_in"] += len(mbmode)
    if not keep.any():
        return None
    sub = table.filter(pa.array(keep))
    sub = sub.set_column(sub.schema.get_field_index("geom"), "geom", sub.column("geom").cast(pa.large_binary()))
    stats["rows_agricultural"] += sub.num_rows

    geoms = shapely.from_wkb(sub.column("geom").to_numpy(zero_copy_only=False))
    geoms, n_invalid, n_trimmed = repair(geoms)
    stats["rows_invalid_before_make_valid"] += n_invalid
    stats["rows_collection_trimmed"] += n_trimmed

    empty = shapely.is_empty(geoms) | shapely.is_missing(geoms)
    if empty.any():
        stats["rows_dropped_empty"] += int(empty.sum())
        sub = sub.filter(pa.array(~empty))
        geoms = geoms[~empty]
    if len(geoms) == 0:
        return None

    centroids = shapely.centroid(geoms)
    cx = shapely.get_x(centroids)
    cy = shapely.get_y(centroids)

    # Point in polygon with the state's municipalities. A centroid in no polygon takes the nearest.
    muni = np.full(len(geoms), None, dtype=object)
    q_pts, q_polys = muni_tree.query(centroids, predicate="within")
    muni[q_pts] = muni_codes[q_polys]
    missing = np.array([m is None for m in muni])
    if missing.any():
        nearest = muni_tree.nearest(centroids[missing])
        muni[missing] = muni_codes[nearest]
        stats["rows_muni_nearest_fallback"] += int(missing.sum())

    bounds = shapely.bounds(geoms)
    mb = sub.column("mbmode").to_numpy()
    crop_group = np.array([CROP_GROUP[int(c)] for c in mb], dtype=object)

    out = pa.table({
        "fid": sub.column("fid"),
        "layer": sub.column("layer"),
        "area_ha": sub.column("area_ha"),
        "mbmode": sub.column("mbmode"),
        "crop_group": pa.array(crop_group, pa.string()),
        "hansen_loss_year": sub.column("hansen_loss_year"),
        "hansen_loss_frac": sub.column("hansen_loss_frac"),
        "muni_code": pa.array(muni, pa.string()),
        "state_uf": pa.array([state_uf] * len(geoms), pa.string()),
        "centroid_lon": pa.array(cx, pa.float64()),
        "centroid_lat": pa.array(cy, pa.float64()),
        "bbox": pa.StructArray.from_arrays(
            [pa.array(bounds[:, i], pa.float64()) for i in range(4)],
            names=["xmin", "ymin", "xmax", "ymax"],
        ),
        "geometry": pa.array(shapely.to_wkb(geoms), pa.binary()),
    }, schema=OUT_SCHEMA)
    stats["rows_out"] += out.num_rows
    return out


def geo_metadata(bbox: list[float]) -> bytes:
    from pyproj import CRS

    meta = {
        "version": "1.1.0",
        "primary_column": "geometry",
        "columns": {
            "geometry": {
                "encoding": "WKB",
                "geometry_types": ["MultiPolygon"],
                "crs": CRS.from_epsg(4326).to_json_dict(),
                "bbox": bbox,
                "covering": {"bbox": {
                    "xmin": ["bbox", "xmin"], "ymin": ["bbox", "ymin"],
                    "xmax": ["bbox", "xmax"], "ymax": ["bbox", "ymax"],
                }},
            }
        },
        "creator": {"library": "relative-land-productivity/pipeline/s01_prepare_fields.py"},
    }
    return json.dumps(meta).encode()


def prepare(state: str, year: int, force: bool = False) -> dict:
    t0 = time.time()
    dst = out_path(state, year)
    if dst.exists() and not force:
        return {"state": state, "year": year, "skipped": True}
    state_uf = STATES[state][0]
    stats = {
        "state": state, "year": year, "state_uf": state_uf, "skipped": False,
        "rows_in": 0, "rows_agricultural": 0, "rows_invalid_before_make_valid": 0,
        "rows_collection_trimmed": 0, "rows_dropped_empty": 0, "rows_muni_nearest_fallback": 0,
        "rows_out": 0,
    }
    muni_tree, muni_codes = load_municipalities(state)
    pf = pq.ParquetFile(src_path(state, year))
    parts = []
    for i in range(pf.metadata.num_row_groups):
        rg = pf.read_row_group(i, columns=READ_COLUMNS)
        out = process_row_group(rg, state_uf, muni_tree, muni_codes, stats)
        if out is not None:
            parts.append(out)
        del rg
    if not parts:
        table = OUT_SCHEMA.empty_table()
        bbox = [0.0, 0.0, 0.0, 0.0]
    else:
        table = pa.concat_tables(parts)
        b = table.column("bbox").combine_chunks()
        bbox = [
            float(pa.compute.min(b.field("xmin")).as_py()), float(pa.compute.min(b.field("ymin")).as_py()),
            float(pa.compute.max(b.field("xmax")).as_py()), float(pa.compute.max(b.field("ymax")).as_py()),
        ]
    table = table.replace_schema_metadata({b"geo": geo_metadata(bbox)})
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp, compression="zstd", row_group_size=ROW_GROUP_SIZE)
    os.replace(tmp, dst)
    stats["seconds"] = round(time.time() - t0, 1)
    stats["bbox"] = bbox
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    log_path(state, year).write_text(json.dumps(stats, indent=1))
    return stats


def write_summary() -> None:
    rows = []
    for p in sorted(LOG_ROOT.glob("*.json")):
        d = json.loads(p.read_text())
        d.pop("bbox", None)
        rows.append(d)
    if not rows:
        return
    keys = ["year", "state", "state_uf", "rows_in", "rows_agricultural", "rows_invalid_before_make_valid",
            "rows_collection_trimmed", "rows_dropped_empty", "rows_muni_nearest_fallback", "rows_out", "seconds"]
    with open(LOG_ROOT / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["year"], r["state"])):
            w.writerow(r)


def task_order(states: list[str], years: list[int]) -> list[tuple[str, int]]:
    """Tier 1 first, then tier 2, then the rest; inside a tier the biggest file first."""
    tasks = [(s, y) for s in states for y in years]

    def key(t):
        s, y = t
        return (TIER.get(s, 3), -os.path.getsize(src_path(s, y)))

    return sorted(tasks, key=key)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int, action="append", choices=YEARS, help="repeatable; default both")
    ap.add_argument("--state", action="append", choices=sorted(STATES), help="repeatable; default all")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--force", action="store_true", help="rewrite outputs that already exist")
    args = ap.parse_args(argv)

    years = args.year or list(YEARS)
    states = args.state or sorted(STATES)
    tasks = task_order(states, years)
    print(f"{len(tasks)} tasks, {args.workers} workers", flush=True)

    done = 0
    failed = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(prepare, s, y, args.force): (s, y) for s, y in tasks}
        for fut in as_completed(futures):
            s, y = futures[fut]
            done += 1
            try:
                r = fut.result()
            except Exception as e:  # noqa: BLE001
                failed.append((s, y, repr(e)))
                print(f"[{done}/{len(tasks)}] FAILED {s} {y}: {e!r}", flush=True)
                continue
            if r.get("skipped"):
                print(f"[{done}/{len(tasks)}] skip {s} {y} (exists)", flush=True)
            else:
                print(f"[{done}/{len(tasks)}] {s} {y}: in {r['rows_in']:,} ag {r['rows_agricultural']:,} "
                      f"invalid {r['rows_invalid_before_make_valid']:,} empty {r['rows_dropped_empty']:,} "
                      f"nearest {r['rows_muni_nearest_fallback']:,} out {r['rows_out']:,} "
                      f"in {r['seconds']} s", flush=True)
    write_summary()
    if failed:
        print("failed:", failed, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
