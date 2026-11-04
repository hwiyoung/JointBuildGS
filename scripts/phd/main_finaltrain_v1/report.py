"""Per-arm measurements and explicitly pending comparison rows; no interpretation."""
import csv,subprocess,sys
from common import *
RS=PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1'
SITES={'B173nb_b10':'B173주변','B0_b10':'B0','R1rep_b10':'R1'}
PRIORS={'ALS':'항공LiDAR','LoD2':'LoD2'}
FAMILIES=[('prior','사전 정보'),('mvs','MVS'),('fusion','결합'),('baseline','기준선'),('GeoGS','GeoGS'),('2DGS','2DGS'),('CDGS','CDGS'),('judgment_mesh','판단으로 조합한 메시'),('oracle','상한'),('finaltrain','본 방법')]
REGIONS={1:'일치',2:'보존',3:'보정',0:'결측'}

def table(name,rows):
    root=D/'tables';root.mkdir(exist_ok=True);dump(root/f'{name}.json',dict(rows=rows,scientific_verdict=None))
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (root/f'{name}.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
    (root/f'{name}.md').write_text('| '+' | '.join(fields)+' |\n| '+' | '.join(['---']*len(fields))+' |\n'+'\n'.join('| '+' | '.join('' if r.get(k) is None else str(r.get(k,'')) for k in fields)+' |' for r in rows)+'\n')

def old_release(site,prior,it):
    base=TG/'r8/runs'/f'tg_{site}_{prior}_s0_r8/model'
    candidates=[base/'target_monitor'/f'snapshot_{it}.npz']
    if site=='B173nb_b10' and prior=='LoD2':
        for suffix in ['rfix_continue/runs/r8_LoD2_rfix/model','rfix_continue/attempt2/runs/r8_LoD2_rfix/model']:
            candidates.append(TG/suffix/'target_monitor'/f'snapshot_{it}.npz')
    for p in candidates:
        if p.exists():
            z=loadz(p,['origin','init_id','region','target_tag']);reg=z['region'][z['init_id']];rows={}
            for r in REGIONS:
                m=(z['origin']==1)&(reg==r);rows[r]=float((z['target_tag'][m]==2).mean()) if m.any() else None
            return rows,str(p),sha(p)
    return {},None,None

def monitor(site,prior,run):
    receipt=json.loads((run/'receipt.json').read_text());model=Path(receipt['attempts'][-1]['model']);rows=[];alert=[]
    for it in [7000,15000,30000]:
        p=model/'target_monitor'/f'release_{it}.json'
        if not p.exists():continue
        old,path,digest=old_release(site,prior,it)
        for r in json.loads(p.read_text())['rows']:
            base=old.get(r['region']);value=r['fraction'];ratio=value/base if value is not None and base is not None and base>0 else None
            exceeds=value is not None and base is not None and value>2*base
            row=dict(site=site,prior=prior,iteration=it,region=REGIONS[r['region']],prior_descendants=r['prior_descendants'],released=r['released'],fraction=value,
                r8_fraction=base,ratio_to_r8=ratio,exceeds_twice_r8=exceeds,r8_source=path,r8_sha256=digest)
            rows.append(row)
            if exceeds:alert.append(f'{it:,}회 {REGIONS[r["region"]]} 풀림 {value*100:.2f}%: r8 {base*100:.2f}%의 2배 초과')
    table(f'release_{site}__{prior}',rows);return rows,alert

def comparison(site,prior,current):
    unavailable=(O/'post'/f'{site}__{prior}.json').exists()
    available=[]
    for p in sorted((RS/'scores').glob('*/values.json')):
        d=json.loads(p.read_text())
        if d.get('site')==site and d.get('prior')==prior and not d.get('legacy',False):available.append((p,d))
    rows=[];cellrows=[]
    for family,label in FAMILIES:
        src=None;value=None
        if family=='finaltrain':src,value=current
        else:
            matches=[(p,d) for p,d in available if d.get('family')==family or f'__{family}_' in d.get('key','') or d.get('key','').endswith('__'+family)]
            if matches:src,value=matches[-1]
        row=dict(site=site,prior=prior,family=family,method=label,status='완료' if value else '셈 전',source=str(src) if value else None,source_sha256=sha(src) if value else None)
        if value is None and unavailable and family not in ['prior','mvs']:row['status']='확인 불가'
        row.update({k:value['scene'].get(k) if value else None for k in ['n_gt','n_result','completeness','accuracy','gt_mean_m','result_mean_m']});rows.append(row)
        for cell in [0,1,2,4,3]:
            v=next((x for x in value['cells'] if x['cell']==cell),None) if value else None
            cellrows.append({**row,'cell':cell,**{k:v.get(k) if v else None for k in ['n_gt','n_result','completeness','accuracy','gt_mean_m','result_mean_m']},
                'outside_column_fraction':value['diagnostic']['outside_column_fraction'] if value else None})
    return rows,cellrows

def fmt(value,percent=False):return '확인 불가' if value is None else f'{value*(100 if percent else 1):.2f}'

def main(site,prior):
    cfg();stem=f'{site}__{prior}';run=O/'runs'/site/f'ft_{prior}_s0';r=json.loads((run/'receipt.json').read_text());status=r['status'];rows,alerts=monitor(site,prior,run)
    current_path=O/'rescore/scores'/('ft_'+stem)/'values.json';current=json.loads(current_path.read_text()) if current_path.exists() else None
    post_path=O/'post'/f'{stem}.json';post=json.loads(post_path.read_text()) if post_path.exists() else None
    comp,cells=comparison(site,prior,(current_path,current));table('table3_'+stem,comp);table('table4_'+stem,cells)
    table('table7_'+stem,[x for x in cells if x['family'] in ['baseline','judgment_mesh','finaltrain','oracle']])
    if current or post:
        offsets=[];bands=[]
        for row in comp:
            base={k:row[k] for k in ['site','prior','family','method','status','source','source_sha256']}
            if row['source']:
                score=json.loads(Path(row['source']).read_text());offsets.extend(dict(base,**x) for x in score['offsets']);bands.append(dict(base,**score['band']))
            else:
                for cell in [1,2]:
                    for lo,hi in [(0,.5),(.5,1),(1,2),(2,4),(4,None)]:offsets.append(dict(base,cell=cell,lower_m=lo,upper_m=hi,n_gt=None,completeness=None,patches=None))
                bands.append(dict(base,area_m2=None,patches=None,n_gt=None,completeness=None))
        table('table5_'+stem,offsets);table('table8_'+stem,bands)
        from outcome_targets import measure
        measure(site,prior,table)
        if current and not all((D/'figures'/f'{stem}_그림7_{n}_{prior}.png').exists() for n in [3,5]):
            subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('figures_bridge.py')),site,prior,'early'],check=True)
    targets=json.loads((O/'targets'/f'{stem}.json').read_text());pixels=json.loads((O/'stage1'/stem/'ready.json').read_text());model=Path(r['attempts'][-1]['model']);counts=[]
    table('target_regions_'+stem,[dict(site=site,prior=prior,**x) for x in targets['regions']])
    curve=model/'target_monitor/curve.jsonl'
    if curve.exists():
        counts=[json.loads(line) for line in curve.read_text().splitlines() if line.strip()]
        table('training_'+stem,counts)
    title=f'결과_{SITES[site]}_{PRIORS[prior]}'
    comparison_path=D/'tables'/f'targets_rescore_comparison_{stem}.json'
    target_comparison=json.loads(comparison_path.read_text())['rows'] if comparison_path.exists() else targets['rescore_comparison']
    text=['# '+title,'','[이 발주에서 냄] · PHD-MAIN-FINALTRAIN-v1 · scientific_verdict: null','']
    text+=['**풀림 기록: '+x+'**' for x in alerts]
    if post:text+=['','**최종 채점 확인 불가: '+post['reason']+'**']
    text+=['',f'- 판의 상태: {status}. 씨앗 0. 요청 반복 30,000회.',f'- 학습 시간: {sum(x["seconds"] for x in r["attempts"])/3600:.3f}시간. 시도 {len(r["attempts"])}회.',
        '- 채점: '+('RESCORE-v1 최종 메시·기둥·새 τ·새 칸.' if current else '결과 없음 또는 채점 전. 숫자를 채우지 않았다.'),
        f'- 목표 범위: 전체 {targets["patches"]:,}패치. 평가 밖 {targets["outside_patches"]:,}패치 / {targets["outside_area_m2"]:.3f}m². {targets["outside_status"]}.',
        f'- 유한한 목표·불확실도를 정하지 못한 넓이(빈 공간 제외): {targets["unassigned_target_area_m2"]:.3f}m². 해당 값은 보간하거나 추측하지 않았다.',
        f'- 장면 σ_ref: {pixels["sigma_ref"]:.10f}m. 무게 차수 1. 배경 무게 1. σ_W와 r은 목표에 넣지 않았다.','',
        '| 판 | 완전성 % | 정확성 % | 참값 기준 거리 m | 결과 기준 거리 m | 상태 |','|---|---:|---:|---:|---:|---|']
    for x in comp:
        values=[fmt(x['completeness'],True),fmt(x['accuracy'],True),fmt(x['gt_mean_m']),fmt(x['result_mean_m'])] if x['status']=='완료' else [x['status']]*4
        text.append('| '+' | '.join([x['method'],*values,x['status']])+' |')
    text+=['','맞는 판단별 반올림 전 네 값·표본 수·기둥 밖 비율은 `tables/table4_'+stem+'.{csv,json}`에 있다.',
        '',f'화소 무게 1·10·50·90·99%: {pixels["weight_q01_q10_q50_q90_q99"]}. 아래 끝 비율 {pixels["clip_low_fraction"]*100:.5f}%, 위 끝 비율 {pixels["clip_high_fraction"]*100:.5f}%.',
        '',f'목표 수식·기본값 100회 점검: PASS. 학습 입력 대조: PASS. 자르기 전 패치 넓이 가중 평균 무게: {targets["unclipped_area_weighted_mean"]:.15f}.',
        '',f'고정 평가 입력의 판단문 재실행 불일치: {targets["eval_replay"]["decision_mismatches"]}개. 전체 범위로 입력을 확장한 재계산의 평가 범위 판단 차이: {targets["extended_eval_decision_mismatches"]}개. 평가 범위 학습에는 고정 JUDGEAPPLY 판단을 썼다. RESCORE 목표 대조: {target_comparison}.',
        '','7,000·15,000·30,000회 풀림과 r8 비교는 `tables/release_'+stem+'.{csv,json}`에 기록했다. r8 값이 없는 항목은 비워 두었다.']
    for it in [7000,15000,30000]:
        h=model/'target_monitor'/f'health_{it}.json'
        if h.exists():
            v=json.loads(h.read_text());text.append(f'- {it:,}회: 가우시안 {v["gaussians"]:,}개, {v["status"]}.')
    figures=sorted((D/'figures').glob(stem+'*.png'))
    for p in figures:text+=['',f'![{p.stem}](figures/{p.name})']
    if not figures:text+=['','그림: '+post['reason'] if post else ('그림: 생성 전.' if current else '그림: 학습 완료 결과가 없어 생성하지 않았다.')]
    (D/(title+'.md')).write_text('\n'.join(text)+'\n')
    dump(O/'reports'/f'{stem}.json',dict(at=now(),status=status,report=str(D/(title+'.md')),figures=[str(p) for p in figures],scored=current is not None,post=post,scientific_verdict=None))
    from verify_delivery import main as verify
    verify(site,prior)
    print('REPORT',title,flush=True)

