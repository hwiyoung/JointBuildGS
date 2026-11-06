"""Versioned addendum delivery; original packages and measurement files stay intact."""
import re,zipfile,fcntl,difflib
from add2_host import *
SITES=['B173nb_b10','B0_b10','R1rep_b10']
def rows(p):return json.loads(p.read_text())['rows'] if p.exists() else []
def fmt(x):return '확인 불가' if x is None else f'{x:.2f}' if isinstance(x,float) else str(x)
def training(site,prior,arm):
    run=O/'runs'/site/f'{"fix" if arm=="fix" else "gt" if arm=="A1" else "gtfs"}_{prior}_s0';r=json.loads((run/'receipt.json').read_text());v=dict(site=site,prior=prior,arm=arm,status=r['status'],iterations=0,lambda_fs=None,calibration_iteration=None,opacity_pruned_recent_targets=None,psnr_test=None,scientific_verdict=None)
    if r.get('attempts'):
        a=run/f"attempt{r['attempts'][-1]['attempt']}";mon=a/'model/target_monitor';curve=mon/'curve.jsonl'
        if curve.exists():
            last=json.loads(curve.read_text().splitlines()[-1]);v.update(iterations=last['iteration'],gaussians=last['gaussians'],loss=last['loss'])
        p=mon/'preserve_freespace_lambda.json'
        if p.exists():z=json.loads(p.read_text());v.update(lambda_fs=z['lambda_fs'],calibration_iteration=z['iteration'])
        p=mon/'preserve_freespace.jsonl'
        if p.exists():
            rr=[json.loads(l) for l in p.read_text().splitlines()];v['opacity_pruned_recent_targets']=rr[-1]['opacity_pruned_recent_targets'];dump(D/'tables/addendum2/fix'/f'{site}__{prior}_{arm}_freespace.json',dict(rows=rr,scientific_verdict=None))
        if (a/'train.log').exists():
            with (a/'train.log').open(errors='replace') as f:
                for line in f:
                    if '[ITER 30000]' in line:
                        m=re.search(r'Evaluating test.*PSNR ([0-9.eE+-]+)',line)
                        if m:v['psnr_test']=float(m[1])
    metrics=rows(D/'tables/addendum2/stage1'/f'{site}__{prior}.json')
    for m in ['FINALTRAIN_30000',arm]:
        x=next((x for x in metrics if x['method']==m and x['surface']=='all' and x['case_id']=='all'),None);v[m+'_accuracy_pct']=x['accuracy_pct'] if x else None
    # Parent PSNR is copied from the existing FINALTRAIN summary, never rerendered.
    parent=D.parent/'main_finaltrain_v1/tables'/f'training_summary_{site}__{prior}.json'
    if not parent.exists():parent=D.parent/'main_finaltrain_v1/tables'/f'training_{site}__{prior}.json'
    v['FINALTRAIN_psnr_test']=None
    if parent.exists():
        parent_rows=json.loads(parent.read_text())['rows']
        logs={Path(x['training_log']) for x in parent_rows if 'training_log' in x}
        parent_run=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs'/site/f'ft_{prior}_s0'
        if not logs and (parent_run/'receipt.json').exists():
            attempts=json.loads((parent_run/'receipt.json').read_text()).get('attempts',[])
            logs={parent_run/f"attempt{x['attempt']}"/'train.log' for x in attempts if x['status']=='TRAINING_COMPLETE_30000'}
        for log in sorted(logs):
            if log.exists():
                with log.open(errors='replace') as f:
                    for line in f:
                        if '[ITER 30000]' in line:
                            match=re.search(r'Evaluating test.*PSNR ([0-9.eE+-]+)',line)
                            if match:v['FINALTRAIN_psnr_test']=float(match[1])
    v['scene_comparison']=[dict(method='FINALTRAIN',accuracy_pct=v.get('FINALTRAIN_30000_accuracy_pct'),psnr_test=v['FINALTRAIN_psnr_test']),dict(method=arm,accuracy_pct=v.get(arm+'_accuracy_pct'),psnr_test=v['psnr_test'])]
    failure=O/'queue/recovery_20261106/errors'/f'{site}__{prior}__{arm}.json'
    if failure.exists():v['postprocessing_error']=json.loads(failure.read_text())['error']
    dump(D/'tables/addendum2/fix'/f'{site}__{prior}_{arm}_training.json',v)
    fs_line='빈 공간 항 미적용(off).' if arm=='A1' else f"λ_fs {fmt(v['lambda_fs'])}; 결정 {fmt(v['calibration_iteration'])}회; 최근 대상 불투명도 정리 {fmt(v['opacity_pruned_recent_targets'])}개."
    text=[f'# {site} {prior} '+('고친 판' if arm=='fix' else arm),'',f"상태 {r['status']}; {v['iterations']}회. scientific_verdict: null.",fs_line,f"PSNR(test) {fmt(v['psnr_test'])}; 정확성 {fmt(v.get(arm+'_accuracy_pct'))}%.",'','|경우|참값 행|완전성 %|정확성 %|','|---|---:|---:|---:|']
    if failure.exists():text.insert(3,'후처리 일부 확인 불가: '+v['postprocessing_error'][:240])
    for x in metrics:
        if x['method']==arm and x['surface']=='all':text.append('|'+ '|'.join(fmt(x[k]) for k in ['case_id','n_gt','completeness_pct','accuracy_pct'])+'|')
    text+=['',f"FINALTRAIN → {arm}: 장면 정확성 {fmt(v.get('FINALTRAIN_30000_accuracy_pct'))} → {fmt(v.get(arm+'_accuracy_pct'))}%; PSNR(test) {fmt(v['FINALTRAIN_psnr_test'])} → {fmt(v['psnr_test'])} dB.",'참값은 채점과 위험 확인에만 사용. 판단·목표·빈 공간 대상·λ_fs에는 사용하지 않음.' if arm=='fix' else '정답 판단 진단 학습.','세부 값과 위험 확인: tables/addendum2/fix.']
    text='\n'.join(text)+'\n';assert len(text)<1500;(D/f'결과_{site}_{prior}_{arm}.md').write_text(text)

