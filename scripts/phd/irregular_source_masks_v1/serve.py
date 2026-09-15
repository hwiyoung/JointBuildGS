"""Read-only evidence browser and exact native-pixel query, CPU Docker only."""
from __future__ import annotations
import argparse
from functools import lru_cache
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from threading import RLock
from urllib.parse import parse_qs, urlsplit
import numpy as np

LOCK = RLock()

@lru_cache(maxsize=1)
def arrays(path, mtime):
    with np.load(path, allow_pickle=False) as data:
        return {key: data[key] for key in data.files}

def clean(value):
    if isinstance(value, dict): return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value, (np.ndarray, list, tuple)): return [clean(v) for v in value]
    if isinstance(value, (np.integer,)): return int(value)
    if isinstance(value, (np.bool_,)): return bool(value)
    if isinstance(value, (np.floating, float)): return float(value) if np.isfinite(value) else None
    return value

def pixel(root, query):
    region, view = query['region'][0], query['view'][0]
    if region not in ('P1','P2','P3') or not re.fullmatch(r'view_\d+', view):
        raise ValueError('Invalid region/view')
    x, y = int(query['x'][0]), int(query['y'][0])
    folder = root/'evidence'/region/view
    meta = json.loads((folder/'camera.json').read_text())
    h,w = meta['height'], meta['width']
    if not (0<=x<w and 0<=y<h): raise ValueError('Pixel outside source image')
    file = folder/'arrays.npz'
    with LOCK:
        data = arrays(str(file), file.stat().st_mtime_ns)
        values={}
        for key,a in data.items():
            if a.shape == (h,w): values[key]=a[y,x]
            elif a.ndim==3 and a.shape[-2:]==(h,w): values[key]=a[:,y,x]
            elif a.ndim==3 and a.shape[:2]==(h,w) and a.shape[2]<=32: values[key]=a[y,x]
    labels={0:'검사 범위 밖',1:'한쪽 이상 깊이 결측',2:'깊이 양립 가능 · 우세 소스 미판정',
            3:'관측 검사 진행 중',4:'판단 유보',5:'MVS 지지 후보',6:'Prior 지지 후보',7:'두 깊이 결측 · 영역 소속 불명'}
    return clean(dict(region=region,view=view,x=x,y=y,decision_label=labels.get(int(values.get('decision',-1)),'미산출'),
                      values=values,neighbor_names=meta.get('neighbors',[]),
                      visibility_status_labels={0:'기준 깊이 무효 또는 미검사',1:'영상 밖 또는 카메라 뒤',
                          2:'이웃 깊이 결측',3:'해당 깊이 모델과 호환',4:'관측 모델 뒤',5:'관측 모델 앞'},
                      scientific_verdict=None,interpretation='관측 기반 후보 판정입니다. 보정된 소스 정확도 또는 실제 시간 변화 정답을 뜻하지 않습니다.'))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--port',type=int,default=8080);a=ap.parse_args()
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(a.root),**kwargs)
        def do_GET(self):
            url=urlsplit(self.path)
            if url.path!='/api/pixel':return super().do_GET()
            try:
                result=pixel(a.root,parse_qs(url.query));code=200
            except FileNotFoundError: result={'error':'이 영상의 원픽셀 계산 결과가 아직 준비되지 않았습니다.'};code=409
            except (ValueError,KeyError,IndexError) as e:result={'error':str(e)};code=400
            except Exception:result={'error':'원픽셀 자료를 읽지 못했습니다. 서버 기록을 확인하세요.'};code=500
            body=json.dumps(result,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    ThreadingHTTPServer(('0.0.0.0',a.port),Handler).serve_forever()

if __name__=='__main__':main()
