"""Expose only the new evidence app, its local Three module and task payload."""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if urlsplit(self.path).path == "/":
            self.send_response(302)
            self.send_header("Location", "/app/index.html?manifest=/task/evaluation/viewer/manifest.json")
            self.end_headers()
            return
        super().do_GET()

    def translate_path(self, path):
        path = unquote(urlsplit(path).path)
        if path == "/":
            return "/app/index.html"
        if path == "/gs3d_4way_viewer/build/three.module.min.js":
            return "/three/three.module.min.js"
        for prefix, root in (("/app/", Path("/app")), ("/task/", Path("/task"))):
            if path.startswith(prefix):
                target = (root / path[len(prefix):]).resolve()
                if target.is_relative_to(root):
                    return str(target)
        return "/nonexistent-geogs-route"

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def list_directory(self, path):
        self.send_error(403, "Directory listing disabled; use evidence manifest")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()