def reports():
    component_summaries=[]
    for site in SITES:
        components=rows(D/'tables/addendum2'/f'alt_da_components_{site}.json')
        if components:
            component_summaries.append(dict(site=site,components=len(components),preserved_area_m2=sum(x['area_m2'] for x in components if x['keep']),remaining_correction_area_m2=sum(x['area_m2'] for x in components if not x['keep']),remaining_reasons=[dict(reason=reason,components=sum(x['reason']==reason for x in components),area_m2=sum(x['area_m2'] for x in components if x['reason']==reason)) for reason in ['image_greater','equal','no_adjacent_decision']]))
    dump(D/'tables/addendum2/alt_da_summary.json',dict(rows=component_summaries,scientific_verdict=None))
    events=O/'queue/addendum2/events.jsonl'
    order=[json.loads(line) for line in events.read_text().splitlines() if json.loads(line)['event']=='TRAINING_STARTED'] if events.exists() else []
    dump(D/'tables/addendum2/execution_order.json',dict(rows=order,scientific_verdict=None))
    progress=(D/'progress.md').read_text()
    with (D/'progress.md').open('a') as handle:
        for event_row in order:
            text=f"- {event_row['at']}: 실제 발사 GPU {event_row['gpu']}: {' / '.join(event_row['job'])}."
            if text not in progress:handle.write(text+'\n')
    selection=D/'판고르기.json';s=json.loads(selection.read_text()) if selection.exists() else None
    decision=s['reason'] if s else '세 판 채점 중.'
    if s:
        notes=[]
        for variant in ['alt_na','alt_da']:
            guard=[x for x in s['checks'] if x['variant']==variant and x['used_for_guard']]
            worst=min(guard,key=lambda x:x['delta_pp'])
            passed=all(x['pass_guard'] for x in guard)
            notes.append(f"{variant}: {worst['site']} 경우 {worst['case_id']}의 최저 차이 {worst['delta_pp']:.2f}%p, 2.0%p 조건 {'통과' if passed else '불통과'}")
        decision='; '.join(notes)
    t=['# 정답 판단 학습 덧붙임 2','',f"고른 판: {s['selected'] if s else '선택 전'}. {decision}", '1부 판 고르기는 참값 채점 사용. 2부 판단·목표·빈 공간 대상·λ_fs에는 참값 미사용. scientific_verdict: null.','','|장면|경우|판 가 %|판 나 %|판 다 %|','|---|---|---:|---:|---:|---:|']
    rr=rows(D/'tables/addendum2/alternative_metrics.json')
    for site in SITES:
        for case in [0,1,2,4]:
            vals=[next((x['completeness_pct'] for x in rr if x['site']==site and x['method']==v and x['surface']=='all' and x['case_id']==case),None) for v in ['alt_ga','alt_na','alt_da']];t.append('|'+ '|'.join(map(fmt,[site,case,*vals]))+'|')
    t+=['','|R1 LoD2|본 방법 완전성 %|영상만 GS 완전성 %|','|---|---:|---:|'];rr=rows(D/'tables/addendum2/stage1/R1rep_b10__LoD2.json')
    for surface in ['roof','wall']:
        vals=[next((x['completeness_pct'] for x in rr if x['method']==m and x['surface']==surface and x['case_id']=='all'),None) for m in ['FINALTRAIN_30000','baseline_30000']];t.append('|'+ '|'.join(map(fmt,[surface,*vals]))+'|')
    t+=['','|장면|사전 정보|범위|무늬 없음 %|가장자리 %|무늬 확인 불가 %|','|---|---|---|---:|---:|---:|']
    for site in SITES:
        for prior in ['ALS','LoD2']:
            for x in rows(D/'tables/addendum2'/f'feature_comparison_{site}__{prior}.json'):
                if x['case_id'] in ['all','2']:t.append('|'+ '|'.join(fmt(x[k]) for k in ['site','prior','case_id','textureless_pct','edge_pct','texture_unknown_pct'])+'|')
    t+=['','|장면|사전 정보|FINALTRAIN %|A-2 %|고친 판 %|정답 판단 메시 %|','|---|---|---:|---:|---:|---:|']
    risks=[]
    for site in SITES:
        for prior in ['ALS','LoD2']:
            rr=rows(D/'tables/addendum2/stage1'/f'{site}__{prior}.json');vals=[next((x['completeness_pct'] for x in rr if x['method']==m and x['surface']=='all' and x['case_id']==2),None) for m in ['FINALTRAIN_30000','A2','fix','gt_judgment_mesh']];t.append('|'+ '|'.join(map(fmt,[site,prior,*vals]))+'|')
            risks.extend(x for x in rows(D/'tables/addendum2/fix'/f'{site}__{prior}_risks_and_strata.json') if x['division'] in ['image_only_in_freespace_columns','gt_over_1m_outside_target'])
    if risks:
        t+=['','|장면|사전 정보|위험 확인|참값 행|FINALTRAIN %|고친 판 %|','|---|---|---|---:|---:|---:|']
        for x in risks:t.append('|'+ '|'.join(fmt(x.get(k)) for k in ['site','prior','division','n_gt','FINALTRAIN_30000_completeness_pct','fix_completeness_pct'])+'|')
    failures=[]
    for path in sorted((O/'queue/recovery_20261106/errors').glob('*.json')):
        item=json.loads(path.read_text());failures.append(' / '.join(item['job'])+': '+item['error'][:180])
    if failures:t+=['','후처리 확인 불가(학습 완료와 구별):',*['- '+x for x in failures]]
    t+=['','실행 문제와 정의 보완은 issues.md에 기록했다. 먼저 만든 결과와 ZIP은 보존했다.'];text='\n'.join(t)+'\n';assert len(text)<8000;(D/'보고_덧붙임2.md').write_text(text)

