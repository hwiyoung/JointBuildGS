"""Immutable, bounded interim ZIPs at the user-requested Korean deadlines."""
import argparse,hashlib,json,time,zipfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
KST=timezone(timedelta(hours=9));O=Path('/out');D=Path('/docs');C=Path('/config')
def read(p,default=None):
    return json.loads(p.read_text()) if p.exists() else default
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()
def progress(now):
    a=read(O/'status/task1.json',{});patch=[read(O/'status'/f'patch_{p}.json',{}) for p in ['ALS','LoD2']]
    mesh=list((D/'tables/meshes').glob('*.json'))
    lines=[f'# 진행 · {now:%Y-%m-%d %H:%M} 한국 시각','',
        '1. 일별 상태',f"- 일 1: {'끝남(논문 전문 접근 제한)' if a else '진행 중, 10/28 23:00 목표'}.",
        '- 일 3: '+', '.join(f"{p} {x.get('stage','시작 전')}" for p,x in zip(['ALS','LoD2'],patch))+'. 패치 표 10/29 18:00 목표.',
        f'- 일 2: 대상별 기록 {len(mesh)}건. '+('진행 중' if mesh else '시작 전')+'. 10/30 09:30까지 끝난 대상을 설명용으로 제공, 전체 12:00 목표.',
        '', '2. 나온 숫자 [이 발주에서 냄]','| 일 | 대상 | 패치 수 | 넓이 m² | 상태 |','|---|---|---:|---:|---|']
    for prior in ['ALS','LoD2']:
        s=read(D/'tables'/f'patch_{prior}_table.json')
        if s:lines.append(f"| 패치 표 | {prior} | {s['patches']} | {s['area_m2']:.6f} | {s['status']} |")
    lines+=['','3. 멈춤·차이·숫자 변경',
        '- 학습 없음. 기존 메시·표·코드는 덮어쓰지 않음. 큰 CPU 작업은 공유 잠금과 56 GiB/60초 입장 조건 적용.',
        '- 영역 v3와 넓히기 v2의 패치 기하·표본 범위가 다름. 사용자 결정에 따라 확인되는 코드만 붙이고, MVS 없음·사전 정보 τ 안 여부·미연결 까닭을 추가. 새 가시성·영역 계산 없음.',
        '- 면 수 등 기준 대조는 tables/patch_*_tracka_check에 기록. 불일치가 있으면 PASS로 표시하지 않음.',
        '- 앞 중간 묶음의 값은 해당 ZIP에 보존. 이번 파일의 입력 해시·분모가 기준이며 숫자 수정은 issues.md에 기록.',
        '', '4. 다음 중간 묶음',
        '- 패치 표 대조 및 정리 전·후 메시 표의 새 완료분. 메모리 입장이 늦으면 완료 예상 시각을 다시 기록.',
        '', 'scientific_verdict: null']
    s='\n'.join(lines)+'\n';assert len(s)<=2000
    return s
def package(at=None):
    now=at or datetime.now(KST);folder=O/'deliveries';folder.mkdir(exist_ok=True)
    p=folder/f'PHD-MAIN-MESHPATCH-v1_중간_{now:%m%d-%H%M}.zip'
    if p.exists():return p
    temp=p.with_suffix('.zip.tmp');members=[]
    for f in sorted((D/'tables').rglob('*')):
        if f.is_file() and f.suffix in ['.md','.json']:members.append((f,'tables/'+str(f.relative_to(D/'tables'))))
    for f in sorted((D/'figures').rglob('*')) if (D/'figures').exists() else []:
        if f.is_file() and f.suffix in ['.png','.jpg','.glb']:members.append((f,'figures/'+str(f.relative_to(D/'figures'))))
    for name in ['issues.md','메시정리와패치표_보고_v1.md']:
        if (D/name).exists():members.append((D/name,name))
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr('진행.md',progress(now))
        manifest=[]
        for f,name in members:
            data=f.read_bytes();z.writestr(name,data);manifest.append(dict(name=name,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
        z.writestr('manifest.json',json.dumps(dict(files=manifest,scientific_verdict=None),ensure_ascii=False,indent=2))
    assert temp.stat().st_size<100_000_000,'interim ZIP exceeded 100 MB'
    with zipfile.ZipFile(temp) as z:
        assert z.namelist()[0]=='진행.md';assert z.testzip() is None
    temp.replace(p);h=sha(p);p.with_suffix('.zip.sha256').write_text(h+'  '+p.name+'\n')
    print(json.dumps(dict(file=str(p),sha256=h,bytes=p.stat().st_size,created_at=datetime.now(KST).isoformat()),ensure_ascii=False),flush=True)
    return p
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--schedule',action='store_true');a=ap.parse_args()
    if not a.schedule:package();return
    cfg=read(C/'meshpatch_v1.json');dates=[datetime.fromisoformat(s) for s in cfg['schedule_kst']]
    (O/'status').mkdir(exist_ok=True)
    state=O/'status/delivery_schedule.json';state.write_text(json.dumps(dict(status='RUNNING',schedule=cfg['schedule_kst'],scientific_verdict=None),indent=2)+'\n')
    for target in dates:
        while datetime.now(KST)<target:time.sleep(min(30,max(.1,(target-datetime.now(KST)).total_seconds())))
        package(target)
    state.write_text(json.dumps(dict(status='COMPLETE',schedule=cfg['schedule_kst'],scientific_verdict=None),indent=2)+'\n')
if __name__=='__main__':main()
