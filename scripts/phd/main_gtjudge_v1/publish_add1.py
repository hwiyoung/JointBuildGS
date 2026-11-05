"""Compact factual reports, immutable ZIPs and explicit-path commit/push events."""
import sys,os,json,csv,hashlib,subprocess,zipfile,fcntl,re,difflib
from pathlib import Path
from gpu_job import R,O,D,C,dump,now
SITES=['R1rep_b10','B173nb_b10','B0_b10'];PRIORS=['ALS','LoD2']
ALLOWED=['configs/phd/main_gtjudge_v1','scripts/phd/main_gtjudge_v1','docs/experiments/phd/main_gtjudge_v1','src/phd/forks/GeoGS-conf-guided-v1-r25']
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def rows(p):return json.loads(p.read_text())['rows'] if p.exists() else []
def fmt(x):return '확인 불가' if x is None else f'{x:.2f}' if isinstance(x,float) else str(x)
def csvwrite(p,rr):
    dump(p.with_suffix('.json'),dict(rows=rr,scientific_verdict=None));p.parent.mkdir(parents=True,exist_ok=True)
    with p.with_suffix('.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rr for k in r)));w.writeheader();w.writerows(rr)
def training(site,prior,arm):
    run=O/'runs'/site/f'{"gt" if arm=="A1" else "gtfs"}_{prior}_s0';rec=json.loads((run/'receipt.json').read_text());out=dict(site=site,prior=prior,arm=arm,status=rec['status'],iterations=0,psnr_test=None,psnr_train=None,lambda_fs=None,calibration_iteration=None,opacity_pruned_recent_targets=None,scientific_verdict=None)
    if rec.get('attempts'):
        a=run/f"attempt{rec['attempts'][-1]['attempt']}";mon=a/'model/target_monitor';curve=mon/'curve.jsonl'
        if curve.exists():
            rr=[json.loads(l) for l in curve.read_text().splitlines() if l.strip()];out.update(iterations=rr[-1]['iteration'] if rr else 0,gaussians=rr[-1]['gaussians'] if rr else None,training_seconds=rec['attempts'][-1]['seconds'])
        if (a/'train.log').exists():
            with (a/'train.log').open(errors='replace') as f:
                for line in f:
                    if '[ITER 30000]' in line and 'PSNR' in line:
                        m=re.search(r'Evaluating (test|train).*PSNR ([0-9.eE+-]+)',line)
                        if m:out['psnr_'+m[1]]=float(m[2])
        if (mon/'preserve_freespace_lambda.json').exists():
            v=json.loads((mon/'preserve_freespace_lambda.json').read_text());out.update(lambda_fs=v['lambda_fs'],calibration_iteration=v['iteration'])
        if (mon/'preserve_freespace.jsonl').exists():
            rr=[json.loads(l) for l in (mon/'preserve_freespace.jsonl').read_text().splitlines()];dump(D/'tables/stage3'/f'{site}__{prior}__{arm}_freespace.json',dict(rows=rr,scientific_verdict=None));out['opacity_pruned_recent_targets']=rr[-1]['opacity_pruned_recent_targets'] if rr else None
        for iteration in [7000,15000,30000]:
            p=mon/f'health_{iteration}.json'
            if p.exists():dump(D/'tables/stage3'/f'{site}__{prior}__{arm}_health{iteration}.json',json.loads(p.read_text()))
    metric=next((x for x in rows(D/'tables/stage1'/f'{site}__{prior}_metrics.json') if x['method']==arm and x['case_id']=='all'),None)
    out['scene_accuracy_pct']=metric['accuracy_pct'] if metric else None
    csvwrite(D/'tables/stage3'/f'{site}__{prior}__{arm}_training.csv',[out]);return out

def reports():
    old=D/'status.json';archive=D/'provenance/preflight_status_1923967f.json'
    if old.exists() and not archive.exists():archive.write_bytes(old.read_bytes());(D/'provenance/preflight_report_1923967f.md').write_bytes((D/'보고.md').read_bytes())
    gate=json.loads((D/'단계0_판정.json').read_text()) if (D/'단계0_판정.json').exists() else None
    states=[];comparisons=[];upper=[];feature=[];deltas=[]
    for site in SITES:
        for prior in PRIORS:
            stem=f'{site}__{prior}';metric=rows(D/'tables/stage1'/f'{stem}_metrics.json');row=dict(site=site,prior=prior)
            for m in ['FINALTRAIN_30000','A1','A2','gt_judgment_mesh']:
                x=next((x for x in metric if x['method']==m and x['case_id']==2),None);row[m]=x['completeness_pct'] if x else None
            comparisons.append(row);upper.extend(rows(D/'tables/stage1'/f'{stem}_upper.json'))
            p=D/'tables/stage2'/f'{stem}_summary.json'
            if p.exists():feature.append(json.loads(p.read_text()))
            oldrows=rows(D/'tables/stage0'/f'{stem}.json')
            for x in oldrows:
                if x['distance']!='normal_line' or x['n_gt']<1000 or x['case_id']=='all':continue
                y=next((r for r in oldrows if r['distance']=='nearest_comparison' and r['method']==x['method'] and r['case_id']==x['case_id']),None)
                if y:deltas.append(dict(site=site,prior=prior,method=x['method'],case_id=x['case_id'],normal_pct=x['completeness_pct'],nearest_pct=y['completeness_pct'],delta_pp=x['completeness_pct']-y['completeness_pct']))
            for arm in ['A1','A2']:
                p=O/'runs'/site/f'{"gt" if arm=="A1" else "gtfs"}_{prior}_s0'/'receipt.json'
                states.append(training(site,prior,arm) if p.exists() else dict(site=site,prior=prior,arm=arm,status='PENDING',iterations=0))
    csvwrite(D/'tables/run_status.csv',states);csvwrite(D/'tables/preservation_comparison.csv',comparisons)
    top=sorted(deltas,key=lambda x:abs(x['delta_pp']),reverse=True)[:3];csvwrite(D/'tables/stage0_largest_differences.csv',top)
    complete=sum(x['status']=='TRAINING_COMPLETE_30000' for x in states);done=sum(x['status']!='PENDING' for x in states)
    state=dict(at=now(),status='CONTINUING_ADDENDUM1' if done<12 else 'STAGE3_FINISHED',stage0=gate['status'] if gate else 'RUNNING',training_runs_finished=done,training_runs_completed_30000=complete,scientific_verdict=None);dump(D/'status.json',state);dump(O/'STATUS.json',state)
    text=['# PHD-MAIN-GTJUDGE-v1 정답 판단 진단','',f"단계 0: **{state['stage0']}**. "+('단계 1·2·3의 칸은 여섯 장면 모두 RECOUNT 최근접 칸이다.' if gate and gate['global_case_basis']!='normal_line' else '칸은 법선 측정선 거리로 나눴다.'),'`scientific_verdict: null`. 참값은 점군 그대로 사용했다.','',
        f'학습 종료 {done}/12판, 30,000회 완료 {complete}/12판. 미완료 값을 채워 넣지 않았다.','',
        '## 두 거리의 완전성 차이가 큰 세 항목','', '| 장면 | 사전 정보 | 방법 | 경우 | 법선 % | 최근접 % | 차이 pp |','|---|---|---|---|---:|---:|---:|']
    for x in top:text.append('| '+' | '.join(fmt(x[k]) for k in ['site','prior','method','case_id','normal_pct','nearest_pct','delta_pp'])+' |')
    text+=['','## 본 방법 판단 맞음과 패치 다수결 상한','', '| 장면 | 사전 정보 | 경우 | 참값 행 | 본 방법 % | 다수결 상한 % |','|---|---|---|---:|---:|---:|']
    for x in upper:
        if x['case_id'] in [0,1,2,4]:text.append('| '+' | '.join((fmt(x[k])+(' · 적음' if k=='n_gt' and x[k]<1000 else '')) for k in ['site','prior','case_id','n_gt','method_correct_pct','majority_upper_pct'])+' |')
    text+=['','## 보존 칸 구성','', '| 장면 | 사전 정보 | 행 | 무늬 없음 % | 가장자리 % | 무늬 확인 불가 행 | 사진 지지 보존 % |','|---|---|---:|---:|---:|---:|---:|']
    for x in feature:text.append('| '+' | '.join(map(fmt,[x['site'],x['prior'],x['n_gt'],100*x['textureless_n']/x['n_gt'] if x['n_gt'] else None,100*x['edge_n']/x['n_gt'] if x['n_gt'] else None,x['texture_unavailable_n'],x['photo_supported_preserve_pct']]))+' |')
    text+=['','## 보존 칸 완전성','', '| 장면 | 사전 정보 | FINALTRAIN % | A-1 % | A-2 % | 정답 판단 조합 메시 % |','|---|---|---:|---:|---:|---:|']
    for x in comparisons:text.append('| '+' | '.join(map(fmt,x.values()))+' |')
    text+=['','기대와 다른 항목·실행 문제는 `issues.md`, 각 단계 계산은 `tables/stage0`, `tables/stage1`, `tables/stage2`, `tables/stage3`, 그림과 출처 JSON은 `figures`에 있다.','',
        '완전성은 AXES71 PCA 법선 측정선, 정확성은 원래 참값 점군의 가는 원기둥 안 최소 절댓값 축 거리다. 평균 거리는 사용하지 않았다. 장면별 반지름·제외 수는 거리 receipt에 기록했다.']
    report='\n'.join(text)+'\n';assert len(report)<10000;(D/'보고.md').write_text(report)
    return states,comparisons

def run_report(site,prior,arm):
    rec=training(site,prior,arm);stem=f'{site}__{prior}';rr=rows(D/'tables/stage1'/f'{stem}_metrics.json');rr=[r for r in rr if r['method']==arm]
    t=[f'# {site} · {prior} · {arm} — 정답 판단 진단','',f"상태: {rec['status']}; 반복 {rec['iterations']:,}. scientific_verdict: null.",'',f"λ_fs={fmt(rec['lambda_fs'])}, 결정 반복={fmt(rec['calibration_iteration'])}; 최근 100회 대상 중 불투명도 정리 수={fmt(rec['opacity_pruned_recent_targets'])}.",f"장면 정확성 {fmt(rec['scene_accuracy_pct'])}%, PSNR(test) {fmt(rec['psnr_test'])} dB.",'','| 경우 | 행 | 완전성 % | 정확성 % | 먼 만남 % | 면 없음 % |','|---|---:|---:|---:|---:|---:|']
    for r in rr:
        t.append('| '+' | '.join((fmt(r[k])+(' · 적음' if k=='n_gt' and r[k]<1000 else '')) for k in ['case_id','n_gt','completeness_pct','accuracy_pct','gt_far_hit_pct','gt_no_surface_pct'])+' |')
    t+=['',f'표: tables/stage1/{stem}_metrics.csv; tables/stage3/{stem}__{arm}_training.csv.',f'그림: figures/{stem}_{arm}_section.png, _preservation_maps.png, _mesh_views.png.','보존 칸 분할 표: tables/stage2/'+stem+'.csv.']
    s='\n'.join(t)+'\n';assert len(s)<2000;(D/f'결과_{site}_{prior}_{arm}.md').write_text(s)

def changed_lines():
    a=R/'src/phd/forks/GeoGS-conf-guided-v1-r23';b=R/'src/phd/forks/GeoGS-conf-guided-v1-r25';chunks=[];rr=[]
    for p in sorted(b.rglob('*.py')):
        relative=p.relative_to(b);old=a/relative;before=old.read_text().splitlines(True) if old.exists() else [];after=p.read_text().splitlines(True)
        if before!=after:
            chunks.extend(difflib.unified_diff(before,after,fromfile='r23/'+str(relative),tofile='r25/'+str(relative)));rr.append(dict(path=str(relative),r25_sha256=sha(p)))
    (D/'provenance/r23_r25.diff').write_text(''.join(chunks));dump(D/'provenance/r25_changed_files.json',dict(files=rr,scientific_verdict=None))

def package(label):
    out=O/'delivery/addendum1';out.mkdir(parents=True,exist_ok=True);zipname='PHD-MAIN-GTJUDGE-v1'+('_'+label if label else '')+'.zip';target=out/zipname
    if target.exists():return json.loads(target.with_suffix('.json').read_text())
    files=[]
    for base in [C,R/'scripts/phd/main_gtjudge_v1',D]:
        for p in base.rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and '/delivery/' not in str(p):files.append((p,str(p.relative_to(R))))
    for p in (O/'targets_gt').glob('*.npz'):files.append((p,'payload/targets_gt/'+p.name))
    for p in (O/'targets_gt').glob('*.json'):files.append((p,'payload/targets_gt/'+p.name))
    for p in (O/'scenes').glob('*/distances/*.json'):files.append((p,'payload/'+str(p.relative_to(O))))
    manifest=[]
    for p in O.rglob('receipt.json'):
        if 'delivery' not in p.parts:manifest.append(dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size))
    manifest_bytes=(json.dumps(dict(receipts=manifest,scientific_verdict=None),ensure_ascii=False,indent=2)+'\n').encode();sums=[]
    tmp=target.with_suffix('.tmp')
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p,name in sorted(files,key=lambda x:x[1]):data=p.read_bytes();z.writestr(name,data);sums.append(hashlib.sha256(data).hexdigest()+'  '+name)
        z.writestr('payload_receipts.json',manifest_bytes);sums.append(hashlib.sha256(manifest_bytes).hexdigest()+'  payload_receipts.json');z.writestr('SHA256SUMS','\n'.join(sums)+'\n')
    tmp.rename(target)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for line in z.read('SHA256SUMS').decode().splitlines():digest,name=line.split('  ',1);assert hashlib.sha256(z.read(name)).hexdigest()==digest
        entries=len(z.namelist())
    digest=sha(target);target.with_suffix('.zip.sha256').write_text(digest+'  '+target.name+'\n')
    rec=dict(at=now(),package=str(target),bytes=target.stat().st_size,entries=entries,sha256=digest,CRC='PASS',member_sha256='PASS',scientific_verdict=None);dump(target.with_suffix('.json'),rec);dump(D/'delivery/addendum1'/f'{label or "all"}.json',rec);return rec

