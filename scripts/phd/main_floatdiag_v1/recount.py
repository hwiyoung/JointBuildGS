"""Recount Appendix C and freeze reproducible seven-case membership."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from scipy import ndimage
from common import *

LABELS = {'nojudge':'판정 끔','prop':'본 방법 s0','lt_fixgt':'판 1','lt_dyngt':'판 2',
          'lt_dynsoft':'판 3','lt_dynnow':'판 4','mvs_a':'MVS','prior':'학습 전 사전',
          'analytic_dyn_gt':'학습 없는 도착점 판 2'}

def load_eval(site, prior):
    root = LT/'direct_stage1_v2'/f'{site}__{prior}'
    with np.load(root/'evaluation.npz') as f:
        e = {k:f[k] for k in f.files}
    return e, root

def classes(e, z):
    good = np.isfinite(z['z']) & ~z['no_surface']
    within = good & (np.abs(z['z']-e['p_gt']) <= e['tau'])
    floating = good & ~within & (z['side']==2) & (z['z']>e['p_gt']+e['tau'])
    cat = np.full(len(e['area']),4,np.uint8)
    cat[good & ~within & (z['side']==1)] = 2
    cat[good & ~within & (z['side']==0)] = 3
    cat[within], cat[floating] = 0, 1
    return cat

def components(e, mask, config):
    xy = e['centre'][:,:2].astype(float)
    lo = xy.min(0)
    ij = np.floor((xy-lo)/config['grid_m']).astype(int)
    shape = tuple((ij.max(0)+1)[::-1])
    raster = np.zeros(shape,bool)
    raster[ij[mask,1],ij[mask,0]] = True
    closed = ndimage.binary_closing(raster,iterations=config['closing_iterations'])
    labs, n = ndimage.label(closed)
    patch_label = labs[ij[:,1],ij[:,0]]
    rows = []
    for label in range(1,n+1):
        ids = np.flatnonzero(mask & (patch_label==label))
        if not len(ids): continue
        points = xy[ids]
        rows.append(dict(label=label,area_m2=float(e['area'][ids].sum()),patches=len(ids),
            centre_xy=points.mean(0).tolist(),
            bbox=[*points.min(0),*points.max(0)],patch_indices=ids.tolist(),
            closed_component_patch_indices=np.flatnonzero(patch_label==label).tolist()))
    rows.sort(key=lambda x:(-x['area_m2'],x['label']))
    return rows, lo

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--prior',default='ALS',choices=['ALS','LoD2']);a=ap.parse_args()
    cfg=config();rows=[];checks=[];sources=[];cases=[];inventory=[]
    ref=json.loads((DOC/'request/점검값_v1.json').read_text())['뜬면_비율_표']
    for site in SITES:
        e,root=load_eval(site,a.prior)
        elig=e['in_eval'] & e['scoring_allowed']; all03=elig&(e['cell']>=0)&(e['cell']<=3)
        sources.append(dict(path=str(root/'evaluation.npz'),sha256=sha(root/'evaluation.npz')))
        for prefix,label in LABELS.items():
            result = prefix if prefix in ['mvs_a','prior','analytic_dyn_gt'] else f'{prefix}_{a.prior}_s0'
            path=LT/'patch_z'/f'{site}__{a.prior}__{result}.npz'
            if not path.exists():
                inventory.append(dict(site=site,result=result,status='확인 불가',reason='저장된 patch_z 없음'))
                continue
            with np.load(path) as z:
                data={k:z[k] for k in z.files}
            expected=np.array([f'stage1:{site}:{a.prior}:{i}' for i in range(len(e['area']))])
            assert np.array_equal(data['patch_id'],expected),'patch identity/order mismatch'
            c=classes(e,data)
            sources.append(dict(path=str(path),sha256=sha(path)))
            groups=[(str(i),elig&(e['cell']==i)) for i in range(6)]+[('0~3',all03),('전체',elig)]
            for group,mask in groups:
                area=float(e['area'][mask].sum());n=int(mask.sum())
                r=dict(site=site,prior=a.prior,result=result,label=label,cell=group,patches=n,area_m2=area,
                    sample_status='표본 부족' if n<100 else 'PASS',source=str(path),source_sha256=sha(path),origin='[이 발주에서 냄]')
                for i,cat in enumerate(['within_tau','floating','mvs','prior','other_missing']):
                    m=mask&(c==i)
                    r[cat+'_patches']=int(m.sum());r[cat+'_area_m2']=float(e['area'][m].sum())
                    r[cat+'_pct']=100*r[cat+'_area_m2']/area if area else None
                missing=mask&data['no_surface']
                r['no_surface_area_m2']=float(e['area'][missing].sum())
                r['no_surface_pct']=100*r['no_surface_area_m2']/area if area else None
                assert np.isclose(sum(r[k+'_area_m2'] for k in ['within_tau','floating','mvs','prior','other_missing']),area)
                rows.append(r)
                if group=='0~3' and a.prior=='ALS' and ref[site].get(label):
                    q=ref[site][label]
                    diffs={k:abs(r[k]-q[qk]) for k,qk in [('within_tau_pct','tau_안_pct'),('floating_pct','뜬면_pct')]}
                    checks.append(dict(site=site,result=result,actual={k:r[k] for k in diffs},
                        reference={k:q[qk] for k,qk in [('within_tau_pct','tau_안_pct'),('floating_pct','뜬면_pct')]},
                        absolute_difference_pp=diffs,status='PASS' if max(diffs.values())<=cfg['stops']['appendix_C_tolerance_pp'] else 'STOP'))
            if result==f'lt_dyngt_{a.prior}_s0':
                comps,lo=components(e,all03&(c==1),cfg['case_selection'])
                save(OUT/'selection'/f'{site}_{a.prior}_components.json',dict(grid_origin=lo.tolist(),components=comps,scientific_verdict=None))
                for rank,r in enumerate([r for r in comps if r['area_m2']>10][:2],1):
                    name={'B173nb_b10':'B173','B0_b10':'B0','R1rep_b10':'R1'}[site]+f'-뜬면-{rank}'
                    cases.append(dict(id=name,site=site,prior=a.prior,kind='floating',**r))
            if result in [f'{p}_{a.prior}_s0' for p in ['nojudge','lt_dyngt','lt_dynnow']]:
                model=model_path(site,result)
                saved=[dict(path=str(p),bytes=p.stat().st_size) for p in sorted(model.glob('point_cloud/iteration_*/point_cloud.ply'))]
                ckpts=[dict(path=str(p),bytes=p.stat().st_size) for p in sorted(model.glob('chkpnt*.pth'))]
                mesh,receipt=mesh_path(site,result,a.prior)
                inventory.append(dict(site=site,result=result,model=str(model),saved_point_clouds=saved,checkpoints=ckpts,
                    mesh=str(mesh),mesh_bytes=mesh.stat().st_size if mesh.exists() else None,
                    mesh_expected_sha256=receipt['mesh_sha256'],patch_z_receipt=str(path.with_suffix('.json')),
                    status='PASS' if saved and mesh.exists() else 'UNAVAILABLE'))
        if site=='R1rep_b10':
            with np.load(root/'values.npz') as v:
                unexplained=e['has_mvs']&(np.abs(e['p_mvs'])/np.sqrt(v['sigma_prior'].astype(float)**2+v['sigma_mvs'].astype(float)**2)>3)
            comps,lo=components(e,all03&(e['cell']==2)&unexplained,cfg['case_selection'])
            assert comps
            cases.append(dict(id='R1-보존띠-1',site=site,prior=a.prior,kind='preservation',**comps[0]))
        print(site,'recount done',flush=True)
    wing=next(x for x in cfg['case_selection']['references'] if x['id']=='B173-날개')
    e,_=load_eval(wing['site'],a.prior);b=wing['bbox'];xy=e['centre'][:,:2]
    mask=e['in_eval']&e['scoring_allowed']&(xy[:,0]>=b[0])&(xy[:,0]<=b[2])&(xy[:,1]>=b[1])&(xy[:,1]<=b[3])
    cases.append(dict(**wing,prior=a.prior,kind='wing',centre_xy=wing['centre'],patch_indices=np.flatnonzero(mask).tolist(),
        patches=int(mask.sum()),area_m2=float(e['area'][mask].sum())))
    status='PASS' if checks and all(x['status']=='PASS' for x in checks) else 'STOP'
    save(DOC/'tables'/f'recount_{a.prior}.json',dict(rows=rows,sources=sources,scientific_verdict=None))
    with (DOC/'tables'/f'recount_{a.prior}.csv').open('w') as f:
        w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    lines=['# 다섯 구분 다시 세기','','[이 발주에서 냄]. 넓이 가중 비율. 표본 100패치 미만은 표본 부족.','',
        '| 단위 | 결과 | 칸 | 패치 | 넓이 m² | τ 안 % | 뜬 면 % | MVS % | 사전 % | 그 밖·면 없음 % |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        vals=[r[k+'_pct'] for k in ['within_tau','floating','mvs','prior','other_missing']]
        lines.append(f"| {r['site']} | {r['label']} | {r['cell']} | {r['patches']} | {r['area_m2']:.6f} | "+' | '.join('확인 불가' if v is None else f'{v:.6f}' for v in vals)+' |')
    (DOC/'tables'/f'recount_{a.prior}.md').write_text('\n'.join(lines)+'\n')
    save(DOC/'provenance'/f'appendix_C_{a.prior}.json',dict(at=now(),status=status,checks=checks,scientific_verdict=None))
    save(DOC/'provenance'/f'input_inventory_{a.prior}.json',dict(at=now(),inputs=inventory,scientific_verdict=None))
    save(CFG/f'cases_{a.prior}.json',dict(selected_at=now(),selection_config_sha256=sha(CFG/'floatdiag_v1.json'),cases=cases,scientific_verdict=None))
    print('Appendix C',status,'max difference pp',max(v for r in checks for v in r['absolute_difference_pp'].values()))
    print('cases',[(r['id'],r['patches'],r['area_m2'],r['bbox']) for r in cases])
    if status!='PASS':raise SystemExit('STOP: Appendix C differs by more than 0.5 percentage points')

if __name__=='__main__':main()
