"""CPU validation of the diagnostic loss adapter against the unchanged r17 API."""
import ast
import math
import sys
from types import SimpleNamespace
import numpy as np
import torch
from common import *

source=Path('/repo/src/phd/forks/GeoGS-conf-guided-v1-r17')
sys.path.insert(0,str(source))
import jbgs_judgment as JJ
path=Path(__file__).with_name('diagnose_gpu.py')
nodes=[n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in ['terms','dynamic_peak']]
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'))
torch.set_default_dtype(torch.float64)
D=torch.tensor([[[9.2,9.95,10.,10.1],[10.3,11.1,13.,16.]]],requires_grad=True)
P=torch.full((2,4),10.);M=P+.1;A=torch.ones_like(P);A[1,2]=0
sigma=torch.tensor([.03,.2,.03,.2,.03,.2,.03,.2]);V=torch.tensor([.5,.98]*4)
j=SimpleNamespace(P={'test':P},M={'test':M},A={'test':A},TAU={'test':torch.full_like(P,.2)},
    GW={'test':torch.ones_like(P)},W={},NOTRUNC={},mode='P',
    sw={'prior':True,'prior_band':True},fix={'prior_share_band':False,'own_depth_release':False},ab={'tolerance_band':False},
    lt_locations={'test':torch.arange(8).reshape(2,4)},lt_values=dict(v_prior=V,v_mvs=V,
    sigma_prior=sigma,sigma_mvs=sigma,normal=torch.tensor([[0.,0.,1.]]*8),fallback=torch.zeros(8,dtype=torch.bool)),
    lt_cameras={'test':SimpleNamespace(projection_matrix=torch.eye(4),world_view_transform=torch.eye(4))},
    args=SimpleNamespace(jbgs_sw_depth_loss='dynamic',jbgs_depth_norm='pixels',jbgs_trunc_hi=4.))
rows=[]
for mode,lam in [('dynamic',.0025),('current',.05)]:
    j.args.jbgs_sw_depth_loss=mode
    exact=JJ.Judgment.losses(j,'test',{'surf_depth':D})[:2]
    adapter=terms(D,j,mode)
    for term,a,b in zip(['mvs','prior'],exact,adapter):
        a=a*lam
        ga,=torch.autograd.grad(a,D,retain_graph=True)
        gb,=torch.autograd.grad(b,D,retain_graph=True)
        assert torch.equal(a,b) and torch.equal(ga,gb)
        rows.append(dict(mode=mode,term=term,loss=float(a),bit_identical_loss_and_gradient=True))
peak=dynamic_peak(sigma,V)
t=torch.linspace(0,15,200001)
for i in range(len(sigma)):
    loga=torch.log(V[i])-torch.log1p(-V[i])-torch.log(sigma[i])-math.log(.1*math.sqrt(2*math.pi))
    dense=(.0025*torch.sigmoid(loga-.5*t*t)*t/sigma[i]).max()
    assert abs(float(peak[i]-dense))/float(peak[i])<1e-8
save(DOC/'provenance/diagnostic_loss_adapter.json',dict(at=now(),status='PASS',rows=rows,
    peak_check='32-step root solve agrees with 200001-point dense maximum within relative 1e-8',
    implementation_sha256=sha(path),source_sha256=sha(source/'jbgs_judgment.py'),optimizer_steps=0,scientific_verdict=None))
print('exact r17 diagnostic adapter and per-pixel maximum-force checks PASS')