def commit(label):
    # Explicit paths only, and --only prevents any unrelated staged files entering this event.
    if label=='단계01' or not label:paths=ALLOWED
    else:
        paths=['docs/experiments/phd/main_gtjudge_v1/보고.md','docs/experiments/phd/main_gtjudge_v1/status.json','docs/experiments/phd/main_gtjudge_v1/tables/run_status.csv','docs/experiments/phd/main_gtjudge_v1/tables/run_status.json','docs/experiments/phd/main_gtjudge_v1/tables/preservation_comparison.csv','docs/experiments/phd/main_gtjudge_v1/tables/preservation_comparison.json','docs/experiments/phd/main_gtjudge_v1/issues.md','configs/phd/main_gtjudge_v1']
        if label=='단계2':
            candidates=list((D/'tables/stage2').glob('*'))+list((D/'figures').glob('*_stage2_*'))
        else:
            site,prior,arm=label.rsplit('_',2);stem=site+'__'+prior
            candidates=[D/f'결과_{site}_{prior}_{arm}.md']+list((D/'tables/stage3').glob(stem+'__'+arm+'*'))+list((D/'figures').glob(stem+'_'+arm+'*'))+list((D/'tables/stage1').glob(stem+'_metrics.*'))+list((D/'tables/stage2').glob(stem+'*'))
        candidates.append(D/'delivery/addendum1'/f'{label}.json');paths += [str(p.relative_to(R)) for p in candidates if p.exists()]
    subprocess.run(['git','add','--',*paths],cwd=R,check=True)
    changed=subprocess.run(['git','diff','--cached','--quiet','--',*paths],cwd=R).returncode
    if changed:subprocess.run(['git','commit','--only','-m',f'PHD-MAIN-GTJUDGE-v1 addendum1 {label or "final"}','--',*paths],cwd=R,check=True)
    subprocess.run(['git','push','origin','HEAD:exp/main-experiment'],cwd=R,check=True)
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()

def main(label='',site=None,prior=None,arm=None):
    lock=O/'queue/publish.lock';lock.parent.mkdir(exist_ok=True)
    with lock.open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        if site:label=f'{site}_{prior}_{arm}';run_report(site,prior,arm)
        reports();changed_lines()
        from cpu_queue import cpu
        qa_tag=re.sub(r'[^A-Za-z0-9_.-]+','-',label or 'all').strip('-') or 'all'
        cpu('qa-'+qa_tag,'qa_panels.py',label or 'all')
        rec=package(label);rec['commit']=commit(label)
        with (O/'queue/events.jsonl').open('a') as events:events.write(json.dumps(dict(event='PACKAGE',label=label,**rec),ensure_ascii=False)+'\n')
        print('PACKAGE_READY',json.dumps(rec,ensure_ascii=False),flush=True)
if __name__=='__main__':main(*sys.argv[1:])
