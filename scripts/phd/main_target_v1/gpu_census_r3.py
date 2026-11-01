"""Uncapped initial background size census; geometry only, without filling unfinished u."""
import sys
sys.path.insert(0,'/source')
import numpy as np
import torch
from simple_knn._C import distCUDA2
from common import *

def main():
    site,prior=sys.argv[1:3];cfg,lock=locked_r3()
    root=OUT/'r3/census'/f'{site}_{prior}';root.mkdir(parents=True,exist_ok=False)
    seeds=OUT/'r3/prior_only'/f'{site}_{prior}/seeds.npz'
    geometry=OUT/'r2/background'/site/prior/'uncert'/f'patches_{site}_{prior}.npz'
    with np.load(seeds) as z:p=z['xyz']
    with np.load(geometry) as z:bg=z['centre'].astype('f4')
    combined=torch.as_tensor(np.r_[p,bg],device='cuda',dtype=torch.float32)
    # Identical operations to Target.__init__, including log/exp float32 rounding.
    scale=torch.exp(torch.log(torch.sqrt(torch.clamp_min(distCUDA2(combined),1e-7))))[len(p):].cpu().numpy()
    ids=np.flatnonzero(scale>1.);rank=np.lexsort((ids,-scale[ids]))[:10];top=ids[rank]
    np.savez_compressed(root/'initial_background_sizes.npz',xyz=bg,scale=scale,init_id=np.arange(len(bg))+len(p),large=scale>1.)
    record=dict(at=stamp(),site=site,prior=prior,prior_count=len(p),background_count=len(bg),count_gt_1m=len(ids),
        max_scale_m=float(scale.max()),scale_quantiles_m=np.quantile(scale,[0,.1,.5,.9,.99,1]).tolist(),
        top10=[dict(background_index=int(i),init_id=int(i+len(p)),xyz_local_m=bg[i].tolist(),scale_m=float(scale[i])) for i in top],
        seeds_sha256=sha(seeds),background_geometry_sha256=sha(geometry),config_sha256=lock['config_sha256'],
        sigma_not_used='geometry-only census; unfinished ring uncertainty is neither read nor replaced',
        stop_criterion=False,training_steps=0,scientific_verdict=None)
    dump(root/'initial_background_sizes.json',record);print('CENSUS_COMPLETE',site,prior,len(ids),float(scale.max()),flush=True)

if __name__=='__main__':main()
