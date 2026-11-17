"""Run several pipeline scripts one after another, stopping at the first failure.

    python run_chain.py "pipeline/s09_swap_state_to_s2.py --state Para --steps assemble" "..."

Each argument is one script with its arguments, run with this same interpreter from the repo
root, with output to this process's streams, so launch_detached.py can send everything to one
log. This replaces cmd.exe "a && b && c" chains. On 17 November 2026 such a chain failed at
once with "'E:\\Water\\water' is not recognized", because the venv Python path has a space.
"""
import os
import shlex
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREATE_NO_WINDOW = 0x08000000


def main():
    for line in sys.argv[1:]:
        cmd = [sys.executable, "-u"] + shlex.split(line)
        print(f"[chain] {time.strftime('%Y-%m-%d %H:%M:%S')} start: {line}", flush=True)
        rc = subprocess.call(cmd, cwd=REPO, stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
        print(f"[chain] {time.strftime('%Y-%m-%d %H:%M:%S')} exit {rc}: {line}", flush=True)
        if rc != 0:
            sys.exit(rc)


if __name__ == "__main__":
    main()
