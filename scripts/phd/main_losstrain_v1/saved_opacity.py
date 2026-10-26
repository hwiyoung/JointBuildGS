"""Read saved 15k/30k PLY populations; no training or inferred birth labels."""
import argparse,json,math
from pathlib import Path
import numpy as np
import torch
from scipy.special import expit
from plyfile import PlyData
from inputs import OUT,PH,SITES,PRIORS,save,sha

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site');ap.add_argument('--prior');ap.add_argument('--result');a=ap.parse_args()
    ns=dict(json=json,math=math,np=np,torch=torch,ORIGIN_PRIOR=1)
    exec(Path('/repo/scripts/phd/main_losstrain_v1/r17_monitor.py').read_text(),ns)
    units=[(s,p,'nojudge_'+p+'_s0') for s in SITES for p in PRIORS] if not a.result else [(a.site,a.prior,a.result)]
    for site,prior,result in units:
        if result.startswith('nojudge'):
            model=PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs'/site/result/'model'
        else:
            root=OUT/'runs'/site/result
            if (root/'PASS.json').exists():attempt=json.loads((root/'PASS.json').read_text())['attempt']
            elif result=='lt_fixgt_ALS_s0' and site=='B173nb_b10':attempt=1
            else:raise ValueError('model not available')
            model=root/f'attempt_{attempt}/model'
        with np.load(OUT/'direct_stage1_v2'/(site+'__'+prior)/'evaluation.npz') as z:cell=z['cell']
        init=model/'monitor/init_points.npz'
        with np.load(init) as z:loc=z['location'][z['planted'].astype(bool)].astype(np.int64)
        initial_cell=np.full(len(loc),6,dtype=np.int8);valid=(loc>=0)&(loc<len(cell));initial_cell[valid]=cell[loc[valid]]
        for iteration in [15000,30000]:
            ply=model/f'point_cloud/iteration_{iteration}/point_cloud.ply'
            if not ply.exists():continue
            dest=OUT/'opacity_saved'/site/result/f'{iteration}.json'
            if dest.exists():print('reuse',site,result,iteration,flush=True);continue
            vertex=PlyData.read(str(ply))['vertex'].data
            ids=np.array(vertex['init_id'],dtype=np.int64);origin=np.array(vertex['origin'])
            opacity=expit(np.array(vertex['opacity'],dtype=np.float64))
            assert np.isfinite(opacity).all(),'nonfinite saved opacity'
            birth=model/'monitor'/f'losstrain_birth_{iteration}.npz';initial=None
            if birth.exists():
                with np.load(birth) as z:initial=z['initial_survivor']
                assert len(initial)==len(ids)
            groups=ns['lt_population_summary'](opacity,origin,ids,initial_cell,initial)
            row=dict(site=site,prior=prior,result=result,iteration=iteration,groups=groups,
                mutually_exclusive_birth_status='available' if initial is not None else '기록 없음',
                definition='saved PLY float64 sigmoid(logit opacity); origin and initial GT patch lineage; GT diagnostic only',
                sources=dict(model=str(ply),model_sha256=sha(ply),init=str(init),init_sha256=sha(init)),
                optimizer_steps=0,scientific_verdict=None)
            save(dest,row);save(Path('/docs/tables/opacity_saved')/site/result/f'{iteration}.json',row)
            print(site,result,iteration,'saved opacity PASS',groups['all'],flush=True)

if __name__=='__main__':main()
