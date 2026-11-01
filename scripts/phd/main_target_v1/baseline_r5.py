"""Saved-model rendering and exact frozen target coverage; zero optimization steps."""
import sys
sys.path.insert(0,'/source')
from argparse import ArgumentParser
import numpy as np
import torch
from common import *
from arguments import ModelParams,PipelineParams
from scene import Scene,GaussianModel
from gaussian_renderer import render
from utils.general_utils import safe_state

def loadz(p):
    with np.load(p) as z:return {k:z[k] for k in z.files}

def count(depth,m,t):
    good=np.isfinite(m['depth'])&(m['depth']>0)&np.isfinite(m['sigma'])&(m['sigma']>0)
    rendered=np.isfinite(depth)&(depth>0);hit=good&rendered&(abs(depth-m['depth'])<=np.float32(1.96)*m['sigma'])
    has=m['owner']>=0;p=np.maximum(m['owner'],0)
    masks={'all':good,'prior':good&has,'background':good&~has,'prior_roof':good&has&(t['kind'][p]==1),'prior_wall':good&has&(t['kind'][p]==2)}
    masks.update({f'region_{i}':good&has&(t['region'][p]==i) for i in range(4)})
    masks.update({label:good&has&(t['any_replaced'][p]==flag) for label,flag in [('prior_original',False),('prior_replaced',True)]})
    return {k:dict(target_pixels=int(v.sum()),inside=int((v&hit).sum()),missing=int((v&~rendered).sum())) for k,v in masks.items()}

@torch.no_grad()
def main():
    cfg=json.loads((CFG/'diagnostics_r5.json').read_text());key=sys.argv[1];c=next(v for v in cfg['models'] if v['key']==key)
    root=OUT/'r5/baselines'/key;root.mkdir(parents=True,exist_ok=True)
    model=Path(c['model']);it=c['iteration'];ply=model/f'point_cloud/iteration_{it}/point_cloud.ply'
    paths=[ply,model/'cfg_args',model/'cameras.json',model/'input.ply',S0/'fork_inputs/s61/B173nb_b10/split.json']
    binding={str(p):sha(p) for p in paths if p.exists()};binding.update(config_sha256=sha(CFG/'diagnostics_r5.json'),runtime_sha256=sha(CFG/'target_v1.runtime.r4n.lock.json'))
    dump(root/'binding.json',binding)
    parser=ArgumentParser();lp=ModelParams(parser);pp=PipelineParams(parser)
    args=parser.parse_args(['-s',str(S0/'fork_inputs/s61/B173nb_b10'/f"scene_{c['scene_prior']}"),'-m',str(model),'--eval','-r','1','--data_device','cpu'])
    safe_state(False);g=GaussianModel(args.sh_degree);scene=Scene(lp.extract(args),g,load_iteration=it,shuffle=False);pipe=pp.extract(args);bg=torch.zeros(3,device='cuda')
    maps={p:OUT/'r2/stage1'/f'B173nb_b10_{p}'/'maps' for p in c['compare_priors']}
    indexes={p:json.loads((d/'index.json').read_text()) for p,d in maps.items()};targets={p:loadz(OUT/'r2/targets'/f'B173nb_b10_{p}.npz') for p in maps}
    totals={p:{} for p in maps};rows={p:[] for p in maps};rep=json.loads((CFG/'representatives_v1.json').read_text())['rows'][0]['camera']['name']
    cams=sorted(scene.getTrainCameras(),key=lambda x:x.image_name)
    assert all({x.image_name for x in cams}==set(ix['views']) for ix in indexes.values())
    (root/'renders').mkdir(exist_ok=True)
    for n,cam in enumerate(cams):
        pkg=render(cam,g,pipe,bg);depth=pkg['surf_depth'].squeeze().cpu().numpy();dest=root/'renders'/f'{cam.image_name}.npz'
        extra={} if cam.image_name!=rep else {'rgb':(pkg['render'].permute(1,2,0).clamp(0,1).cpu().numpy()*255).astype('u1')}
        np.savez_compressed(dest,depth=depth,**extra)
        for p in maps:
            v=indexes[p]['views'][cam.image_name];mp=maps[p]/v['file'];assert sha(mp)==v['sha256'];m=loadz(mp)
            assert depth.shape==m['depth'].shape
            assert np.allclose(cam.world_view_transform.T.cpu().numpy(),v['W2C'],atol=2e-5)
            counts=count(depth,m,targets[p]);rows[p].append(dict(camera=cam.image_name,sha256=sha(dest),**counts['all']))
            for label,a in counts.items():
                b=totals[p].setdefault(label,dict(target_pixels=0,inside=0,missing=0))
                for field in b:b[field]+=a[field]
        if n%20==0:print('BASELINE',key,n+1,len(cams),flush=True)
    for p in totals:
        for row in totals[p].values():
            den=row['target_pixels'];row.update(fraction=row['inside']/den if den else None,missing_fraction=row['missing']/den if den else None)
    dump(root/'coverage.json',dict(at=stamp(),key=key,iteration=it,gaussians=len(g.get_xyz),strata=totals,views=rows,model_sha256=binding[str(ply)],optimization_steps=0,scientific_verdict=None))
    print('BASELINE_DONE',key,{p:totals[p]['all']['fraction'] for p in totals},flush=True)
if __name__=='__main__':main()