def diff():
    a=R/'src/phd/forks/GeoGS-conf-guided-v1-r25';b=R/'src/phd/forks/GeoGS-conf-guided-v1-r26';lines=[]
    for p in sorted(b.rglob('*.py')):
        old=a/p.relative_to(b)
        if old.read_bytes()!=p.read_bytes():lines+=difflib.unified_diff(old.read_text().splitlines(True),p.read_text().splitlines(True),fromfile='r25/'+str(p.relative_to(b)),tofile='r26/'+str(p.relative_to(b)))
    (D/'provenance/r25_r26.diff').write_text(''.join(lines))

def package(label):
    target=O/'delivery/addendum2'/('PHD-MAIN-GTJUDGE-v1_'+label+'.zip');target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():return json.loads(target.with_suffix('.json').read_text())
    files=[]
    for base in [D/'tables/addendum2',D/'figures/addendum2',D/'addendum2',C]:
        files.extend((p,str(p.relative_to(R))) for p in base.rglob('*') if p.is_file())
    for p in [D/'판고르기.json',D/'보고_덧붙임2.md',D/'issues.md',D/'progress.md',D/'provenance/addendum2.txt',D/'provenance/r25_r26.diff']:
        if p.exists():files.append((p,str(p.relative_to(R))))
    files += [(p,str(p.relative_to(R))) for p in D.glob('결과_*_fix.md')]
    files += [(p,str(p.relative_to(R))) for p in (D/'verification').glob('addendum2*.json')]
    if label not in ['CPU보완','고친판']:
        site,prior,arm=label.rsplit('_',2)
        files += [(p,str(p.relative_to(R))) for p in (D/'figures').glob(f'{site}__{prior}_{arm}_*')]
        p=D/f'결과_{site}_{prior}_{arm}.md'
        if p.exists():files.append((p,str(p.relative_to(R))))
    for base in [O/'targets_alt',O/'freespace_targets']:
        files += [(p,'payload/'+str(p.relative_to(O))) for p in base.rglob('*') if p.is_file()]
    for site in ['B173nb_b10','B0_b10']:
        files += [(p,str(p.relative_to(R))) for p in (D/'figures').glob(site+'__LoD2_stage2_*')]
        files += [(p,str(p.relative_to(R))) for p in (D/'tables/stage2').glob(site+'__LoD2*')]
    sums=[];tmp=target.with_suffix('.tmp')
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p,name in sorted(dict((name,p) for p,name in files).items()):
            # dict stores archive name -> source path
            data=name.read_bytes();z.writestr(p,data);sums.append(hashlib.sha256(data).hexdigest()+'  '+p)
        z.writestr('SHA256SUMS','\n'.join(sums)+'\n')
    with zipfile.ZipFile(tmp) as z:
        assert z.testzip() is None
        for l in z.read('SHA256SUMS').decode().splitlines():h,n=l.split('  ',1);assert hashlib.sha256(z.read(n)).hexdigest()==h
        entries=len(z.namelist())
    tmp.rename(target);digest=hashlib.sha256(target.read_bytes()).hexdigest();target.with_suffix('.zip.sha256').write_text(digest+'  '+target.name+'\n')
    rec=dict(at=now(),path=str(target),bytes=target.stat().st_size,sha256=digest,entries=entries,CRC='PASS',member_sha256='PASS',scientific_verdict=None);dump(target.with_suffix('.json'),rec);dump(D/'delivery/addendum2'/f'{label}.json',rec);return rec

