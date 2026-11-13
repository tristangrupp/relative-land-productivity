"""Stage 4 and 5 runner: wait for the extract tables, then run every analyze stage in order.

  python s04_run_all.py [--source modis] [--skip-wait] [--from metrics|relative|change|validate|tiles|upload]

Waits until every state has its MODIS table for both polygon years
(extracted\\modis\\year=<Y>\\state=<S>\\ndvi_16day.parquet, written by the extract watcher) and
its cross-year table (analysis\\modis_xyear\\year=2024\\state=<S>\\ndvi_16day.parquet, written by
s04_xyear_reduce.py watch), polling every three minutes, then runs:

  1. s04_metrics.py for (polys 2024, ay 2024), (2024, 2020) and (2020, 2020)
  2. s04_relative.py --polys 2024 (fits layer 2 on both years) and --polys 2020
  3. s04_change.py
  4. s04_validate.py
  5. s05_tiles.py all --force
  6. s05_upload.py

Each step's stdout goes to analysis\\run_all.log with timings. A failing step stops the run.
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s04_common as C  # noqa: E402

PY = sys.executable
HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(C.ANALYSIS, "run_all.log")
STEPS = ["metrics", "relative", "change", "validate", "tiles", "upload"]


def log(msg):
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    os.makedirs(C.ANALYSIS, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def missing_tables(source):
    miss = []
    for y in C.POLY_YEARS:
        for s in C.state_dirs(y):
            if not os.path.exists(C.ndvi_path(source, y, y, s)):
                miss.append(f"{y}/{s}")
    for s in C.state_dirs(2024):
        if not os.path.exists(C.ndvi_path(source, 2024, 2020, s)):
            miss.append(f"xyear/{s}")
    return miss


def run(step, args):
    t0 = time.time()
    log(f"start {step}: {' '.join(args)}")
    with open(LOG, "a", encoding="utf-8") as fh:
        r = subprocess.run([PY, os.path.join(HERE, args[0])] + args[1:], stdout=fh, stderr=subprocess.STDOUT, cwd=HERE)
    log(f"end {step}: returncode {r.returncode} in {time.time() - t0:.0f} s")
    if r.returncode != 0:
        log("stopping")
        sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="modis")
    ap.add_argument("--skip-wait", action="store_true")
    ap.add_argument("--from", dest="start", choices=STEPS, default="metrics")
    ap.add_argument("--poll", type=int, default=180)
    args = ap.parse_args()
    if not args.skip_wait:
        while True:
            miss = missing_tables(args.source)
            if not miss:
                break
            log(f"waiting for {len(miss)} NDVI tables, e.g. {miss[:3]}")
            time.sleep(args.poll)
    log("all NDVI tables present")
    todo = STEPS[STEPS.index(args.start):]
    src = args.source
    if "metrics" in todo:
        run("metrics 2024/2024", ["s04_metrics.py", "--source", src, "--polys", "2024", "--ay", "2024", "--workers", "3", "--force"])
        run("metrics 2024/2020", ["s04_metrics.py", "--source", src, "--polys", "2024", "--ay", "2020", "--workers", "3", "--force"])
        run("metrics 2020/2020", ["s04_metrics.py", "--source", src, "--polys", "2020", "--ay", "2020", "--workers", "3", "--force"])
    if "relative" in todo:
        run("relative 2024", ["s04_relative.py", "--source", src, "--polys", "2024"])
        run("relative 2020", ["s04_relative.py", "--source", src, "--polys", "2020"])
    if "change" in todo:
        run("change", ["s04_change.py", "--source", src, "--workers", "3", "--force"])
    if "validate" in todo:
        run("validate", ["s04_validate.py", "--source", src])
    if "tiles" in todo:
        run("tiles", ["s05_tiles.py", "all", "--workers", "4", "--parallel", "3", "--force"])
    if "upload" in todo:
        run("upload", ["s05_upload.py"])
    log("run_all done")


if __name__ == "__main__":
    main()
