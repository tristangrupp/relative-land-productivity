"""Stage 5b: upload the tiles, stats.json and the scored GeoParquet to S3.

  python s05_upload.py [--tiles] [--fields] [--check] [--dry-run]

Target: s3://wri-datalab-sandbox/trazofields/trazo4/relative-land-productivity/ with the AWS
profile mfr-datalab (SSO). tiles\\fields.pmtiles, summary.pmtiles and stats.json go to
.../tiles/, the per-state analysis\\year=2024\\state=<State>\\fields_scored.parquet to
.../fields/year=2024/state=<State>/fields_scored.parquet and analysis\\abandoned\\<State>.parquet
to .../fields/abandoned/state=<State>.parquet. Every copy is `aws s3 cp` with
`--acl public-read`, skipped when S3 already holds an object of the same size, and retried up to
four times on a dropped connection; if the bucket refuses ACLs (BucketOwnerEnforced) the copy is retried
without the ACL, since the bucket policy already serves the restoration-works-para prefix
publicly. S3 is storage only; no AWS compute is started.

--check fetches the first bytes of each uploaded tile object anonymously with curl and prints
the HTTP status, so a 200 proves public read.

If the SSO session has expired (`aws s3 ls` fails with an SSO or token error), the script
prints the command `aws sso login --profile mfr-datalab --no-browser` and stops (the check is
`aws sts get-caller-identity`, because `aws s3 ls` of an empty prefix exits 1 too); the user
runs it and approves the URL. Nothing is uploaded until then.
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s04_common as C  # noqa: E402

PROFILE = "mfr-datalab"
BUCKET = "wri-datalab-sandbox"
PREFIX = "trazofields/trazo4/relative-land-productivity"
HTTP = f"https://{BUCKET}.s3.amazonaws.com/{PREFIX}"


def aws(*args, check=True):
    r = subprocess.run(["aws", *args, "--profile", PROFILE], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[-800:])
    return r


def session_ok():
    r = aws("sts", "get-caller-identity", check=False)
    if r.returncode == 0:
        return True
    err = (r.stderr or "").lower()
    if "sso" in err or "token" in err or "expired" in err or "credentials" in err:
        print("SSO session expired. Run this and approve the URL it prints:")
        print(f"  aws sso login --profile {PROFILE} --no-browser")
        return False
    raise RuntimeError(r.stderr)


def remote_size(key):
    """Size of the object on S3, or None when it does not exist."""
    r = aws("s3api", "head-object", "--bucket", BUCKET, "--key", key, check=False)
    if r.returncode != 0:
        return None
    return int(json.loads(r.stdout)["ContentLength"])


def cp(local, key, dry_run=False, attempts=4):
    uri = f"s3://{BUCKET}/{key}"
    size = os.path.getsize(local)
    if dry_run:
        print(json.dumps({"dry_run": True, "local": local, "s3": uri, "bytes": size}))
        return
    if remote_size(key) == size:
        print(json.dumps({"s3": uri, "bytes": size, "skipped": "same size on S3"}), flush=True)
        return
    t0 = time.time()
    acl = "public-read"
    for attempt in range(1, attempts + 1):
        r = aws("s3", "cp", local, uri, "--acl", "public-read", "--only-show-errors", check=False)
        if r.returncode != 0 and "AccessControlListNotSupported" in (r.stderr or ""):
            r = aws("s3", "cp", local, uri, "--only-show-errors", check=False)
            acl = "bucket-policy"
        if r.returncode == 0:
            break
        # the shared link drops connections now and then; wait and retry the same object
        print(json.dumps({"s3": uri, "attempt": attempt, "error": r.stderr.strip()[-300:]}), flush=True)
        if attempt == attempts:
            raise RuntimeError(f"{uri}: {r.stderr.strip()[-600:]}")
        time.sleep(30 * attempt)
    print(json.dumps({"s3": uri, "bytes": size, "seconds": round(time.time() - t0, 1), "acl": acl,
                      "mb_per_s": round(size / 1e6 / max(time.time() - t0, 1e-3), 2)}), flush=True)


def check_public():
    for name in ("stats.json", "summary.pmtiles", "fields.pmtiles"):
        url = f"{HTTP}/tiles/{name}"
        r = subprocess.run(["curl", "-s", "-o", os.devnull, "-w", "%{http_code} %{size_download}", "-r", "0-1023", url],
                           capture_output=True, text=True)
        print(json.dumps({"url": url, "range_request": r.stdout.strip()}), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiles", action="store_true")
    ap.add_argument("--fields", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not (args.tiles or args.fields or args.check):
        args.tiles = args.fields = args.check = True
    if not session_ok():
        sys.exit(2)
    if args.tiles:
        for name in ("stats.json", "summary.pmtiles", "fields.pmtiles"):
            p = os.path.join(C.TILES, name)
            if os.path.exists(p):
                cp(p, f"{PREFIX}/tiles/{name}", args.dry_run)
            else:
                print("missing", p)
    if args.fields:
        for s in C.state_dirs(2024):
            p = os.path.join(C.ANALYSIS, "year=2024", f"state={s}", "fields_scored.parquet")
            if os.path.exists(p):
                cp(p, f"{PREFIX}/fields/year=2024/state={s}/fields_scored.parquet", args.dry_run)
            p = os.path.join(C.ANALYSIS, "abandoned", f"state={s}.parquet")
            if os.path.exists(p):
                cp(p, f"{PREFIX}/fields/abandoned/state={s}.parquet", args.dry_run)
    if args.check and not args.dry_run:
        check_public()


if __name__ == "__main__":
    main()
