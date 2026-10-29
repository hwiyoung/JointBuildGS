"""Standalone immutable interview ZIPs and the 09:00 KST deadline, stdlib only."""
import argparse,hashlib,json,time,zipfile,subprocess,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
O=Path('/out');D=Path('/docs');C=Path('/config');I=D/'interview_v2'
KST=timezone(timedelta(hours=9))
def read(p,default=None):return json.loads(p.read_text()) if p.exists() else default
def now():return datetime.now(KST)
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):h.update(b)
    return h.hexdigest()

def completed_artifact(path):
    rel=path.relative_to(I);tag=None
    if rel.parts[0]=='figures':
        tag='fig-'+rel.parts[1] if len(rel.parts)>2 else 'counts'
    elif rel.parts[0]=='tables':
        stem=path.stem
        if stem.startswith('figure_'):tag='fig-'+stem[len('figure_'):]
        elif stem in ['axis_curves','missing_invisible','boundary_spread','lod2_four_way']:tag='counts'
        elif stem.startswith('comparison_'):tag='comparison'
        elif stem.startswith('gaussians-'):tag=stem.removesuffix('_patches')
        elif stem.startswith('virtual-'):tag=stem.removesuffix('_walls').removesuffix('_missing_reclassified')
    return tag is None or read(I/'status'/(tag+'.json'),{}).get('status') in ['PASS','PARTIAL']

def progress():
    cfg=read(C/'interview_addendum_v2.json');axes=read(D/'tables/axes_progress.json',{})
    jobs=read(I/'jobs.json',{'jobs':[]})['jobs'];done=[];left=[]
    for j in jobs:
        r=read(I/'status'/(j['tag']+'.json'),{})
        (done if r.get('status') in ['PASS','PARTIAL','UNAVAILABLE','WAIT_RESOURCE_REVIEW'] else left).append((j,r))
    six=[]
    for site in ['B0_b10','B173nb_b10','R1rep_b10']:
        for r in ['nojudge_ALS_s0','lt_dynnow_ALS_s0']:
            key=f'{site}__ALS__{r}';v=read(D/'tables/axes'/(key+'.json'),{})
            six.append((key,v.get('status')=='PASS'))
    plan=read(D/'tables/mesh_memory_plan.json',{'rows':[]})
    held=[r['key'] for r in plan['rows'] if r.get('disposition')=='WAIT_RESOURCE_REVIEW']
    frozen=[r['key'] for r in read(C/'mesh_targets_v1.json')['targets'] if r['status']=='UNAVAILABLE_FROZEN_STOP']
    target=set(cfg['comparison_targets']);n_six=sum(x[1] for x in six)
    mesh_done=sum(read(p,{}).get('status')=='PASS' for p in (D/'tables/meshes').glob('*.json'))
    rates={}
    for ap in (D/'tables/axes').glob('*.json'):
        ar=read(ap,{});mr=read(D/'tables/meshes'/ap.name,{})
        if ar.get('status')!='PASS' or 'cleanup' not in mr:continue
        triangles=mr['cleanup']['before_triangles']+mr['cleanup']['after_triangles']
        seconds=ar['before']['seconds']+ar['after']['seconds']
        site=ap.stem.split('__')[0]
        if triangles:rates[site]=max(rates.get(site,0),seconds/triangles)
    remaining=0
    for key,complete in six:
        if complete:continue
        mr=read(D/'tables/meshes'/(key+'.json'),{});cl=mr.get('cleanup',{})
        triangles=cl.get('before_triangles',0)+cl.get('after_triangles',0)
        remaining+=60+triangles*rates.get(key.split('__')[0],max(rates.values(),default=0))
    eta=now()+timedelta(seconds=remaining);fmt=lambda t:t.strftime('%m/%d %H:%M')
    terminal=['PASS','PARTIAL','UNAVAILABLE','WAIT_RESOURCE_REVIEW','FAILED']
    phase_done=lambda tags:bool(tags) and all(read(I/'status'/(t+'.json'),{}).get('status') in terminal for t in tags)
    figures_done=phase_done([j['tag'] for j in jobs if j['tag'].startswith('fig-')])
    counts_done=phase_done(['counts']+[f'gaussians-{s}-{p}' for s in ['b0','b173','r1'] for p in ['nojudge','lt_dynnow']])
    figure_eta=eta if figures_done else eta+timedelta(hours=2)
    expected=f"필수 여섯 개 {fmt(eta) if n_six<6 else '완료'}, 그림 {'시도 종료' if figures_done else fmt(figure_eta)}, 집계 {'시도 종료' if counts_done else fmt(figure_eta+timedelta(hours=1))}"
    pending_text=f'{len(left)}개' if jobs else '그림·비교·집계·가상 메시 대기'
    lines=[f'# 진행 · {now():%m/%d %H:%M} KST',
        f"- 완료: 메시 정리·기존 평가 {mesh_done}/60, 추가 네 값 {axes.get('completed',0)}/60; 필수 여섯 개 추가 지표 {n_six}/6. 새 작업 {sum(r.get('status')=='PASS' for _,r in done)}개 완료, {sum(r.get('status')!='PASS' for _,r in done)}개 부분·확인 불가.",
        f"- 남음: {pending_text}. 09:00에 완료분 납품. 전체 종료 시각은 메모리 보류 때문에 확인 불가.",
        f'- 예상 KST: {expected}(지역별 관측 최대 초/삼각형으로 보수 추정; 실행 중도 한 개분 포함, 잠금·메모리 대기 제외). GPU 시각 미정.',
        '- 차례: 현재 R1 둘째 씨앗 → 필수 여섯 개 → 그림 → 비교 채점 → 집계 → 나머지.',
        f'- 메모리 보류 {len(held)}개. *는 이번 비교 채점 대상:']
    lines += [('  * ' if k in target else '  - ')+k for k in held]
    lines += ['- 원본 없음: '+', '.join(frozen),
        '- 부분·보류는 완료 수치가 아니다. 상세 이름·상태: interview_v2/status 및 tables/comparison_status.json.',
        '- 패치 표의 기준 면 수 불일치는 미해결. 새 영역·가시성 표는 만들지 않음. 사진 구조 판단은 사람 확인 전 모름.',
        '- 92.3%는 기존 표의 본 방법 두 씨앗 평균. 한 씨앗 값과 혼동하지 않음.',
        'scientific_verdict: null']
    text='\n'.join(lines)+'\n';assert len(text)<=2000,len(text)
    I.mkdir(parents=True,exist_ok=True);tmp=I/'진행.md.tmp';tmp.write_text(text);tmp.replace(I/'진행.md')
    return text

