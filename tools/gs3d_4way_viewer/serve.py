#!/usr/bin/env python3
"""HTTP server with CORS + COOP/COEP headers for GaussianSplats3D 4-way viewer.

Serves the JointBuildGS repo root so HTML at tools/gs3d_4way_viewer/index.html
can reference PLY files at ../../results/phase1_ablation/figures/ply_3dgs_dense/*.ply.

Headers set:
  - Cross-Origin-Opener-Policy: same-origin
  - Cross-Origin-Embedder-Policy: require-corp
  (Required if you want SharedArrayBuffer performance; viewer falls back if absent.)

Usage:
  python3 tools/gs3d_4way_viewer/serve.py [PORT]
  Default PORT=8771. Binds 0.0.0.0 for LAN access.

  Open in browser:
    http://localhost:PORT/tools/gs3d_4way_viewer/
    http://<LAN-IP>:PORT/tools/gs3d_4way_viewer/
"""
import http.server
import socketserver
import sys
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8771
ROOT = Path(__file__).resolve().parents[2]  # JointBuildGS repo root


class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
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
    print(f"  Local:    http://localhost:{PORT}/tools/gs3d_4way_viewer/")
    print(f"  LAN:      http://<YOUR-IP>:{PORT}/tools/gs3d_4way_viewer/")
    print("Press Ctrl+C to stop.")
    with socketserver.TCPServer(("0.0.0.0", PORT), CORSRequestHandler) as httpd:
        httpd.serve_forever()


if __name__ == '__main__':
    main()
