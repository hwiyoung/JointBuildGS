"""Local HTTP surface with explicit read-only data/image routes."""
from __future__ import annotations
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import threading
from urllib.parse import parse_qs, unquote, urlsplit


def make_handler(store, app_root, vendor_path, task_root):
    app_root, vendor_path, task_root = Path(app_root), Path(vendor_path), Path(task_root)
    lock=threading.RLock()
    allowed_figures={f['path'].split('/')[-1] for row in json.loads((task_root/'figures/figure_manifest.json').read_text())['figures'] for f in row['files']}

    class Handler(BaseHTTPRequestHandler):
        server_version='SourceCandidateViewer/1'

        def respond(self, data, status=200, mime='application/json; charset=utf-8'):
            if not isinstance(data,bytes):
                from scripts.phd.source_candidate_v1.common import clean
                data=json.dumps(clean(data),ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','same-origin')
            self.end_headers()
            if self.command!='HEAD':
                try:self.wfile.write(data)
                except (BrokenPipeError,ConnectionResetError):pass # Superseded browser request.

        def file(self,path):
            path=Path(path)
            if not path.is_file():return self.respond({'error':'파일이 없습니다.'},404)
            mime=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
            if path.suffix in ('.js','.mjs'):mime='text/javascript; charset=utf-8'
            self.respond(path.read_bytes(),mime=mime)

        def do_HEAD(self):self.do_GET()

        def do_GET(self):
            parsed=urlsplit(self.path);path=unquote(parsed.path);q=parse_qs(parsed.query)
            if '\\' in path or '..' in path.split('/') or '\x00' in path:
                return self.respond({'error':'허용되지 않은 경로입니다.'},404)
            try:
                if path in ('/','/index.html'):return self.file(app_root/'index.html')
                if path in ('/app.js','/style.css'):return self.file(app_root/path[1:])
                if path=='/favicon.ico':return self.respond(b'',204,mime='image/x-icon')
                if path=='/vendor/three.module.min.js':return self.file(vendor_path)
                if path=='/api/health':return self.respond({'status':'ready','read_only':True,'scientific_verdict':None})
                parts=path.strip('/').split('/')
                if len(parts)==3 and parts[0]=='images':return self.file(store.image_path(parts[1],parts[2]))
                if len(parts)==2 and parts[0]=='figures' and parts[1] in allowed_figures:
                    return self.file(task_root/'figures'/parts[1])
                if len(parts)==2 and parts[0]=='downloads':
                    files={'per_cell.csv':'run/evaluation/per_cell.csv','risk_coverage.csv':'run/evaluation/risk_coverage.csv',
                           'stages.csv':'report/stages.csv','analysis.json':'report/analysis.json'}
                    if parts[1] in files:return self.file(task_root/files[parts[1]])
                with lock:
                    if path=='/api/manifest':return self.respond(store.manifest())
                    if len(parts)==3 and parts[:2]==['api','region']:return self.respond(store.region(parts[2]))
                    if len(parts)==4 and parts[:2]==['api','cell']:return self.respond(store.cell(parts[2],int(parts[3])))
                    if len(parts)==4 and parts[:2]==['api','points']:return self.respond(store.points(parts[2],parts[3]))
                    if len(parts)==4 and parts[:2]==['api','evidence']:
                        anchor=int(q['anchor'][0]) if 'anchor' in q else None
                        return self.respond(store.evidence(parts[2],int(parts[3]),q.get('pair_id',[None])[0],anchor))
                return self.respond({'error':'등록되지 않은 경로입니다.'},404)
            except (KeyError,ValueError,IndexError,FileNotFoundError) as exc:
                return self.respond({'error':str(exc)},400)
            except Exception as exc:
                self.log_error('request failed: %s: %s',type(exc).__name__,str(exc))
                return self.respond({'error':'자료를 읽는 중 오류가 발생했습니다. 서버 로그를 확인하세요.'},500)

        def do_POST(self):self.respond({'error':'읽기 전용 뷰어입니다.'},405)
        do_PUT=do_POST
        do_DELETE=do_POST
        do_PATCH=do_POST

    return Handler


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8080)
    parser.add_argument('--task-root',default='/task');parser.add_argument('--inputs-root',default='/inputs')
    parser.add_argument('--app-root',default='/workspace/JointBuildGS/src/apps/source_candidate_viewer_v1')
    parser.add_argument('--vendor-path',default='/vendor/three.module.min.js');args=parser.parse_args()
    if not Path('/.dockerenv').exists():raise RuntimeError('Run project server in Docker')
    from scripts.phd.source_candidate_viewer_v1.data import DataStore
    store=DataStore(args.task_root,inputs_root=args.inputs_root)
    handler=make_handler(store,args.app_root,args.vendor_path,args.task_root)
    print(json.dumps({'status':'VIEWER_READY','port':args.port,'scientific_verdict':None}),flush=True)
    ThreadingHTTPServer(('0.0.0.0',args.port),handler).serve_forever()


if __name__=='__main__':main()
