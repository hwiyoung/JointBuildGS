"""Synthetic formula, compositing, gradient isolation, and AST checks (no training)."""
import ast
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,'/source')
import torch
import jbgs_freespace as F
from freespace_entry import instrument


def main():
    device='cuda';d=torch.tensor([10.,15.,99.,10.],device=device,requires_grad=True)
    src=[(torch.tensor([10.,10.,0.,11.],device=device),torch.full((4,),.1,device=device),
          torch.full((4,),.98,device=device),torch.tensor([1,1,0,1],device=device,dtype=torch.bool)),
         (torch.tensor([20.,20.,0.,10.],device=device),torch.full((4,),.1,device=device),
          torch.full((4,),.98,device=device),torch.tensor([1,1,0,1],device=device,dtype=torch.bool))]
    G,margins,responsibilities=F.source_gate(d,src)
    assert G[0]<.5 and G[3]<.5 and G[1]>.999999 and G[2]==0 and not G.requires_grad
    expected=.1*math.sqrt(2*math.log(.98/(.02*.1*.1*math.sqrt(2*math.pi))))
    assert abs(float(margins[0][0])-expected)<1e-7
    _,m,_=F.source_gate(d,[(torch.ones(4,device=device),torch.full((4,),10.,device=device),torch.full((4,),.01,device=device),torch.ones(4,device=device,dtype=torch.bool))])
    assert torch.isinf(m[0]).all()
    # The two centred surfels have rho=0 at the middle pixel, so alpha=opacity.
    from scene.cameras import Camera
    from scene.gaussian_model import GaussianModel
    import numpy as np
    cam=Camera(0,np.eye(3),np.zeros(3),math.pi/2,math.pi/2,torch.zeros((3,17,17)),None,'synthetic',0,data_device='cpu')
    g=GaussianModel(0)
    g._xyz=torch.nn.Parameter(torch.tensor([[0.,0.,3.],[0.,0.,4.]],device=device))
    g._scaling=torch.nn.Parameter(torch.log(torch.full((2,2),.4,device=device)))
    g._rotation=torch.nn.Parameter(torch.tensor([[1.,0.,0.,0.],[1.,0.,0.,0.]],device=device))
    g._opacity=torch.nn.Parameter(torch.logit(torch.tensor([[.3],[.4]],device=device)))
    feature=torch.tensor([.2,.8],device=device,requires_grad=True)
    image,_=F.feature_render(cam,g,feature)
    hand=.3*.2+(1-.3)*.4*.8
    assert abs(float(image[8,8])-hand)<1e-6,(float(image[8,8]),hand)
    gradient=torch.autograd.grad(image[8,8],[g._xyz,g._scaling,g._rotation,g._opacity,feature],allow_unused=True)
    assert all(x is None or torch.count_nonzero(x)==0 for x in gradient[:3])
    assert torch.count_nonzero(gradient[3])==2
    assert torch.allclose(gradient[4],torch.tensor([.3,.28],device=device),atol=1e-6,rtol=1e-6)
    # Colour adjoint gives sum w; multiplied by each f exactly gives P.
    assert torch.allclose(gradient[4]*feature,torch.tensor([.06,.224],device=device),atol=1e-6,rtol=1e-6)
    g.frozen_mask=torch.tensor([False,True],device=device)
    full=[torch.full((17,17),v,device=device) for v in [10.,.1,.98]]
    present=torch.ones((17,17),device=device,dtype=torch.bool)
    flags=F.centre_flags(cam,g,[(*full,present)],[torch.full((17,17),.5,device=device)],torch.ones(2,device=device,dtype=torch.bool))
    assert flags.tolist()==[float(full[2][0,0]),0.]
    assert F.centre_flags(cam,g,[(*full,present)],[torch.full((17,17),.5,device=device)],torch.zeros(2,device=device,dtype=torch.bool)).sum()==0
    code=instrument(Path('/source/train.py').read_text());compile(code,'freespace_executed_train.py','exec')
    assert code.count('jbgs_freespace.add_loss(')==1
    total=torch.tensor(2.,requires_grad=True);assert F.add_loss(total,None,None,None,None,None,500) is total
    result=dict(status='PASS',source_gate=G.tolist(),margin_expected=expected,
        absent_sources_zero=True,weak_source_no_freespace=True,detached_G=True,
        compositing=dict(actual=float(image[8,8]),hand=hand),
        geometry_gradient_exact_zero=True,opacity_gradient_nonzero=True,colour_adjoint_pressure_exact=True,
        protected_and_outside_f_zero=True,off_identity_without_arithmetic=True,
        integration_compiles=True,off_ten_view_replay='PENDING',optimizer_steps=0,scientific_verdict=None)
    root=Path('/out/freespace_v1');root.mkdir(exist_ok=True)
    (root/'unit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
