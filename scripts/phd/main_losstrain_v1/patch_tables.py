"""8.1 all available patch scores, with paired analytical columns and pooled sites."""
import argparse
import csv
from pathlib import Path
import numpy as np
from inputs import OUT,SITES,PRIORS,save,sha
from analytic_tables import summarize
from side_tables import VARS

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',choices=SITES);ap.add_argument('--prior',choices=PRIORS);a=ap.parse_args()
    rows=[];sources=[];pool={}
    for site in [a.site] if a.site else SITES:
        for prior in [a.prior] if a.prior else PRIORS:
            root=OUT/'direct_stage1_v2'/(site+'__'+prior)
            with np.load(root/'evaluation.npz') as e,np.load(root/'values.npz') as v:
                common={k:e[k] for k in ['area','in_eval','cell','scoring_allowed','has_mvs','p_gt','p_mvs','tau']}
                common.update({k:v[k].astype(np.float64) for k in ['sigma_prior','sigma_mvs']})
            for path in sorted((OUT/'patch_z').glob(f'{site}__{prior}__*.npz')):
                result=path.stem.split('__',2)[2]
                with np.load(path) as z:
                    assert len(z['z'])==len(common['area'])
                    r={**common,'z_'+result:z['z']}
                rr=summarize(site,prior,r)
                kind='analytic' if result.startswith('analytic_') else 'mesh'
                digest=sha(path)
                for row in rr:row.update(result_type=kind,source=str(path),source_sha256=digest)
                rows+=rr;sources.append(str(path))
                # Canonical result identity retains the prior in its name; the
                # three sites have the exact same result labels.
                pool.setdefault((prior,result),[]).append((site,r))
    for (prior,result),parts in pool.items():
        if {x[0] for x in parts}!=set(SITES):continue
        r={k:np.concatenate([x[1][k] for x in parts]) for k in parts[0][1]}
        rr=summarize('three_units_pooled',prior,r)
        for row in rr:row.update(result_type='analytic' if result.startswith('analytic_') else 'mesh',source='pooled exact three units',source_sha256=None)
        rows+=rr
    lookup={(r['site'],r['prior'],r['variant'],r['subset']):r for r in rows}
    for r in rows:
        variant=next((v for v in VARS if r['variant']==v+'_'+r['prior']+'_s0'),None)
        analytic=lookup.get((r['site'],r['prior'],'analytic_'+VARS[variant],r['subset'])) if variant else None
        r['analytic_within_tau_percent']=analytic['within_tau_percent'] if analytic else None
        r['analytic_minus_trained_pp']=analytic['within_tau_percent']-r['within_tau_percent'] if analytic and r['within_tau_percent'] is not None else None
    tag='__'.join(x for x in [a.site,a.prior] if x) or 'all'
    save(f'/docs/tables/patch_scores_{tag}.json',dict(rows=rows,sources=sources,scientific_verdict=None))
    if rows:
        with Path(f'/docs/tables/patch_scores_{tag}.csv').open('w') as f:
            w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    lines=['# 1단계 패치 채점','', '[이 발주에서 냄]. 같은 평가 패치·넓이·허용 오차로 계산했다. 면 없음은 τ 밖으로 센다. 100패치 미만은 표본 부족이다.','',
        '거리 중앙값은 면을 만난 패치에서 구하며 그 표본 수는 error_observed_patches에 적었다. τ 안 비율에서는 면 없음도 실패로 센다.','',
        '| 단위 | 사전 | 결과 | 범위 | N | 넓이(m²) | 학습 없는 시험(%) | 결과 τ 안(%) | 면 없음(%) |',
        '|---|---|---|---|---:|---:|---:|---:|---:|']
    for r in rows:
        if r['result_type']=='analytic' or r['subset'] not in ['all_0_3','unexplained','cell_0','cell_4','cell_5']:continue
        fmt=lambda x:'확인 불가' if x is None else f'{x:.4f}'
        lines.append(f"| {r['site']} | {r['prior']} | {r['variant']} | {r['subset']} | {r['patches']} | {r['area_m2']:.3f} | {fmt(r['analytic_within_tau_percent'])} | {fmt(r['within_tau_percent'])} | {fmt(r['no_surface_percent'])} |")
    Path(f'/docs/tables/patch_scores_{tag}.md').write_text('\n'.join(lines)+'\n')
    print('patch score rows',len(rows),flush=True)

if __name__=='__main__':main()
