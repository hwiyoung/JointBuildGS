"""Read-only local packet server with bounded operational status reads."""
import argparse,json,mimetypes
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote,urlsplit
from zoneinfo import ZoneInfo

def read(p):return json.loads(p.read_text())
def status(task):
    rows=[]
    for region in ['P1','P2','P3']:
        for depth in ['005','0005','0']:
            for protection in ['native','release']:
                condition=f'LC_D{depth}_P{protection}';original=task/'runs'/region/condition
                attempts=[original]+sorted((task/'retries').glob(f'{region}_{condition}_attempt*'))
                run=next((x for x in attempts if (x/'metrics_receipt.json').exists() and read(x/'metrics_receipt.json').get('status')=='PASS'),attempts[-1])
                phases={p:read(run/(p+'_receipt.json')).get('status') for p in ['train','render','metrics'] if (run/(p+'_receipt.json')).exists()}
                failed=(original/'train_receipt.json').exists() and read(original/'train_receipt.json').get('status')=='FAIL'
                state='완료' if phases.get('metrics')=='PASS' else '실패·복구 대기' if 'FAIL' in phases.values() else '진행' if (run/'train_invocation.json').exists() else '대기'
                iteration=None;trace=run/'model/local_trace.jsonl'
                if trace.exists():
                    with trace.open('rb') as f:
                        f.seek(max(0,trace.stat().st_size-65536));lines=f.read().splitlines()
                    for line in reversed(lines):
                        try:iteration=json.loads(line).get('iteration');break
                        except (ValueError,TypeError):continue
                rows.append(dict(region=region,condition=condition,status=state,iteration=iteration,failed_original=failed,attempt=str(run.relative_to(task))))
    automation=None;log=task/'automation_v2/events.log'
    if log.exists():automation=log.read_text().splitlines()[-1] if log.stat().st_size else None
    return dict(rows=rows,complete=sum(x['status']=='완료' for x in rows),active=sum(x['status']=='진행' for x in rows),
                failed_original=sum(x['failed_original'] for x in rows),observed_at=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%H:%M:%S KST'),automation=automation,scientific_verdict=None)

def main():
    p=argparse.ArgumentParser();p.add_argument('--site',type=Path,required=True);p.add_argument('--task',type=Path,required=True);p.add_argument('--port',type=int,default=8080);a=p.parse_args()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                name=unquote(urlsplit(self.path).path).lstrip('/') or 'index.html'
                current=read(a.site/'current.json')['packet']
                if name=='status.json':
                    live=status(a.task);live['current_packet']=current.split('/')[-1]
                    body=json.dumps(live,ensure_ascii=False).encode();kind='application/json'
                else:
                    if not name.startswith('packets/'):
                        self.send_response(302);self.send_header('Location','/'+current+'/'+name);self.send_header('Cache-Control','no-store');self.end_headers();return
                    parts=name.split('/',2)
                    if len(parts)!=3 or not parts[1].startswith('packet_'):
                        self.send_error(404);return
                    root=(a.site/'packets'/parts[1]).resolve();name=parts[2];path=(root/name).resolve()
                    if not root.is_relative_to((a.site/'packets').resolve()):
                        self.send_error(404);return
                    if not path.is_relative_to(root) or not path.is_file() or name not in ['index.html','app.js','style.css','data.json','receipt.json','sources.json'] and not name.startswith(('assets/','downloads/')):
                        self.send_error(404);return
                    body=path.read_bytes();kind=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
                self.send_response(200);self.send_header('Content-Type',kind+'; charset=utf-8' if kind.startswith(('text/','application/json','application/javascript')) else kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
            except (OSError,ValueError,KeyError) as error:self.send_error(503,str(error))
        def log_message(self,*args):pass
    ThreadingHTTPServer(('0.0.0.0',a.port),Handler).serve_forever()

if __name__=='__main__':main()
