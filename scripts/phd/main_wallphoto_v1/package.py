"""Immutable <=100 MB scheduled snapshots; only public results enter archives."""
import argparse,datetime as dt,time,zipfile,hashlib
from common import *

def progress(due):
    inv=load(O/'inventory.json') if (O/'inventory.json').exists() else {}
    st=load(O/'status.json') if (O/'status.json').exists() else dict(state='RESOURCE_WAIT')
    summary=next((load(O/x) for x in ['full_summary.json','pilot_summary.json'] if (O/x).exists()),{})
    timing=load(O/'timing_first_building.json') if (O/'timing_first_building.json').exists() else {}
    gate=load(O/'gates/projection.json') if (O/'gates/projection.json').exists() else dict(status='미실행')
    first=inv.get('pilot',[]);patches=sum(x['patches'] for x in first);area=sum(x['area_m2'] for x in first)
    txt=f'''# 진행

기준 시각: {due} / 작성: {now()}

1. 끝난 것: 설정 잠금, 원본 수식·설정 동일성 검증, 벽 패치 목록. 현재 {st.get('state','확인 불가')}. 끝날 예상 시각은 첫 건물 시간 기록 뒤 갱신. 시작 전 항목은 투영·그림·전체 확대 가운데 완료 기록이 없는 항목.

2. 지금까지 나온 숫자 [이 발주에서 냄]

| 항목 | 값 |
|---|---:|
| 시험 건물 | {len(first)} |
| 시험 벽 패치 | {patches} |
| 시험 벽 넓이 m² | {area:.6f} |
| 계산 완료 점 | {summary.get('points',0)} |
| 계산 완료 패치 | {summary.get('patches',0)} |
| 끝난 타일 | {summary.get('tiles',0)} |
| 사진 3장 이상 넓이 비율 | {summary.get('three_or_more_fraction','확인 불가')} |
| 전체 CPU 시간 어림 | {timing.get('full_cpu_hours','확인 불가')} |

3. 멈춤 조건: 투영 상태 {gate.get('status')}. 메모리 입장 조건과 MESHPATCH 우선순위 때문에 대기할 수 있으며 대기 기록을 보존한다. 계산 전에는 사진 수와 판단 넓이를 채우지 않는다. 미계산 패치는 -1이다. GPU 시간은 확인 불가. 패치 수는 발주와 모두 같았다. 실행 셸 종료 오류와 자원 프로필은 issues.md에 적었다. 이전 묶음과의 값 변화는 각 묶음 시각의 표를 비교한다.

4. 다음 묶음: 완료된 점·타일의 사진 분포, 판단 넓이, 투영 점검과 단계 나 조건. 투영 실패 시 계산을 멈추고 사용자 지시를 기다린다.

scientific_verdict: null
'''
    assert len(txt)<=2000
    return txt

@locked_public
def package(label,due=None):
    folder=O/'handover';folder.mkdir(parents=True,exist_ok=True)
    stem='PHD-MAIN-WALLPHOTO-v1_'+label;dest=folder/(stem+'.zip')
    if dest.exists():return dest
    txt=progress(due or now());(D/'진행.md').write_text(txt);(D/'progress.md').write_text(txt)
    entries=[]
    for root,prefix in [(C,'configs'),(S,'scripts')]:
        for p in sorted(root.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:entries.append((p,prefix+'/'+str(p.relative_to(root))))
    for p in sorted(D.rglob('*')):
        if not p.is_file() or 'received' in p.parts or 'validation' in p.parts or p.suffix=='.zip' or p.name in ['진행.md','progress.md']:continue
        entries.append((p,'docs/'+str(p.relative_to(D))))
    for sub in ['points','patches']:
        for p in sorted((O/sub).glob('*.npz')):entries.append((p,sub+'/'+p.name))
    # Store exact captured bytes, not a later mutable file; each part starts with progress.
    parts=[];buf=[];size=0
    for p,name in entries:
        data=p.read_bytes()
        if len(data)>97_000_000:raise RuntimeError('single file exceeds archive limit: '+str(p))
        if buf and size+len(data)>97_000_000:parts.append(buf);buf=[];size=0
        buf.append((name,data));size+=len(data)
    parts.append(buf);records=[]
    for i,items in enumerate(parts):
        path=dest if i==0 else folder/(stem+f'_part{i+1:03d}.zip');tmp=path.with_suffix('.pending')
        hashes=[hashlib.sha256(txt.encode()).hexdigest()+'  진행.md']
        with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            z.writestr('진행.md',txt)
            for name,data in items:z.writestr(name,data);hashes.append(hashlib.sha256(data).hexdigest()+'  '+name)
            z.writestr('SHA256SUMS','\n'.join(hashes)+'\n')
        assert tmp.stat().st_size<100_000_000
        with zipfile.ZipFile(tmp) as z:
            assert z.namelist()[0]=='진행.md' and z.testzip() is None
            assert not any('/holdout/' in name or name.startswith('holdout/') for name in z.namelist())
            for line in z.read('SHA256SUMS').decode().splitlines():
                digest,name=line.split('  ',1);assert hashlib.sha256(z.read(name)).hexdigest()==digest
        tmp.replace(path);records.append(dict(name=path.name,bytes=path.stat().st_size,sha256=sha(path),crc='PASS'))
    dump(folder/(stem+'.json'),dict(at=now(),due_kst=due,files=records,scientific_verdict=None))
    print('packaged',clean(records),flush=True);return dest

def watch():
    cfg=load(C/'wallphoto_v1.json');labels=['중간_1028-2300','시험','중간_1029-1400','중간_1029-1800','중간_1030-0930']
    for due,label in zip(cfg['wall_task']['schedules_kst'],labels):
        target=dt.datetime.fromisoformat(due)
        while dt.datetime.now(dt.timezone.utc)<target:
            dump(O/'schedule_status.json',dict(at=now(),next_due=due,next_label=label,status='WAITING',scientific_verdict=None));time.sleep(30)
        package(label,due)
    dump(O/'schedule_status.json',dict(at=now(),status='COMPLETE',scientific_verdict=None))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--watch',action='store_true');ap.add_argument('--label');a=ap.parse_args()
    if a.watch:watch()
    else:package(a.label or '현황')
