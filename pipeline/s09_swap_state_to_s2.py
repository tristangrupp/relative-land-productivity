"""Stage 9: switch one state of the live map from MODIS to Sentinel-2 (decision of 14 November 2026,
"slowly work through state by state updating modis to sentinel").

  python s09_swap_state_to_s2.py --state Para                 every step below, then the national rebuild
  python s09_swap_state_to_s2.py --state Para --steps assemble metrics relative compare swap
  python s09_swap_state_to_s2.py --state Para --no-tiles      stop after the decisions and the summary
  python s09_swap_state_to_s2.py --revert --state Para        put the MODIS tables back

Run order agreed with the user: Mato_Grosso, Para, Rondonia, Acre, Amazonas, Roraima, Amapa, then
Mato_Grosso_Do_Sul, Goias, Tocantins, Maranhao. Run a state once s03g_s2_fetch_reduce.py has finished
its tiles; the assemble step refuses a state with under --min-complete of its tiles complete.

Steps, in order (each is a subprocess of the stage script, logged to
analysis\\source=s2\\logs\\swap_<State>.log):

  assemble   s03h_s2_assemble.py --state S (both field layers), then the completeness check on
             extracted\\s2\\year=<Y>\\state=<S>\\ndvi_monthly.meta.json
  metrics    s04_metrics.py --source s2 for polys 2024 ay 2024, polys 2024 ay 2020, polys 2020 ay 2020
  relative   s04_relative.py --source s2 --polys 2024 and --polys 2020, with --no-summary-copy
  compare    s08_s2_compare.py all --state S: s2 change classes, the calibration of s2 to the MODIS
             national reference (fields over 25 ha, high MODIS confidence), the calibrated area
             values and r_eco_2024, the comparison with MODIS, the noise measurement and the change
             scale k, the IBGE check. The MODIS copy of the live tables is made first.
  swap       s04_change.py --source s2 --change-scale k --force for the state, which rewrites the
             live analysis\\year=2024\\state=S\\fields_scored.parquet, the abandoned layer and
             counts.json from s2 with source = s2; then analysis\\sources.json records the state.
  decisions  s07_decisions.py all (every state: the national reference and the area calls move a
             little when a state changes sensor), then s07 report.
  tiles      s05_tiles.py fields --force for every state (about 45 minutes), summary, stats.
  upload     s05_upload.py --tiles --check, and s05_upload.py --fields for the GeoParquet.

After the run: bump the cache busters in docs/index.html if the site changed, record the state in
WORKLOG.md (counts from data/summaries/s2_<uf>_noise.json and decisions_v2.json), commit and push.

Revert: copies analysis\\source=modis\\year=2024\\state=S\\* back over the live tables, removes the
state from sources.json, then the decisions, tiles and upload steps rebuild as above.

Python: E:\\Water\\water intelligence\\wci_tools\\.venv\\Scripts\\python.exe. Peak memory: the s2
steps stay under 3 GB per state; s07_decisions.py national holds about 6 GB.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s04_common as C  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
S2_EXTRACTED = os.path.join(C.EXTRACTED, "s2")
SOURCES_JSON = os.path.join(C.ANALYSIS, "sources.json")
MODIS_COPY = os.path.join(C.ANALYSIS, "source=modis")
RUN_ORDER = ["Mato_Grosso", "Para", "Rondonia", "Acre", "Amazonas", "Roraima", "Amapa",
             "Mato_Grosso_Do_Sul", "Goias", "Tocantins", "Maranhao"]
STEPS = ["assemble", "metrics", "relative", "compare", "swap", "decisions", "tiles", "upload"]


class Runner:
    def __init__(self, state):
        self.state = state
        d = os.path.join(C.ANALYSIS, "source=s2", "logs")
        os.makedirs(d, exist_ok=True)
        self.log_path = os.path.join(d, f"swap_{state}.log")

    def note(self, **kw):
        kw["t"] = datetime.now().isoformat(timespec="seconds")
        line = json.dumps(kw, ensure_ascii=False)
        print(line, flush=True)
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def run(self, script, *args):
        cmd = [PY, os.path.join(HERE, script), *[str(a) for a in args]]
        t0 = time.time()
        self.note(run=" ".join(cmd[1:]))
        with open(self.log_path, "a", encoding="utf-8") as fh:
            r = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=C.REPO)
        self.note(done=script, returncode=r.returncode, seconds=round(time.time() - t0))
        if r.returncode != 0:
            sys.exit(f"{script} failed, see {self.log_path}")


def load_sources():
    if not os.path.exists(SOURCES_JSON):
        return {}
    with open(SOURCES_JSON) as fh:
        return json.load(fh)


def save_sources(src):
    with open(SOURCES_JSON, "w") as fh:
        json.dump(src, fh, indent=1)
    # a copy in the repo, so the record of which states are s2 is versioned
    with open(os.path.join(C.SUMMARIES, "sources.json"), "w") as fh:
        json.dump(src, fh, indent=1)


def live_paths(state):
    d = os.path.join(C.ANALYSIS, "year=2024", f"state={state}")
    return {"fields": os.path.join(d, "fields_scored.parquet"), "counts": os.path.join(d, "counts.json"),
            "abandoned": os.path.join(C.ANALYSIS, "abandoned", f"state={state}.parquet")}


def copy_paths(state):
    d = os.path.join(MODIS_COPY, "year=2024", f"state={state}")
    return {"fields": os.path.join(d, "fields_scored.parquet"), "counts": os.path.join(d, "counts.json"),
            "abandoned": os.path.join(MODIS_COPY, "abandoned", f"state={state}.parquet")}


def keep_modis_copy(r):
    """Copy the live MODIS tables of the state aside once, before anything overwrites them."""
    if load_sources().get(r.state, {}).get("source") == "s2":
        r.note(modis_copy="state already swapped, copy kept as it is")
        return
    live, cp = live_paths(r.state), copy_paths(r.state)
    for k in live:
        if os.path.exists(live[k]) and not os.path.exists(cp[k]):
            os.makedirs(os.path.dirname(cp[k]), exist_ok=True)
            shutil.copy2(live[k], cp[k])
    r.note(modis_copy={k: os.path.exists(v) for k, v in cp.items()})


def step_assemble(r, min_complete):
    r.run("s03h_s2_assemble.py", "--state", r.state)
    for y in (2020, 2024):
        mp = os.path.join(S2_EXTRACTED, f"year={y}", f"state={r.state}", "ndvi_monthly.meta.json")
        if not os.path.exists(mp):
            sys.exit(f"{r.state} {y}: no assembled table; is the extraction done for this state?")
        with open(mp) as fh:
            m = json.load(fh)
        share = m["tiles_complete"] / max(m["tiles"], 1)
        r.note(assemble=y, tiles=m["tiles"], tiles_complete=m["tiles_complete"], share=round(share, 4))
        if share < min_complete:
            sys.exit(f"{r.state} {y}: {m['tiles_complete']} of {m['tiles']} tiles complete, under {min_complete}; wait for s03g")


def step_metrics(r):
    for polys, ay in ((2024, 2024), (2024, 2020), (2020, 2020)):
        r.run("s04_metrics.py", "--source", "s2", "--polys", polys, "--ay", ay, "--states", r.state, "--workers", 1, "--force")


def step_relative(r):
    for polys in (2024, 2020):
        r.run("s04_relative.py", "--source", "s2", "--polys", polys, "--states", r.state, "--no-summary-copy")


def step_compare(r):
    keep_modis_copy(r)
    r.run("s08_s2_compare.py", "all", "--state", r.state)


def step_swap(r):
    keep_modis_copy(r)
    p = os.path.join(C.ANALYSIS, "source=s2", "compare", f"noise_{r.state}.json")
    with open(p) as fh:
        noise = json.load(fh)
    k = float(noise["change_scale"])
    r.run("s04_change.py", "--source", "s2", "--states", r.state, "--workers", 1, "--force", "--change-scale", k)
    src = load_sources()
    src[r.state] = {"source": "s2", "change_scale": k, "noise_fields": noise["fields"],
                    "changing_share_large": noise["changing_share_large"], "swapped": datetime.now().isoformat(timespec="seconds")}
    save_sources(src)
    r.note(swap=r.state, change_scale=k)


def step_decisions(r):
    r.run("s07_decisions.py", "all")


def step_tiles(r, tiles):
    if tiles:
        r.run("s05_tiles.py", "fields", "--force")
    r.run("s05_tiles.py", "summary")
    r.run("s05_tiles.py", "stats")


def step_upload(r):
    r.run("s05_upload.py", "--tiles", "--check")
    r.run("s05_upload.py", "--fields")


def revert(r):
    live, cp = live_paths(r.state), copy_paths(r.state)
    for k in live:
        if os.path.exists(cp[k]):
            shutil.copy2(cp[k], live[k])
    src = load_sources()
    src.pop(r.state, None)
    save_sources(src)
    r.note(revert=r.state)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--steps", nargs="*", default=STEPS, choices=STEPS)
    ap.add_argument("--min-complete", type=float, default=0.99, help="share of the state's s2 tiles that must be complete")
    ap.add_argument("--no-tiles", action="store_true", help="skip the field tiles (summary and stats still rebuild)")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    if a.state not in C.state_dirs(2024):
        sys.exit(f"unknown state {a.state}")
    r = Runner(a.state)
    r.note(start=a.state, steps=a.steps, revert=a.revert)
    if a.revert:
        revert(r)
        steps = [s for s in ("decisions", "tiles", "upload") if s in a.steps]
    else:
        steps = a.steps
    for s in steps:
        if s == "assemble":
            step_assemble(r, a.min_complete)
        elif s == "metrics":
            step_metrics(r)
        elif s == "relative":
            step_relative(r)
        elif s == "compare":
            step_compare(r)
        elif s == "swap":
            step_swap(r)
        elif s == "decisions":
            step_decisions(r)
        elif s == "tiles":
            step_tiles(r, not a.no_tiles)
        elif s == "upload" and not a.no_upload:
            step_upload(r)
    r.note(end=a.state)


if __name__ == "__main__":
    main()
