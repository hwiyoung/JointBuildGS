"""8.3/8.4: preserve metric definitions and report numerical change thresholds."""
import csv
import json
import math
from pathlib import Path
from inputs import PH,SITES,PRIORS,save,sha

DOC=Path('/docs/tables')

def dump(name,rows,notes):
    save(DOC/(name+'.json'),dict(rows=rows,notes=notes,scientific_verdict=None))
    if rows:
        with (DOC/(name+'.csv')).open('w') as f:
            w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)

def grade(delta,threshold,n):
    if delta is None or threshold is None:return '확인 불가'
    if n<100:return '표본 부족'
    return '확인' if abs(delta)>2*threshold else ('가능, 근거 불완전' if abs(delta)>threshold else '기준 안')

def compare(rows,values,thresholds,kind):
    # Paired new arm versus nojudge, plus the prescribed fixed/dynamic pair.
    for (site,prior,subset,metric,variant),(value,n) in sorted(values.items()):
        if not variant.startswith('lt_'):continue
        references=['nojudge_'+prior+'_s0']
        if variant=='lt_dyngt_'+prior+'_s0':references+=['lt_fixgt_'+prior+'_s0']
        for ref in references:
            rv,rn=values.get((site,prior,subset,metric,ref),(None,0))
            a,b,pooled,case=thresholds.get((site,prior,subset,metric),(None,None,None,None))
            N=min(n,rn)
            three=300/N if N and metric in ['within_tau_percent','no_surface_percent','gt:R_tau','res:P_tau'] else None
            parts=[x for x in [pooled,case,three] if x is not None]
            crit=max(parts) if parts else None
            diff=value-rv if value is not None and rv is not None else None
            rows.append(dict(kind=kind,site=site,prior=prior,subset=subset,metric=metric,variant=variant,reference=ref,
                value=value,reference_value=rv,difference=diff,N=N,seed_0=a,seed_1=b,pooled=pooled,case_spread=case,
                three_points=three,threshold=crit,numerical_change=grade(diff,crit,N),origin='[이 발주에서 냄]'))

