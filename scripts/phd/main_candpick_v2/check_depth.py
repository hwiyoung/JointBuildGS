"""Numerical check of contributor reconstruction against native gsplat channels."""
import torch
from engine import Scene
from depth_rule import expected_depth
from cp2_common import *

def main():
    unit='B173_LoD2';s=Scene(unit,'v1','right');v=arrays(OUT/'depth_views'/unit/'selected_pixels.npz')
    j=int(np.argmax(np.bincount(v['view_index'])));cam=s.cams[j]
    pixels=torch.as_tensor(np.unique(v['pixel_index'][v['view_index']==j]),device='cuda',dtype=torch.long)
    with torch.no_grad():
        r=s.render(cam,depth=True);depth,check=expected_depth(r[-1],pixels)
        ids=check['pixel_ids'];native=r[0][0,...,-1].reshape(-1)[ids];alpha=r[1][0,...,0].reshape(-1)[ids]
        ce=float((native-check['center_expected']).abs().max());ae=float((alpha-check['alpha']).abs().max())
        assert ce<.002 and ae<2e-5,(ce,ae)
        report=dict(status='PASS',at=now(),unit=unit,view=cam['name'],pixels=len(ids),
            max_center_depth_error_m=ce,max_alpha_error=ae,
            below_near_count=check['below_geogs_near_count'],nonfinite_ray_count=check['nonfinite_ray_depth'],
            ray_vs_center_median_abs_m=float(torch.nanmedian((depth[ids]-native).abs())),source=SOURCE,scientific_verdict=None)
    save(OUT/'preflight/depth_rule.json',report);print(clean(report),flush=True)

if __name__=='__main__':main()
