r"""Stage 5c: rebuild the zoom 9 to 11 field tiles without dropping any polygon (user, 17 November
2026: "keep all of the fields the browser can handle it"), then join all states inside WSL,
copy fields.pmtiles to F: and upload the tiles with s05_upload.py --tiles --check.

  python pipeline\s05c_rebuild_lowzoom.py

Per-state GeoJSON that already exists is reused. Zoom 9 to 11 state files older than 6 hours
are removed and rebuilt (s05_tiles.run_tippecanoe, -pk -pf --no-tiny-polygon-reduction); the
zoom 12 to 14 state files are reused. The join runs detached inside WSL (~/join.sh, output
~/tj/fields.pmtiles, exit code in ~/tj/done.txt), so a session end does not kill it. Launch
this script hidden with pipeline/launch_detached.py through WMI. Log:
F:\relative-land-productivity-data\analysis\decisions\logs\rebuild_lowzoom.log
"""
import json, os, shutil, subprocess, sys, time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
sys.path.insert(0, r"C:\Users\grupp\src\relative-land-productivity\pipeline")
import s05_tiles as T, s04_common as C
L = r"F:\relative-land-productivity-data\analysis\decisions\logs\rebuild_lowzoom.log"
NW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
def log(**k):
    k["t"] = time.strftime("%m-%d %H:%M:%S"); open(L, "a").write(json.dumps(k) + "\n")

def main():
    states = sorted(C.state_dirs(2024), key=lambda s: -os.path.getsize(C.fields_path(2024, s)))
    for s in states:
        p = os.path.join(T.STATE_TILES, f"{s}_z9_11.pmtiles")
        if os.path.exists(p) and os.path.getmtime(p) < time.time() - 6 * 3600:
            os.remove(p)
    log(step="start", states=len(states))
    with ProcessPoolExecutor(max_workers=3) as ex:
        for f in as_completed([ex.submit(T.write_geojsonl, s, False) for s in states]):
            log(step="geojson", **{("result_" + k if k == "step" else k): v for k, v in f.result().items() if k != "stderr_tail"})
    with ThreadPoolExecutor(max_workers=3) as ex:
        for f in as_completed([ex.submit(T.run_tippecanoe, s, False) for s in states]):
            r = f.result()
            log(step="tippecanoe", state=r["state"], runs=[(x.get("out"), x.get("returncode", x.get("status")), x.get("bytes")) for x in r["runs"]])
    for s in states:
        p = os.path.join(T.GEOJSON, f"{s}.geojsonl")
        if os.path.exists(p):
            os.remove(p)
    join()


def join():
    """Join inside WSL, copy to F:, upload. Until 17 November 2026 12:40 the join was started
    with setsid nohup inside a short wsl.exe call, which never ran the join, and the wait loop
    polled a UNC path with one leading backslash, so it waited forever. This script is itself
    launched detached, so a plain blocking wsl.exe call is safe here."""
    if "--from-copy" not in sys.argv:
        subprocess.run(["wsl", "-d", "Ubuntu-22.04", "--", "bash", "/home/tristangrupp/join.sh"], creationflags=NW)
    done =r"\\wsl.localhost\Ubuntu-22.04\home\tristangrupp\tj\done.txt"
    rc = open(done).read().strip() if os.path.exists(done) else "missing"
    src = r"\\wsl.localhost\Ubuntu-22.04\home\tristangrupp\tj\fields.pmtiles"
    log(step="join", rc=rc, bytes=os.path.getsize(src))
    if rc != "0":
        return
    dst = os.path.join(C.TILES, "fields.pmtiles")
    shutil.copyfile(src, dst + ".part"); os.replace(dst + ".part", dst)
    log(step="copy", bytes=os.path.getsize(dst))
    r = subprocess.run([sys.executable, os.path.join(C.REPO, "pipeline", "s05_upload.py"), "--tiles", "--check"],
                       capture_output=True, text=True, creationflags=NW)
    log(step="upload", rc=r.returncode, out=r.stdout[-2500:], err=r.stderr[-800:])

if __name__ == "__main__":
    if "--from-join" in sys.argv or "--from-copy" in sys.argv:
        join()
    else:
        main()