def main(mode,*args):
    with (O/'queue/publish.lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        if mode=='fixed' and (O/'delivery/addendum2/PHD-MAIN-GTJUDGE-v1_고친판.zip').exists():return
        if mode=='run':
            site,prior,arm=args;training(site,prior,arm);reports()
            if arm=='fix':return
            label=f'{site}_{prior}_{arm}'
        else:
            label='CPU보완' if mode=='cpu' else '고친판'
            if mode=='cpu':assert cpu('validate-cpu','add2_validate.py')
            if mode=='fixed':
                for site in SITES:
                    for prior in ['ALS','LoD2']:
                        post=json.loads((O/'queue/addendum2/post'/f'{site}__{prior}__fix.json').read_text())
                        if post['mesh_scored'] and post.get('status')!='NO_RESULT_POSTPROCESSING':
                            assert (D/'tables/addendum2/fix'/f'{site}__{prior}_risks_and_strata.json').exists()
                            assert (D/'figures/addendum2'/f'{site}__{prior}_fix_preservation_maps.png').exists()
                coverage=[dict(site=s,prior=p,**json.loads((O/'queue/addendum2/post'/f'{s}__{p}__fix.json').read_text())) for s in SITES for p in ['ALS','LoD2']]
                dump(D/'verification/addendum2_fixed_coverage.json',dict(runs=coverage,
                     status='PARTIAL' if any(x.get('status')=='NO_RESULT_POSTPROCESSING' or not x['mesh_scored'] for x in coverage) else 'PASS',scientific_verdict=None))
            assert cpu('qa-'+mode,'add2_qa.py',mode)
            reports();diff()
        rec=package(label)
        paths=['configs/phd/main_gtjudge_v1','scripts/phd/main_gtjudge_v1','docs/experiments/phd/main_gtjudge_v1','src/phd/forks/GeoGS-conf-guided-v1-r26']
        subprocess.run(['git','add','--',*paths],cwd=R,check=True)
        if subprocess.run(['git','diff','--cached','--quiet','--',*paths],cwd=R).returncode:subprocess.run(['git','commit','--only','-m','PHD-MAIN-GTJUDGE-v1 addendum2 '+label,'--',*paths],cwd=R,check=True)
        subprocess.run(['git','push','origin','HEAD:exp/main-experiment'],cwd=R,check=True)
        event('PACKAGE',label=label,package_at=rec['at'],**{k:v for k,v in rec.items() if k!='at'})
        print('PACKAGE_READY',json.dumps(rec,ensure_ascii=False),flush=True)
if __name__=='__main__':main(*sys.argv[1:])
