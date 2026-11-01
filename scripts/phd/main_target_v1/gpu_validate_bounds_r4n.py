"""Actual corrected runtime: inherited unit checks and complete saved-descendant numerical tests."""
import sys
sys.path.insert(0,'/source')
import torch,numpy as np
from argparse import ArgumentParser
from arguments import OptimizationParams
from common import *
from gpu_preflight_r2 import unit_check
from gpu_bounds_r4 import corrected
import jbgs_target

@torch.no_grad()
def main():
    lock=json.loads((CFG/'target_v1.runtime.r4n.lock.json').read_text())
    for name,digest in lock['files'].items():assert sha(REPO/name)==digest
    p=ArgumentParser();op=OptimizationParams(p);unit=unit_check(op.extract(p.parse_args([])))
    source=OUT/'r4/runs/tg_B173nb_b10_ALS_s0/model/target_monitor/snapshot_6000.npz'
    with np.load(source) as z:
        ids=z['init_id'];x=torch.as_tensor(z['xyz'],device='cuda');a=torch.as_tensor(z['anchor'][ids],device='cuda')
        n=torch.as_tensor(z['normal'][ids],device='cuda');s=torch.as_tensor(z['sigma'][ids],device='cuda')
    maximum=-1.;count=0
    for shift in [0.,.01,-.01,1.,-1.,10.,-10.]:
        input=x+shift*n;actual=jbgs_target.normal_projection(input,a,n,s)
        assert torch.equal(actual,corrected(input,a,n,s))
        error=(((actual.double()-a.double())*n.double()).sum(1).abs()-(1.96*s).double())
        assert torch.isfinite(actual).all() and float(error.max())<=3e-5
        maximum=max(maximum,float(error.max()));count+=len(x)
    result=dict(at=stamp(),status='PASS_CORRECTED_RUNTIME_BOUNDS',unit=unit,tested_positions=count,
        maximum_float64_residual_m=maximum,tolerance_m=3e-5,band_sigma_multiple=1.96,
        model_dtype='float32',projection_intermediates='float64',training_steps=0,scientific_verdict=None)
    dump(OUT/'r4n/verification/bounds.json',result);dump(DOC/'tables/runtime_bounds_r4n.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
