"""Immutable, bounded interim ZIPs at the user-requested Korean deadlines."""
import argparse,hashlib,json,time,zipfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
from priority_delivery import snapshot
from axes_report import status as axes_status
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
    priority=snapshot(D,O,C)
    axes=axes_status(D,O,C)
    times=[x.get('seconds',0) for p in mesh if (x:=read(p,{})).get('status')=='PASS']
    estimate=(6-priority['completed'])*sum(times)/max(1,len(times))/60
    lines=[f'# 진행 · {now:%Y-%m-%d %H:%M} 한국 시각','',
        '1. 일별 상태',f"- 일 1: {'끝남(논문 전문 접근 제한)' if a else '진행 중, 10/28 23:00 목표'}.",
        '- 일 3: '+', '.join(f"{p} {x.get('stage','시작 전')}" for p,x in zip(['ALS','LoD2'],patch))+'. 패치 ZIP 10/28 21:01 생성·전달.',
        f'- 일 2: 메시 정리 PASS {len(times)}개. '+('진행 중' if mesh else '시작 전')+'. 10/30 09:30에 완료분을 설명용으로 제공. 전체 12:00은 원래 목표이며 완료 보장이 아님.',
        f"- 필수 R1·B173·B0 판정 끔·판 4: 정리 {priority['completed']}/6개, 사례 그림 {priority['completed_cases']}/7개 완료. "+('덧붙임 2에 따라 필수 여섯 개 추가 지표 → 새 그림 → 비교 채점 → 집계 순서. 면담 묶음 10/30 09:00.' if (C/'interview_addendum_v2.json').exists() else '추가 지표는 1단계 비교 방법 36개 다음 차례.')+' 상세: tables/priority_six.md.',
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
    if axes:
        eta=[v for v in axes['estimate_kst_excluding_resource_wait'].values() if v]
        end='확인 불가(미해결 실패 있음)' if axes.get('blocked') else eta[-1] if eta else '확인 불가'
        lines[lines.index('2. 나온 숫자 [이 발주에서 냄]'):lines.index('2. 나온 숫자 [이 발주에서 냄]')]=[
            f"- 덧붙임 네 값: {axes['completed']}/{axes['required']}개 완료, 우선 1단계 비교 방법 {axes['stage1_completed']}/{axes['stage1_required']}개. 옛 값 대조 {axes['baseline_status']}.",
            f"- 추가 지표의 남은 {len(axes['pending'])}개 예상: {end}. 남은 정리 포함, 자원 대기는 별도. 대상별 예상은 tables/axes_progress.json. 10/30 09:30에는 완료한 전·후만 포함.",'']
        if axes.get('blocked'):
            oom=sum(r.get('status')=='FAILED_OOM' or (r.get('previous_failure') or {}).get('status')=='FAILED_OOM' for r in axes['blocked'])
            lines.insert(lines.index('4. 다음 중간 묶음')-1,f"- 정리 실패·자원 보류 {len(axes['blocked'])}개(앞 실행 OOM 확인 {oom}개). 완료 표에 넣지 않음. 대상·근거는 tables/axes_progress.json과 mesh_memory_plan.json. 단계별 프로세스 분리·38 GiB 선제 중지를 적용. 처리 가능한 대상은 계속 진행.")
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
    for name in ['issues.md','메시정리와패치표_보고_v1.md','메모리_실행개선_v1.md']:
        if (D/name).exists():members.append((D/name,name))
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr('진행.md',progress(now))
        priority=snapshot(D,O,C)
        z.writestr('priority_status.json',json.dumps(priority,ensure_ascii=False,indent=2))
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
