"""Read-only local RGB comparison app, display packets and evaluation reports."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = unquote(urlsplit(path).path)
        if path == '/':
            return '/app/index.html'
        if path == '/vendor/three.module.min.js':
            return '/vendor/three.module.min.js'
        for prefix, root in (('/data/', Path('/data')), ('/app/', Path('/app')),
                             ('/results/evaluation/', Path('/results/evaluation'))):
            if path.startswith(prefix):
                target = (root / path[len(prefix):]).resolve()
                if target.is_relative_to(root) and not target.is_dir():
                    return str(target)
        if path in ('/index.html', '/style.css', '/viewer.js'):
            return '/app' + path
        return '/not-a-viewer-route'

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        super().end_headers()

    def list_directory(self, path):
        self.send_error(403, 'Directory listing is not enabled')
        return None


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