def package():
    text=progress();folder=O/'deliveries';folder.mkdir(exist_ok=True)
    p=folder/f'PHD-MAIN-MESHPATCH-v1_면담빈칸_{now():%m%d-%H%M}.zip'
    if p.exists():return p
    files=[]
    for base,arc in [(I,'interview_v2'),(D/'tables','tables')]:
        for f in sorted(base.rglob('*')):
            if f.is_file() and f.suffix in ['.json','.md','.csv','.png','.glb'] and '.tmp' not in f.name:
                if base==I and not completed_artifact(f):continue
                files.append((f,arc+'/'+str(f.relative_to(base))))
    for name in ['덧붙임2_적용.md','메모리_실행개선_v1.md','issues.md']:
        if (D/name).exists():files.append((D/name,name))
    scriptroot=Path('/repo/scripts/phd/main_meshpatch_v1')
    scripts=sorted(set(scriptroot.glob('interview_*.py'))|set(scriptroot.glob('run_interview*.sh')))
    for name in ['mesh_common.py','mesh_worker.py','mesh_staged.py','column_store.py','run_cpu.sh']:scripts.append(scriptroot/name)
    for f in scripts:files.append((f,'scripts/'+f.name))
    for f in sorted(C.glob('interview_*json')):files.append((f,'configs/'+f.name))
    temp=p.with_suffix('.zip.tmp');manifest=[]
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr('진행.md',text)
        for f,name in files:
            b=f.read_bytes();z.writestr(name,b);manifest.append(dict(name=name,bytes=len(b),sha256=hashlib.sha256(b).hexdigest()))
        z.writestr('manifest.json',json.dumps(dict(files=manifest,scientific_verdict=None),ensure_ascii=False,indent=2))
    assert temp.stat().st_size<400_000_000,'split required before delivery'
    with zipfile.ZipFile(temp) as z:
        assert z.namelist()[0]=='진행.md' and z.testzip() is None
        for r in manifest:assert hashlib.sha256(z.read(r['name'])).hexdigest()==r['sha256']
    temp.replace(p);h=digest(p);p.with_suffix('.zip.sha256').write_text(h+'  '+p.name+'\n')
    receipt=dict(path=str(p),bytes=p.stat().st_size,sha256=h,members_verified=len(manifest),created_at=now().isoformat(),scientific_verdict=None)
    (O/'status'/f'interview_delivery_{now():%m%d-%H%M}.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False),flush=True);return p

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--package',action='store_true');ap.add_argument('--schedule',action='store_true');a=ap.parse_args()
    if a.schedule:
        cfg=read(C/'interview_addendum_v2.json');deadline=datetime.fromisoformat(cfg['deadline_kst'])
        trigger=deadline-timedelta(seconds=60)
        (O/'status/interview_delivery_schedule.json').write_text(json.dumps(dict(status='RUNNING',deadline=cfg['deadline_kst'],packaging_trigger=trigger.isoformat(),scientific_verdict=None),indent=2)+'\n')
        while now()<trigger:time.sleep(min(30,max(.1,(trigger-now()).total_seconds())))
        # Read the current reporting implementation; computation definitions stay frozen separately.
        subprocess.run([sys.executable,__file__,'--package'],check=True)
        (O/'status/interview_delivery_schedule.json').write_text(json.dumps(dict(status='COMPLETE',at=now().isoformat(),scientific_verdict=None),indent=2)+'\n')
    elif a.package:package()
    else:print(progress())

if __name__=='__main__':main()
