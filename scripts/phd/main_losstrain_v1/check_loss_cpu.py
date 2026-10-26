"""Independent Appendix C.4 loss/derivative checks and mask/default regressions."""
import importlib.util
import math
import sys
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import torch
from inputs import OUT, save

def module(revision):
    root=Path('/repo/src/phd/forks')/f'GeoGS-conf-guided-v1-{revision}'
    sys.path.insert(0,str(root))
    spec=importlib.util.spec_from_file_location('lt_'+revision,root/'jbgs_judgment.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m

def reference(z,zi,s,v,mode):
    r=z-zi
    if mode=='fixed':return .5*v*r*r/(s*s),v*r/(s*s)
    N=math.exp(-r*r/(2*s*s))/(s*math.sqrt(2*math.pi))
    den=v*N+(1-v)*.1
    return -math.log(den),(v*N/den)*r/(s*s)

def main():
    r16,r17=module('r16'),module('r17')
    cases=[]
    for dtype in [torch.float64,torch.float32]:
        for mode in ['fixed','dynamic']:
            for delta in [0,.01,.1,1,6]:
                for sigma in [.03,.20]:
                    for v in [.001,.5,.98]:
                        for both in [False,True]:
                            z=torch.tensor(delta,dtype=dtype,requires_grad=True)
                            # Evaluate the independent reference at exactly the represented inputs.
                            s=torch.tensor(sigma,dtype=dtype);p=torch.tensor(v,dtype=dtype)
                            targets=[0.,.37] if both else [0.]
                            terms=[r17.lt_term(z,torch.tensor(t,dtype=dtype),s,p,mode) for t in targets]
                            loss=sum(terms);grad=torch.autograd.grad(loss,z)[0].item()
                            expected=[reference(z.item(),torch.tensor(t,dtype=dtype).item(),s.item(),p.item(),mode) for t in targets]
                            refL=sum(t[0] for t in expected);refG=sum(t[1] for t in expected)
                            le=abs(loss.item()-refL)/max(abs(refL),1e-12)
                            ge=abs(grad-refG)/max(abs(refG),1e-12)
                            cases.append(dict(dtype=str(dtype),mode=mode,residual_m=delta,sigma_m=sigma,V=v,two_sources=both,
                                loss=loss.item(),reference_loss=refL,gradient=grad,reference_gradient=refG,
                                loss_relative_error=le,gradient_relative_error=ge,pass_check=le<=1e-4 and ge<=1e-4))
    def make(mode,D):
        t=lambda x:torch.tensor(x,dtype=D.dtype)
        j=NS(args=NS(jbgs_sw_depth_loss=mode,jbgs_depth_norm='pixels',jbgs_trunc_hi=4),
            mode='P',sw={'prior':True,'prior_band':True},ab={'tolerance_band':False},fix={'prior_share_band':False,'own_depth_release':False},
            P={'cam':t([[2,2,2],[2,2,2]])},M={'cam':t([[2.1,float('nan'),2.1],[2.1,2.1,0]])},
            A={'cam':t([[1,1,1],[0,1,1]])},TAU={'cam':torch.ones_like(D)*.2},GW={'cam':torch.ones_like(D)},
            lt_locations={'cam':torch.tensor([[0,0,-1],[1,1,-1]])},
            lt_values={'sigma_prior':t([.03,.2]),'sigma_mvs':t([.04,.2]),'v_mvs':t([.98,float('nan')]),
                'v_prior':t([.999,.001]),'normal':t([[0,0,1],[0,0,1]]),'fallback':torch.tensor([False,True])})
        proj=torch.eye(4,dtype=D.dtype);proj[0,0]=2;proj[1,1]=2
        j.lt_cameras={'cam':NS(projection_matrix=proj.T,world_view_transform=torch.eye(4,dtype=D.dtype))}
        return j
    masks=[]
    for mode in ['fixed','dynamic']:
        D=torch.full((2,3),2.01,dtype=torch.float64,requires_grad=True)
        j=make(mode,D);m,p,stats=r17.lt_losses(j,'cam',{'surf_depth':D[None]})
        grad=torch.autograd.grad(m+p,D)[0]
        assert stats['prior_n']==4 and stats['mvs_n']==1 and stats['fallback_n']==2
        assert torch.equal(grad[:,2],torch.zeros(2,dtype=D.dtype))
        assert torch.isfinite(grad).all()
        # A missing MVS value must be excluded before arithmetic, so NaN cannot leak into backward.
        masks.append(dict(mode=mode,**stats,gradient_finite=True,no_patch_depth_gradient_zero=True))
    D=torch.tensor([[2.,2.1,2.8],[2.7,3.,0.]],requires_grad=True)
    j=make('current',D)
    a=r16.Judgment.losses(j,'cam',{'surf_depth':D[None]})
    b=r17.Judgment.losses(j,'cam',{'surf_depth':D[None]})
    assert torch.equal(a[0],b[0]) and torch.equal(a[1],b[1]) and a[2]==b[2]
    ga=torch.autograd.grad(a[0]+a[1],D,retain_graph=True)[0]
    gb=torch.autograd.grad(b[0]+b[1],D)[0]
    assert torch.equal(ga,gb)
    result=dict(task_id='PHD-MAIN-LOSSTRAIN-v1',gate='PASS' if all(c['pass_check'] for c in cases) else 'STOP',
        checks=len(cases),relative_error_floor=1e-12,tolerance=1e-4,cases=cases,mask_checks=masks,
        default_cpu_loss_and_depth_gradient_equal=True,
        six_unit_initialization_and_checkpoint_check='NOT_RUN; CPU synthetic regression is not the order 6.2 gate',
        scientific_verdict=None)
    save(OUT/'checks/loss_cpu.json',result);save('/docs/tables/loss_cpu.json',result)
    print(result['gate'],len(cases),'max loss error',max(c['loss_relative_error'] for c in cases),
          'max gradient error',max(c['gradient_relative_error'] for c in cases))
    assert result['gate']=='PASS'

if __name__=='__main__':main()
