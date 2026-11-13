"""Stage 4, helper: MODIS 16-day NDVI of one agricultural year reduced to the polygons of another.

The extract stage (s03e_modis_reduce.py) couples the polygon year and the composite year: the
table extracted\\modis\\year=2024 holds the 23 composites of agricultural year 2024 on the 2024
polygons, and year=2020 the 2020 composites on the 2020 polygons. METHODS.md section 2 wants
both years measured on the 2024 polygons, so this script reduces the composites of
agricultural year 2020 (day 241 of 2019 to day 225 of 2020) with the weights built for the
2024 polygons (weights\\modis\\year=2024). It reuses the extract stage's functions unchanged
(valid mask, sparse product, half-valid rule, interpolation) by importing s03e_modis_reduce
and pointing its PARTIAL and OUT module paths at folders under analysis\\, so nothing under
extracted\\modis is written or read except the raw GeoTIFFs and the weights.

Outputs:
  analysis\\modis_xyear\\partial\\year=<polys>\\<h##v##>\\<YYYYDDD>.npz     num and den per weights row
  analysis\\modis_xyear\\year=<polys>\\state=<State>\\ndvi_16day.parquet     same schema as the
                                                                           extract tables, but the
                                                                           ndvi_<YYYYDDD> columns are
                                                                           the composites of --ay

Usage (wci_tools venv):
  python s04_xyear_reduce.py reduce  [--polys 2024] [--ay 2020] [--workers 2]
  python s04_xyear_reduce.py assemble [--polys 2024] [--ay 2020] [--workers 2] [--states ...] [--partial] [--force]
  python s04_xyear_reduce.py watch   [--poll 180]      reduce as raw files land, assemble when complete
  python s04_xyear_reduce.py status
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s03e_modis_reduce as s03e  # noqa: E402
from s03c_modis_fetch import composites_for_year  # noqa: E402

DATA = r"F:\relative-land-productivity-data"
ROOT = os.path.join(DATA, "analysis", "modis_xyear")
PARTIAL = os.path.join(ROOT, "partial")

# Redirect the extract module's partial and output roots to this script's folders. The raw
# GeoTIFF, weights and fields paths stay as the extract stage defines them.
s03e.PARTIAL = PARTIAL
s03e.OUT = ROOT


def _init_worker():
    import s03e_modis_reduce as m
    m.PARTIAL = PARTIAL
    m.OUT = ROOT


def tiles():
    with open(s03e.TILES_NEEDED) as fh:
        return json.load(fh)["tiles"]


def expected(polys, ay):
    missing = s03e.load_missing()
    exp = []
    for c in composites_for_year(ay):
        for t in tiles():
            if t["hv"] in missing.get(c, []):
                continue
            exp.append((t["hv"], c))
    return exp


def pending(polys, ay):
    return [(hv, c) for hv, c in expected(polys, ay) if not os.path.exists(s03e.partial_path(polys, hv, c))]


def reducible(polys, ay):
    """Pending partials whose raw NDVI and QA files are already on disk."""
    out = {}
    for hv, c in pending(polys, ay):
        p_nd, p_qa, _ = s03e.raw_paths(c, hv)
        if os.path.exists(p_nd) and os.path.exists(p_qa):
            out.setdefault(hv, []).append(c)
    return out


def run_reduce(polys, ay, workers):
    tasks = reducible(polys, ay)
    if not tasks:
        return 0
    t0 = time.time()
    n = 0
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
        futs = [ex.submit(s03e.reduce_tile_year, polys, hv, comps) for hv, comps in tasks.items()]
        for f in as_completed(futs):
            try:
                r = f.result()
                n += r["done"]
                if r["done"]:
                    print(json.dumps(r), flush=True)
            except Exception as e:  # noqa: BLE001
                print(json.dumps({"status": "fail", "error": str(e)[:300]}), flush=True)
    print(f"xyear reduce pass: {n} partials in {time.time() - t0:.0f} s", flush=True)
    return n


def run_assemble(polys, ay, workers, states=None, partial_ok=False, force=False):
    comps = composites_for_year(ay)
    all_states = sorted({s for t in tiles() for s in t["states"]})
    todo = []
    for s in all_states:
        if states and s not in states:
            continue
        out = os.path.join(ROOT, f"year={polys}", f"state={s}", "ndvi_16day.parquet")
        if os.path.exists(out) and not force:
            continue
        hvs = [t["hv"] for t in tiles() if s in t["states"]]
        todo.append((polys, s, hvs, comps))
    results = []
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
        futs = [ex.submit(s03e.assemble_state, y, s, hvs, c, partial_ok) for y, s, hvs, c in todo]
        for f in as_completed(futs):
            try:
                r = f.result()
            except Exception as e:  # noqa: BLE001
                r = {"status": "fail", "error": str(e)[:300]}
            r["ay"] = ay
            print(json.dumps(r), flush=True)
            results.append(r)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["reduce", "assemble", "watch", "status"])
    ap.add_argument("--polys", type=int, default=2024, help="polygon year whose weights are used")
    ap.add_argument("--ay", type=int, default=2020, help="agricultural year of the composites")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--states", nargs="*", default=None)
    ap.add_argument("--partial", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--poll", type=int, default=180)
    args = ap.parse_args()
    if args.step == "status":
        exp = expected(args.polys, args.ay)
        pend = pending(args.polys, args.ay)
        red = reducible(args.polys, args.ay)
        print(json.dumps({"expected": len(exp), "pending": len(pend),
                          "reducible_now": sum(len(v) for v in red.values())}))
    elif args.step == "reduce":
        run_reduce(args.polys, args.ay, args.workers)
        print("pending:", len(pending(args.polys, args.ay)))
    elif args.step == "assemble":
        run_assemble(args.polys, args.ay, min(args.workers, 3), args.states, args.partial, args.force)
    else:
        while True:
            run_reduce(args.polys, args.ay, args.workers)
            left = len(pending(args.polys, args.ay))
            print(f"{datetime.now().isoformat(timespec='seconds')} xyear pending partials: {left}", flush=True)
            if left == 0:
                break
            time.sleep(args.poll)
        run_assemble(args.polys, args.ay, min(args.workers, 3), args.states)


if __name__ == "__main__":
    main()
