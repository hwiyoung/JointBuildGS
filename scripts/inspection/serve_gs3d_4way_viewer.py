#!/usr/bin/env python3
"""HTTP server with CORS + COOP/COEP headers for GaussianSplats3D 4-way viewer.

Serves the repository UI assets and exposes the declared external artifact root
under the read-only URL prefix ``/artifacts/``.

Headers set:
  - Cross-Origin-Opener-Policy: same-origin
  - Cross-Origin-Embedder-Policy: require-corp
  (Required if you want SharedArrayBuffer performance; viewer falls back if absent.)

Usage:
  python3 scripts/inspection/serve_gs3d_4way_viewer.py [PORT]
  Default PORT=8771. Binds 0.0.0.0 for LAN access.

  Open in browser:
    http://localhost:PORT/src/apps/gs3d_4way_viewer/
    http://<LAN-IP>:PORT/src/apps/gs3d_4way_viewer/
"""
import http.server
import os
import socketserver
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8771
ROOT = Path(__file__).resolve().parents[2]  # JointBuildGS repo root
if not os.environ.get("JBGS_ARTIFACT_ROOT"):
    raise RuntimeError(
        "JBGS_ARTIFACT_ROOT is required; run this server in the project container"
    )
ARTIFACT_ROOT = Path(os.environ["JBGS_ARTIFACT_ROOT"]).resolve()


class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        request_path = unquote(urlsplit(path).path)
        if request_path == "/artifacts" or request_path.startswith("/artifacts/"):
            relative = request_path.removeprefix("/artifacts").lstrip("/")
            candidate = (ARTIFACT_ROOT / relative).resolve()
            if not candidate.is_relative_to(ARTIFACT_ROOT):
                return str(ARTIFACT_ROOT / "__invalid_path__")
            return str(candidate)
        return super().translate_path(path)

    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, format, *args):
        # Compact log
        sys.stderr.write(f"{self.address_string()} - {format % args}\n")


def main():
    # chdir to repo root so relative paths work
    import os
    os.chdir(ROOT)
    print(f"Serving {ROOT} on port {PORT} (bind 0.0.0.0)")
    print(f"  Local:    http://localhost:{PORT}/src/apps/gs3d_4way_viewer/")
    print(f"  LAN:      http://<YOUR-IP>:{PORT}/src/apps/gs3d_4way_viewer/")
    print("Press Ctrl+C to stop.")
    with socketserver.TCPServer(("0.0.0.0", PORT), CORSRequestHandler) as httpd:
        httpd.serve_forever()


if __name__ == '__main__':
    main()
