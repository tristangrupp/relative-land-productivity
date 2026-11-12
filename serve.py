"""Static server for docs/ with HTTP range support, which PMTiles needs.

Python's stock SimpleHTTPRequestHandler ignores Range headers and returns the whole file
with a 200. The pmtiles reader asks for byte ranges, so without 206 handling every tile
request downloads the whole archive. This adds 206 handling and permissive CORS. Copied
from the agriculture-and-drought repository.

    python serve.py [port]      # default 8810, serves ./docs
"""
import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")


class RangeHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Accept-Ranges", "bytes")
        # no-store: the data under the page changes constantly during development.
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def do_GET(self):
        rng = self.headers.get("Range")
        if not rng:
            return super().do_GET()
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return super().do_GET()
        size = os.path.getsize(path)
        m = re.match(r"bytes=(\d*)-(\d*)", rng.strip())
        if not m:
            return super().do_GET()
        s, e = m.group(1), m.group(2)
        start = int(s) if s else max(0, size - int(e))
        end = int(e) if e and s else size - 1
        end = min(end, size - 1)
        if start > end:
            self.send_response(416)
            self.send_header("Content-Range", "bytes */%d" % size)
            self.end_headers()
            return
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8810
    os.chdir(ROOT)
    print("serving %s on http://127.0.0.1:%d  (range requests enabled)" % (ROOT, port))
    ThreadingHTTPServer(("127.0.0.1", port), RangeHandler).serve_forever()
