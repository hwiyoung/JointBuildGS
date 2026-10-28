"""Exact all-view quantiles and population gradient medians; no subsampling."""
import argparse
import csv
import json
import numpy as np
from plyfile import PlyData
from common import *
from recount import load_eval

def table(path,rows,caption):
    save(path.with_suffix('.json'),dict(rows=rows,caption=caption,scientific_verdict=None))
    keys=list(rows[0])
    with path.with_suffix('.csv').open('w') as f:
        w=csv.DictWriter(f,keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    fmt=lambda v:'확인 불가' if v is None else f'{v:.7g}' if isinstance(v,float) else str(v)
    lines=['# '+caption,'','[이 발주에서 냄]. 반올림 전 값과 출처는 같은 이름의 JSON/CSV에 있다.','',
        '| '+' | '.join(keys)+' |','|'+'|'.join(['---']*len(keys))+'|']
    lines+=['| '+' | '.join(fmt(r[k]) for k in keys)+' |' for r in rows]
    path.with_suffix('.md').write_text('\n'.join(lines)+'\n')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',required=True);ap.add_argument('--prior',default='ALS',choices=['ALS','LoD2']);a=ap.parse_args()
    e,_=load_eval(a.site,a.prior);xy=e['centre'][:,:2]
    cases=[x for x in json.loads((CFG/f'cases_{a.prior}.json').read_text())['cases'] if x['site']==a.site]
    geometry={x['id']:x for x in json.loads((CFG/f'geometry_{a.site}_{a.prior}.json').read_text())['cases']}
    domains=[('전체',np.ones(len(xy),bool))]
    for c in cases:
        b=np.array(c['bbox']);domains.append((c['id'],((xy>=b[:2]-3)&(xy<=b[2:]+3)).all(1)))
    rows=[];gradient_rows=[]
    grows=json.loads((DOC/'tables'/f'gaussians_{a.site}_{a.prior}.json').read_text())['rows']
    for result in [f'{p}_{a.prior}_s0' for p in ['nojudge','lt_dyngt','lt_dynnow']]:
        root=OUT/'diagnostics'/a.site/result;receipt=json.loads((root/'receipt.json').read_text())
        fields=['patch_id','pixel_type','has_mvs','prior_r_sigma','mvs_r_sigma','current_prior_inside_band']
        fields += [m+'_'+t+'_'+k for m in ['dynamic','current'] for t in ['prior','mvs'] for k in ['force','dead']]
        values={k:[] for k in fields}
        for view in receipt['views']:
            with np.load(root/(view['view']+'.npz')) as f:
                for k in fields:values[k].append(f[k])
        z={k:np.concatenate(v) for k,v in values.items()};del values
        ids=z['patch_id'];own='current' if result.startswith('nojudge') else 'dynamic'
        for case,region in domains:
            for kind,typ in [('floating',0),('roof',1)]:
                mask=region[ids]&(z['pixel_type']==typ);n=int(mask.sum());patches=len(np.unique(ids[mask]))
                for mode in ['dynamic','current']:
                    both=z[mode+'_prior_dead']&(~z['has_mvs']|z[mode+'_mvs_dead'])
                    for term in ['prior','mvs']:
                        m=mask if term=='prior' else mask&z['has_mvs'];count=int(m.sum())
                        q=np.quantile(z[term+'_r_sigma'][m],[.25,.5,.75,.9]) if count else [None]*4
                        aq=np.quantile(np.abs(z[term+'_r_sigma'][m]),[.25,.5,.75,.9]) if count else [None]*4
                        row=dict(site=a.site,result=result,case=case,kind=kind,loss=mode,role='자기 손실' if mode==own else '반대 손실',term=term,
                            pixels=count,group_pixels=n,patches=patches,dead_fraction=float(z[mode+'_'+term+'_dead'][m].mean()) if count else None,
                            all_terms_dead_fraction=float(both[mask].mean()) if n else None,
                            force_median=float(np.median(z[mode+'_'+term+'_force'][m])) if count else None,
                            current_prior_inside_band_fraction=float(z['current_prior_inside_band'][mask].mean()) if n else None,
                            sample_status='표본 부족' if patches<100 else 'PASS',source=str(root/'receipt.json'))
                        for lab,v,av in zip(['q25','q50','q75','q90'],q,aq):row['r_sigma_'+lab]=float(v) if v is not None else None;row['abs_r_sigma_'+lab]=float(av) if av is not None else None
                        rows.append(row)
        # Save full exact arrays once per result for density plots; no display
        # thinning is used in any quantitative summary.
        np.savez_compressed(root/'all_views_reduced.npz',**z)
        with np.load(root/'centre_gradients.npz') as f:grad={k:f[k] for k in f.files}
        with np.load(OUT/'gaussians'/a.site/result/'membership.npz') as f:mem={k:f[k] for k in f.files}
        cloud=PlyData.read(str(model_path(a.site,result)/'point_cloud/iteration_30000/point_cloud.ply'),mmap='r')['vertex'].data
        xyz=np.column_stack([cloud[k] for k in ['x','y','z']])
        assert len(grad['photo'])==len(mem['floating'])
        for case,region in domains:
            for kind in ['floating','roof']:
                m=mem[kind].copy()
                if case!='전체':
                    c=geometry[case];m &= ((xyz>=c['crop_min'])&(xyz<=c['crop_max'])).all(1)
                n=int(m.sum())
                gp=float(np.median(grad['photo'][m])) if n else None;gd=float(np.median(grad['depth'][m])) if n else None
                original=next(x for x in grows if x['result']==result and x['case']==case and x['kind']==kind)
                assert n==original['count'],'Gaussian membership must match the population table exactly'
                gradient_rows.append(dict(site=a.site,result=result,case=case,kind=kind,count=n,
                    photo_centre_gradient_median=gp,depth_centre_gradient_median=gd,depth_over_photo=gd/gp if gp else None,
                    ratio_status='확인 불가: 사진 기울기 중앙값 0 또는 표본 없음' if not gp else 'PASS',
                    densified_opacity_fraction=original['densified_opacity_fraction'],gaussian_table_count=original['count'],
                    source=str(root/'centre_gradients.npz'),sample_status=original['sample_status']))
        print(a.site,result,'exact quantiles and gradient medians PASS',len(ids),flush=True)
        del z,ids,grad,mem,cloud,xyz
    suffix='' if a.prior=='ALS' else '_'+a.prior
    table(DOC/'tables'/f'forces_{a.site}{suffix}',rows,'깊이 항의 힘과 r/σ')
    table(DOC/'tables'/f'gradients_{a.site}{suffix}',gradient_rows,'가우시안 중심 기울기')

if __name__=='__main__':main()
