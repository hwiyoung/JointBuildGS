"""8.5 stage-2 fate definition, with this order's stage-1 cells and unrounded counts."""
import argparse
import json
import sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0,'/repo')
from src.phd.metrics_v3.surface import MeshScene
from inputs import OUT,PH,S1,SITES,PRIORS,save,sha

def model_path(site,result):
    if result.startswith('lt_'):
        root=OUT/'runs'/site/result
        p=json.loads((root/'PASS.json').read_text())
        return root/f"attempt_{p['attempt']}"/'model'
    assert result.startswith('nojudge_')
    root=PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs'/site/result
    finite=root.with_name(result+'.finite')
    return (finite if finite.exists() else root)/'model'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('site',choices=SITES);ap.add_argument('prior',choices=PRIORS);ap.add_argument('results',nargs='+');a=ap.parse_args()
    root=OUT/'direct_stage1_v2'/(a.site+'__'+a.prior)
    with np.load(root/'evaluation.npz') as e:
        cell=e['cell'];ok=e['in_eval']&e['scoring_allowed'];area=e['area']
    regions={'prior_wrong_1_3':ok&np.isin(cell,[1,3]),'prior_correct_0_2':ok&np.isin(cell,[0,2])}
    with np.load(S1/'defs'/a.site/f'prior_{a.prior}.npz') as p:
        scene=MeshScene(p['V'].astype(np.float64),p['F'].astype(np.int64))
    gp=S1/'defs'/a.site/'gt_classes.npz'
    with np.load(gp) as g:
        x=[g['xyz_gt_points'][g['use_gt_points']].astype(np.float64)]
        if 'xyz_gt_primary' in g.files:x.append(g['xyz_gt_primary'][g['use_gt_primary']].astype(np.float64))
    tree=cKDTree(np.concatenate(x));del x
    for res in a.results:
        dest=OUT/'fates'/a.site/(a.prior+'__'+res+'.json');assert not dest.exists()
        md=model_path(a.site,res);ipath=md/'monitor/init_points.npz';gpath=md/'dump/iteration_30000/gaussians.npz'
        if not ipath.exists() or not gpath.exists():
            save(dest,dict(status='UNAVAILABLE',reason='initial points or final dump absent',model=str(md),scientific_verdict=None));continue
        with np.load(ipath) as z:ip={k:z[k] for k in ['xyz','planted','location','origin']}
        with np.load(gpath) as z:gz={k:z[k] for k in ['init_xyz','init_id','init_last_seen','xyz','origin','opacity']};gz.update({k:z[k] for k in ['init_removed_at'] if k in z.files})
        planted=ip['planted'].astype(bool);assert np.array_equal(ip['xyz'][planted],gz['init_xyz'])
        loc=ip['location'].astype(np.int64);init_ids=np.cumsum(planted)-1
        org=gz['origin'];op=gz['opacity'];iid=gz['init_id'].astype(np.int64);xyz=gz['xyz'].astype(np.float64)
        assert np.isfinite(xyz).all() and np.isfinite(op).all(),'nonfinite final dump; stop and record'
        out=dict(site=a.site,prior=a.prior,result=res,status='PASS',regions={},sources=dict(initial=str(ipath),initial_sha256=sha(ipath),dump=str(gpath),dump_sha256=sha(gpath),gt=str(gp)),
            definition='stage2: seed+descendants by init_id; removed, opaque>=0.5 within prior mesh 0.25m, else opaque within GT points 0.2m, else neither; same priority for both cell groups',scientific_verdict=None)
        for label,region in regions.items():
            inreg=(ip['origin']==1)&(loc>=0)&region[np.maximum(loc,0)]
            sid=init_ids[inreg&planted];selected=np.zeros(len(gz['init_xyz']),bool);selected[sid]=True
            desc=(org==1)&(iid>=0)&selected[np.maximum(iid,0)];opaque=desc&(op>=.5)
            dp=scene.distance(xyz[opaque]);dg=tree.query(xyz[opaque],distance_upper_bound=1.)[0]
            alive=np.zeros(len(selected),bool);alive[np.unique(iid[desc])]=True
            old=np.zeros(len(selected),bool);new=np.zeros(len(selected),bool)
            old[np.unique(iid[opaque][dp<=.25])]=True;new[np.unique(iid[opaque][dg<=.2])]=True
            cat=np.full(len(sid),3,np.int8);cat[~alive[sid]]=0;cat[alive[sid]&old[sid]]=1;cat[alive[sid]&~old[sid]&new[sid]]=2
            names=['removed','old_place','current_surface','neither'];last=gz['init_last_seen'][sid];rm=last[cat==0]
            out['regions'][label]=dict(patches=int(region.sum()),area_m2=float(area[region].sum()),seeds_seated=int(inreg.sum()),
                seeds_planted=len(sid),not_planted=int((inreg&~planted).sum()),counts={name:int((cat==i).sum()) for i,name in enumerate(names)},
                shares={name:float((cat==i).mean()) if len(sid) else None for i,name in enumerate(names)},
                descendants=int(desc.sum()),opaque_descendants=int(opaque.sum()),last_alive_of_removed=dict(zip(['min','median','max'],map(float,np.percentile(rm,[0,50,100])))) if len(rm) else None)
            dest.parent.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(dest.with_name(dest.stem+'__'+label+'.npz'),init_id=sid,category=cat,init_last_seen=last,
                **({'init_removed_at':gz['init_removed_at'][sid]} if 'init_removed_at' in gz else {}))
        save(dest,out);save(Path('/docs/tables/fates')/a.site/dest.name,out);print(a.site,a.prior,res,'fates PASS',flush=True)

if __name__=='__main__':main()
