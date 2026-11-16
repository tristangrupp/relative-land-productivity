"""Start a long pipeline run fully detached from the calling session.

    python launch_detached.py <log> <err> -- <program> [args ...]

Processes started from a Claude Code shell, with Start-Process, or through WMI with a console
were stopped twice in November 2026: once when the session ended and once by a console Ctrl-C
that reached every process in the console group. This launcher starts the program with no
console (DETACHED_PROCESS) in its own process group (CREATE_NEW_PROCESS_GROUP), outside the
caller's job object when Windows allows it (CREATE_BREAKAWAY_FROM_JOB), with stdout and stderr
written to the given files, and the repo root as working directory. Run the launcher itself
through WMI (Invoke-CimMethod Win32_Process Create) so that it too is outside the session.
It prints the child's process id.
"""
import os
import subprocess
import sys

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    if len(sys.argv) < 5 or sys.argv[3] != "--":
        sys.exit(__doc__)
    log, err, cmd = sys.argv[1], sys.argv[2], sys.argv[4:]
    out = open(log, "a", buffering=1)
    er = open(err, "a", buffering=1)
    base = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        p = subprocess.Popen(cmd, cwd=REPO, stdout=out, stderr=er, stdin=subprocess.DEVNULL,
                             creationflags=base | CREATE_BREAKAWAY_FROM_JOB, close_fds=True)
    except OSError:
        p = subprocess.Popen(cmd, cwd=REPO, stdout=out, stderr=er, stdin=subprocess.DEVNULL,
                             creationflags=base, close_fds=True)
    print(p.pid, flush=True)


if __name__ == "__main__":
    main()
