"""Amended 6.4/8.1: area-weighted C.4 results on the stage-1 patches."""
import csv
from pathlib import Path
import numpy as np
from inputs import OUT,SITES,PRIORS,save,sha
from direct_rules import RULES

def median(x,w):
    k=np.argsort(x);return float(x[k][np.searchsorted(np.cumsum(w[k]),w.sum()/2)]) if len(x) else None

def main():
    rows=[];root=OUT/RULES['revision'];pz=OUT/'patch_z';pz.mkdir(exist_ok=True)
    pool={p:[] for p in PRIORS};sources=[]
    for site in SITES:
        for prior in PRIORS:
            d=root/(site+'__'+prior)
            with np.load(d/'evaluation.npz') as e,np.load(d/'values.npz') as v:
                r={k:e[k] for k in ['area','in_eval','cell','scoring_allowed','has_mvs','p_gt','p_mvs','tau']}
                r.update({k:v[k].astype(np.float64) for k in ['sigma_prior','sigma_mvs']})
                r.update({k:e[k] for k in e.files if k.startswith('z_')})
                N=len(r['area']);pid=np.array([f'stage1:{site}:{prior}:{i}' for i in range(N)])
                for key in [k for k in r if k.startswith('z_')]:
                    z=r[key];dp=np.abs(z)/r['sigma_prior'];dm=np.abs(z-r['p_mvs'])/r['sigma_mvs']
                    side=np.where((dp<=3)&((dm>3)|~np.isfinite(dm)|(dp<=dm)),0,np.where(dm<=3,1,2)).astype(np.int8)
                    np.savez_compressed(pz/f'{site}__{prior}__analytic_{key[2:]}.npz',patch_id=pid,z=z,no_surface=np.zeros(N,bool),
                        side=side,in_eval=r['in_eval'],scoring_allowed=r['scoring_allowed'])
            pool[prior].append(r);sources.append(dict(site=site,prior=prior,path=str(d/'evaluation.npz'),sha256=sha(d/'evaluation.npz')))
            rows+=summarize(site,prior,r)
    for prior,parts in pool.items():
        r={k:np.concatenate([p[k] for p in parts]) for k in parts[0]};rows+=summarize('three_units_pooled',prior,r)
    save('/docs/tables/analytic_stage1.json',dict(rows=rows,sources=sources,rules=RULES['revision'],
        origin='[이 발주에서 냄]',training_results=False,scientific_verdict=None))
    cols=list(rows[0])
    with Path('/docs/tables/analytic_stage1.csv').open('w') as f:
        w=csv.DictWriter(f,cols,lineterminator='\n');w.writeheader();w.writerows(rows)
    lines=['# 1단계 패치의 학습 없는 시험','',
        '[이 발주에서 냄]. 도착점은 C.4의 40회 IRLS·두 시작점과 고정 무게 해로 계산했다. 채점은 평가 범위, 참값 있음, 다·라 대체 없음에 한정한다. 전체·설명 안 됨은 MVS 있는 칸 0~3이다. 학습 결과가 아니다.','',
        '| 단위 | 사전 정보 | 판 | 범위 | N | 넓이 (m²) | τ 안 (%) |','|---|---|---|---|---:|---:|---:|']
    for r in rows:
        if r['subset'] not in ['all_0_3','unexplained']:continue
        lines.append(f"| {r['site']} | {r['prior']} | {r['variant']} | {r['subset']} | {r['patches']:,} | {r['area_m2']:.3f} | {r['within_tau_percent'] if r['within_tau_percent'] is not None else '확인 불가'} |")
    Path('/docs/tables/analytic_stage1.md').write_text('\n'.join(lines)+'\n')
    print('analytic rows',len(rows),'units + pooled',flush=True)

def summarize(site,prior,r):
    area=r['area'];cell=r['cell'];ok=r['in_eval']&r['scoring_allowed'];both=ok&r['has_mvs']&(cell<4)
    unexpl=np.abs(r['p_mvs'])/np.sqrt(r['sigma_prior']**2+r['sigma_mvs']**2)>3
    subsets={'all_0_3':both,'unexplained':both&unexpl}
    for i in range(6):subsets[f'cell_{i}']=ok&(cell==i)
    for i in range(4):subsets[f'unexplained_cell_{i}']=both&unexpl&(cell==i)
    out=[]
    for key in [k for k in r if k.startswith('z_')]:
        err=np.abs(r[key]-r['p_gt']);success=err<=r['tau']
        for label,m in subsets.items():
            A=float(area[m].sum());K=int(m.sum());S=float(area[m&success].sum())
            out.append(dict(site=site,prior=prior,variant=key[2:],subset=label,patches=K,area_m2=A,
                successful_patches=int((m&success).sum()),successful_area_m2=S,within_tau_percent=100*S/A if A>0 else None,
                no_surface_patches=int((m&~np.isfinite(r[key])).sum()),no_surface_area_m2=float(area[m&~np.isfinite(r[key])].sum()),
                no_surface_percent=100*float(area[m&~np.isfinite(r[key])].sum())/A if A>0 else None,
                error_area_weighted_median_m=median(err[m&np.isfinite(err)],area[m&np.isfinite(err)]),minimum_sample='PASS' if K>=100 else 'INSUFFICIENT',
                result_type='analytic_not_trained',origin='[이 발주에서 냄]'))
    return out

if __name__=='__main__':main()