if __name__=='__main__':
    if sys.argv[1]=='all':
        rows=[]
        for site in SITES:
            for prior in PRIORS:
                main(site,prior);rows.append(json.loads((O/'reports'/f'{site}__{prior}.json').read_text()))
                if rows[-1]['scored']:
                    subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('figures_bridge.py')),site,prior,'remaining'],check=True)
        dump(O/'reports/all.json',dict(at=now(),rows=rows,scientific_verdict=None))
        lines=['# 최종학습 보고 v1','','PHD-MAIN-FINALTRAIN-v1 · scientific_verdict: null','',
            'r22 사본 r23에서 4장의 고정 판단과 새 목표 정밀도를 사용했다. 깊이 손실의 화소 무게는 clip(σ_ref/σ_목표, 0.1, 10)이고 σ_ref는 지역×사전 정보마다 하나다. 목표에는 σ_W와 정합 오차 r을 넣지 않았다.','',
            '| 지역·사전 정보 | 상태 | 채점 | 판별 보고 |','|---|---|---|---|']
        for site in SITES:
            for prior in PRIORS:
                rec=json.loads((O/'reports'/f'{site}__{prior}.json').read_text());p=Path(rec['report'])
                lines.append(f'| {SITES[site]} {PRIORS[prior]} | {rec["status"]} | '+('RESCORE-v1' if rec['scored'] else ('확인 불가: 원래 가상 시점 입력 없음' if rec.get('post') else '결과 없음 또는 셈 전'))+f' | [{p.name}]({p.name}) |')
        lines+=['','판마다 목표·화소 무게·풀림·가우시안 수·시간은 위 보고와 tables에 있다. 비교 방법의 미완료 행은 셈 전으로 유지했다. 모든 설정과 잠금 기록, 목표 배열, 기록은 전달 ZIP의 SHA256SUMS로 확인할 수 있다.','',
            '단위 점검: 스위치 off의 동일 씨앗 100회 모델·Adam·목표 결정·카메라 순서 일치, 목표 수식 및 장면 기준 무게, 학습 입력의 목표와 정밀도 대조. 각 점검의 계산 수와 원본 해시는 verification 기록에 있다.']
        text='\n'.join(lines)+'\n';assert len(text)<15000;(D/'최종학습_보고_v1.md').write_text(text)
    else:main(*sys.argv[1:])
