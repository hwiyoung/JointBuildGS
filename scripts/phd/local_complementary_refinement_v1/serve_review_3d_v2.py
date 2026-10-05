"""Read-only 3D review routes; source payloads remain outside the viewer output."""
import argparse,json
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote,urlsplit

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8080);a=p.parse_args()
    class Handler(SimpleHTTPRequestHandler):
        def do_HEAD(self):
            name=unquote(urlsplit(self.path).path)
            if name in ['/','/index.html','/manifest.json','/receipt.json']:
                try:current=json.loads(Path('/site/current.json').read_text())['packet']
                except (OSError,ValueError,KeyError):self.send_error(503,'3D packet not yet available');return
                self.send_response(302);self.send_header('Location','/'+current+'/'+('index.html' if name=='/' else name.lstrip('/')));self.end_headers();return
            super().do_HEAD()
        def do_GET(self):
            name=unquote(urlsplit(self.path).path)
            if name in ['/','/index.html','/manifest.json','/receipt.json']:
                try:current=json.loads(Path('/site/current.json').read_text())['packet']
                except (OSError,ValueError,KeyError):self.send_error(503,'3D packet not yet available');return
                self.send_response(302);self.send_header('Location','/'+current+'/'+('index.html' if name=='/' else name.lstrip('/')));self.end_headers();return
            super().do_GET()
        def translate_path(self,path):
            path=unquote(urlsplit(path).path)
            if path.endswith('/gs3d_4way_viewer/build/three.module.min.js'):return '/three/three.module.min.js'
            for prefix,root in [('/packets/',Path('/site/packets')),('/cache/',Path('/site/cache')),('/parent/',Path('/parent')),('/task/',Path('/task'))]:
                if path.startswith(prefix):
                    target=(root/path[len(prefix):]).resolve()
                    if target.is_relative_to(root):
                        if prefix=='/task/' and not path.startswith(('/task/review_site/packets/','/task/evaluation/')):break
                        return str(target)
            return '/nonexistent-route'
        def end_headers(self):
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');super().end_headers()
        def list_directory(self,path):self.send_error(403,'Use the review manifest');return None
        def log_message(self,*args):pass
    ThreadingHTTPServer(('0.0.0.0',a.port),Handler).serve_forever()

if __name__=='__main__':main()
