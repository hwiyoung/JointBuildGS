"""Immutable <=100 MB scheduled snapshots; only public results enter archives."""
import argparse,datetime as dt,time,zipfile,hashlib
from common import *

def progress(due):
    inv=load(O/'inventory.json') if (O/'inventory.json').exists() else {}
    st=load(O/'status.json') if (O/'status.json').exists() else dict(state='RESOURCE_WAIT')
    summary=next((load(O/x) for x in ['full_summary.json','pilot_summary.json'] if (O/x).exists()),{})
    timing=load(O/'timing_first_building.json') if (O/'timing_first_building.json').exists() else {}
    gate=load(O/'gates/projection.json') if (O/'gates/projection.json').exists() else dict(status='미실행')
    replay=load(O/'gates/independent_replay.json') if (O/'gates/independent_replay.json').exists() else {}
    stage='전체' if (O/'full_summary.json').exists() else '시험'
    expected=timing.get('full_cpu_hours','확인 불가')
    first=inv.get('pilot',[]);patches=sum(x['patches'] for x in first);area=sum(x['area_m2'] for x in first)
    txt=f'''# 진행

기준 시각: {due} / 작성: {now()}

1. 끝난 것: 설정 잠금, 원본 수식·설정 동일성 검증, 벽 패치 목록. 현재 {st.get('state','확인 불가')}. 아래 완료 숫자는 {stage} 기준. 전체 시간 어림 {expected}시간이며 자원 대기·그림 시간은 별도다. 전체 시작은 full_started.json, 끝남은 full_complete.json으로 확인한다.

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

3. 멈춤 조건: 투영 상태 {gate.get('status')}. 점수 재현 {replay.get('status','미실행')}. 고정밀 유효 여부 {replay.get('float64_finite_check','미실행')}. 원본 float32가 균일한 사진 조각의 반올림 오차를 무늬로 보는 사례를 기록했다. 계산식·문턱은 보존했다. 예외는 issues.md와 independent_replay.json 참조. MESHPATCH 우선 대기 기록을 보존한다. 미계산 패치는 -1, GPU 시간은 확인 불가. 이전 묶음과의 값 변화는 각 시각의 표를 비교한다. 시험.zip의 points/patches는 동결한 7동 시험 값이다.

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
    data_root=O/'pilot_delivery' if label=='시험' and (O/'pilot_delivery/manifest.json').exists() else O
    for sub in ['points','patches']:
        for p in sorted((data_root/sub).glob('*.npz')):entries.append((p,sub+'/'+p.name))
    if data_root!=O:
        for name in ['manifest.json','벽사진확인_보고_v1.md']:entries.append((data_root/name,'pilot/'+name))
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
