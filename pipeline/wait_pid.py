"""Wait until a process has exited, then exit 0, so run_chain.py can queue a job behind it.

    python wait_pid.py <pid> [--poll 60]

Used on 20 November 2026 to start the tier 3 Sentinel-2 extraction only after the tier 1
and 2 run (pid 38160) finishes, so the two never share the link or the memory.
"""
import argparse
import ctypes
import time

SYNCHRONIZE = 0x00100000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


def alive(pid):
    k = ctypes.windll.kernel32
    h = k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(code))
        return code.value == STILL_ACTIVE
    finally:
        k.CloseHandle(h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pid", type=int)
    ap.add_argument("--poll", type=int, default=60)
    a = ap.parse_args()
    print(f"waiting for pid {a.pid}", flush=True)
    while alive(a.pid):
        time.sleep(a.poll)
    print(f"pid {a.pid} has exited at {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)


if __name__ == "__main__":
    main()
