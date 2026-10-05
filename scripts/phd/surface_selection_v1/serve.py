"""Explicit read-only HTTP endpoints for the complete surface-selection census."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import threading
from urllib.parse import unquote,urlsplit,parse_qs
from scripts.phd.surface_selection_v1.common import clean

def make_handler(store,app_root='src/apps/surface_selection_viewer_v1',vendor='/vendor/three.module.min.js'):
    app=Path(app_root);lock=threading.RLock()
    class Handler(BaseHTTPRequestHandler):
        def response(self,value,status=200,mime='application/json; charset=utf-8'):
            data=value if isinstance(value,bytes) else json.dumps(clean(value),ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
            if self.command!='HEAD':
                try:self.wfile.write(data)
                except (BrokenPipeError,ConnectionResetError):pass
        def file(self,p):
            p=Path(p);mime='text/javascript' if p.suffix=='.js' else mimetypes.guess_type(p.name)[0] or 'application/octet-stream'
            if not p.is_file():raise KeyError('Unknown file')
            return self.response(p.read_bytes(),mime=mime)
        def do_HEAD(self):self.do_GET()
        def do_GET(self):
            parsed=urlsplit(self.path);path=unquote(parsed.path);q=parse_qs(parsed.query)
            if '..' in path.split('/') or '\\' in path or '\0' in path:return self.response({'error':'Invalid path'},404)
            try:
                if path in ('/','/index.html'):return self.file(app/'index.html')
                if path in ('/app.js','/style.css'):return self.file(app/path[1:])
                if path=='/vendor/three.module.min.js':return self.file(vendor)
                if path=='/favicon.ico':return self.response(b'',204)
                if path=='/api/health':return self.response(dict(status='ready',read_only=True,scientific_verdict=None))
                parts=path.strip('/').split('/')
                if len(parts)==3 and parts[0]=='images':return self.file(store.image_path(parts[1],parts[2]))
                with lock:
                    if path=='/api/manifest':return self.response(store.manifest())
                    if len(parts)==3 and parts[:2]==['api','region']:return self.response(store.region(parts[2]))
                    if len(parts)==4 and parts[:2]==['api','unit']:return self.response(store.unit(parts[2],parts[3]))
                    if len(parts)==4 and parts[:2]==['api','points']:return self.response(store.points(parts[2],parts[3]))
                    if len(parts)==4 and parts[:2]==['api','evidence']:
                        return self.response(store.evidence(parts[2],parts[3],q.get('pair_id',[None])[0],int(q['anchor'][0]) if 'anchor' in q else None))
                    if path=='/downloads/summary.json':return self.response(store.eval_summary)
                return self.response({'error':'Unknown route'},404)
            except (KeyError,IndexError):return self.response({'error':'Unknown region/unit/image'},404)
            except ValueError as e:return self.response({'error':str(e)},400)
            except Exception as e:
                import traceback;traceback.print_exc();return self.response({'error':str(e)},500)
        def do_POST(self):self.response({'error':'Read-only viewer'},405)
        do_PUT=do_POST;do_PATCH=do_POST;do_DELETE=do_POST
    return Handler

def main():
    from scripts.phd.surface_selection_v1.data import Store
    store=Store();print(json.dumps(dict(status='ready',manifest=store.manifest())),flush=True)
    ThreadingHTTPServer(('0.0.0.0',8080),make_handler(store)).serve_forever()

if __name__=='__main__':main()