def main():
    patch=json.loads((DOC/'patch_scores_all.json').read_text())
    values={};thresholds={};noise=[];comparisons=[]
    metrics=['within_tau_percent','no_surface_percent','error_patch_median_m']
    for r in patch['rows']:
        if r['site'] not in SITES:continue
        for metric in metrics:values[(r['site'],r['prior'],r['subset'],metric,r['variant'])]=(r[metric],r['error_observed_patches'] if metric=='error_patch_median_m' else r['patches'])
    for site,prior,subset,metric,_ in values:
        k=(site,prior,subset,metric)
        if k in thresholds:continue
        a,na=values.get(k+('prop_'+prior+'_s0',),(None,0));b,nb=values.get(k+('prop_'+prior+'_s1',),(None,0))
        case=2.8*abs(a-b)/math.sqrt(2) if a is not None and b is not None else None
        thresholds[k]=(a,b,None,case);N=min(na,nb)
        three=300/N if N and metric!='error_patch_median_m' else None
        parts=[x for x in [case,three] if x is not None]
        noise.append(dict(kind='stage1_patch',site=site,prior=prior,subset=subset,metric=metric,seed_0=a,seed_1=b,
            N=N,pooled=None,pooled_unavailable='no existing pooled spread for this new stage-1 first-hit patch metric',
            case_spread=case,three_points=three,threshold=max(parts) if parts else None))
    compare(comparisons,values,thresholds,'stage1_patch')
    source=PH/'main_axes71_v2/PHD-MAIN-AXES71-v2/tables/a3_criterion.json';criteria=json.loads(source.read_text())['data']
    base=json.loads((DOC/'axes_baselines_existing.json').read_text())['rows']
    base += [json.loads(p.read_text()) for p in sorted((DOC/'axes').glob('*.json'))]
    flat=[];values={};thresholds={}
    for r in base:
        for subset,x in r['values'].items():
            available=str(x.get('status','')).startswith('있음')
            gt=x.get('gt',{});res=x.get('res',{}).get('E',{});both=x.get('both',{}).get('E',{})
            row=dict(site=r['site'],prior=r['prior'],variant=r['result'],subset=subset,status=x.get('status'),
                gt_N=gt.get('n_gt',0),R_tau_percent=None if gt.get('R_tau') is None else 100*gt['R_tau'],gt_mean_cm=gt.get('mean'),
                result_E_N=res.get('n',0),P_tau_E_percent=None if res.get('P_tau') is None else 100*res['P_tau'],result_E_mean_cm=res.get('mean'),
                F1_tau_E_percent=None if both.get('F1_tau') is None else 100*both['F1_tau'],Chamfer_E_cm=both.get('chamfer'),
                origin=r.get('origin','기존 AXES71 일3 표에서 옮김'))
            flat.append(row)
            for metric,value,N in [('gt:R_tau',row['R_tau_percent'],row['gt_N']),('gt:mean',row['gt_mean_cm'],row['gt_N']),
                ('res:P_tau',row['P_tau_E_percent'],row['result_E_N']),('res:mean',row['result_E_mean_cm'],row['result_E_N'])]:
                values[(r['site'],r['prior'],subset,metric,r['result'])]=(value if available else None,N)
    for site,prior,subset,metric,_ in values:
        k=(site,prior,subset,metric)
        if k in thresholds:continue
        a,na=values.get(k+('prop_'+prior+'_s0',),(None,0));b,nb=values.get(k+('prop_'+prior+'_s1',),(None,0))
        case=2.8*abs(a-b)/math.sqrt(2) if a is not None and b is not None else None
        pooled=criteria.get(subset,{}).get(metric,{}).get('pooled');thresholds[k]=(a,b,pooled,case);N=min(na,nb)
        three=300/N if N and metric in ['gt:R_tau','res:P_tau'] else None
        parts=[x for x in [pooled,case,three] if x is not None]
        noise.append(dict(kind='AXES71',site=site,prior=prior,subset=subset,metric=metric,seed_0=a,seed_1=b,N=N,
            pooled=pooled,pooled_unavailable=None if pooled is not None else 'no matching existing spread',case_spread=case,
            three_points=three,threshold=max(parts) if parts else None))
    compare(comparisons,values,thresholds,'AXES71')
    dump('axes_metrics',flat,dict(count='E',source_of_existing='AXES71 a3/a9; exact functions for new arms'))
    dump('noise_thresholds',noise,dict(existing_pooled=str(source),sha256=sha(source),
        units='patch median m; AXES mean cm; shares percentage points',no_geometry_or_training_parameter_selection=True))
    dump('numerical_changes',comparisons,dict(rule='absolute change > 2 thresholds: confirmed numerical change; > threshold: possible; N<100 unreadable',
        scientific_interpretation=False))
    lines=['# 두 축 평가와 수치 차이 기준','',
        '기존 AXES71의 열두 칸·의도별 합·전체를 그대로 사용한다. 결과 쪽은 셈 마다. 새 1단계 패치 채점과 서로 다른 지표다.','',
        '| 단위 | 사전 | 결과 | 참값 N | R(τ) % | 참값 평균 cm | 결과 N | P(τ) % | 결과 평균 cm | F1 % | Chamfer cm |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    fmt=lambda x:'확인 불가' if x is None else f'{x:.4f}'
    for r in flat:
        if r['subset']!='all':continue
        lines.append('| '+' | '.join(str(r[k]) if k in ['site','prior','variant','gt_N','result_E_N'] else fmt(r[k]) for k in ['site','prior','variant','gt_N','R_tau_percent','gt_mean_cm','result_E_N','P_tau_E_percent','result_E_mean_cm','F1_tau_E_percent','Chamfer_E_cm'])+' |')
    lines+=['','수치 차이의 기준은 모은 흔들림(같은 지표가 있을 때), 두 씨앗의 2.8×절대차/√2, 비율에서 300/N 중 최댓값이다. 새 1단계 패치 지표의 기존 모은 흔들림은 없어 다른 지표의 값을 대신 넣지 않았다. 기준의 두 배를 넘는 차이만 수치 차이 확인으로 적는다. 과학적 판정은 하지 않는다.']
    (DOC/'axes_metrics.md').write_text('\n'.join(lines)+'\n')
    lines=['# 지표별 수치 차이 기준','','단위: 새 패치 거리 중앙값 m, 두 축 거리 평균 cm, 비율 %p. 정의가 같은 기존 흔들림 값만 사용한다.','',
        '| 지표 묶음 | 단위 | 사전 | 범위 | 지표 | N | 모은 폭 | 해당 단위 폭 | 300/N | 기준 |',
        '|---|---|---|---|---|---:|---:|---:|---:|---:|']
    for r in noise:
        lines.append('| '+' | '.join(str(r[k]) if k in ['kind','site','prior','subset','metric','N'] else fmt(r[k]) for k in ['kind','site','prior','subset','metric','N','pooled','case_spread','three_points','threshold'])+' |')
    (DOC/'noise_thresholds.md').write_text('\n'.join(lines)+'\n')
    lines=['# 수치 차이의 구간','','기준 두 배 초과, 기준 초과~두 배 이하, 기준 안을 구분한다. 과학적 판정이 아니다.','',
        '| 단위 | 사전 | 범위 | 지표 | 판 | 비교 기준 | N | 차 | 문턱 | 수치 구간 |',
        '|---|---|---|---|---|---|---:|---:|---:|---|']
    for r in comparisons:
        lines.append(f"| {r['site']} | {r['prior']} | {r['subset']} | {r['metric']} | {r['variant']} | {r['reference']} | {r['N']} | {fmt(r['difference'])} | {fmt(r['threshold'])} | {r['numerical_change']} |")
    (DOC/'numerical_changes.md').write_text('\n'.join(lines)+'\n')
    print('axes rows',len(flat),'thresholds',len(noise),'new comparisons',len(comparisons),flush=True)

if __name__=='__main__':main()
