"""Distances to original loss targets at each saved formation time; no training."""
import cv2
import numpy as np
from common import *
from recount import load_eval
from reduce_diagnostics import table
rows=[]
for site in SITES:
    e,_=load_eval(site,'ALS');cases={c['id']:c for c in json.loads((CFG/f'cases_ALS.json').read_text())['cases'] if c['site']==site}
    for recpath in sorted((OUT/'formation'/site).glob('*/iteration_*/receipt.json')):
        rec=json.loads(recpath.read_text())
        for r in rec['rows']:
            path=recpath.parent/(r['view']+'.npz')
            with np.load(path) as f:z={k:f[k] for k in f.files}
            ids=z['patch_id'];xy=e['centre'][ids,:2];b=np.array(cases[r['case']]['bbox'])
            selected=z['early_floating']&((xy>=b[:2]-3)&(xy<=b[2:]+3)).all(1)
            y,x=z['pixel_y'],z['pixel_x'];D=z['depth'][y,x];K=z['intrinsic'];inv=np.linalg.inv(z['world_to_camera'])
            ray=np.column_stack([(x-K[0,2])/K[0,0],(y-K[1,2])/K[1,1],np.ones(len(x))]);worldray=ray@inv[:3,:3].T
            # Camera-Z residual -> local normal distance without the loss's
            # 0.25 cosine clamp; also retain camera-Z distance explicitly.
            factor=np.abs((worldray*e['normal'][ids]).sum(1))
            for term,folder in [('prior','prior_ALS'),('mvs','mvs')]:
                base=S0/'fork_inputs/s61'/site/'maps'/folder
                if (base/'raw_depth').exists():base=base/'raw_depth'
                target=np.load(base/(r['view']+'.npy'))
                if target.shape!=z['depth'].shape:target=cv2.resize(target.astype(np.float32),(z['depth'].shape[1],z['depth'].shape[0]),interpolation=cv2.INTER_NEAREST)
                m=selected.copy()
                if term=='mvs':m&=z['has_mvs']
                residual=(D-target[y,x])[m];normal=residual*factor[m];n=len(residual)
                rows.append(dict(site=site,result=rec['result'],case=r['case'],iteration=rec['iteration'],term=term,pixels=n,
                    camera_z_abs_q25_q50_q75_q90=np.quantile(np.abs(residual),[.25,.5,.75,.9]).tolist() if n else None,
                    normal_abs_q25_q50_q75_q90=np.quantile(np.abs(normal),[.25,.5,.75,.9]).tolist() if n else None,
                    normal_distance_over_20cm_fraction=float((np.abs(normal)>.2).mean()) if n else None,
                    camera_z_distance_over_20cm_fraction=float((np.abs(residual)>.2).mean()) if n else None,
                    source=str(path),target_source=str(base/(r['view']+'.npy')),scientific_verdict=None))
table(DOC/'tables/formation_target_distances',rows,'앞 반복 뜬 면 화소와 학습 자료의 거리 · 시선 Z 및 법선 m')
print('formation target distance rows',len(rows))
