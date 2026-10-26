"""No optimizer: render a fixed checkpoint, check BOTH new depth masks."""
import ast
import json
import runpy
import sys
from pathlib import Path
import numpy as np
import torch
sys.path.insert(0,'/source')
import jbgs_judgment as JJ

cut=sys.argv.index('--');own=sys.argv[1:cut];train=sys.argv[cut+1:]
ARGS={own[i].lstrip('-'):own[i+1] for i in range(0,len(own),2)}
OUTD=Path(ARGS['probe_out']);OUTD.mkdir(parents=True,exist_ok=False)
# Reuse the exact existing checkpoint-id loader, without running its main.
source=Path('/repo/scripts/phd/main_fixtest_v1/probe_ckpt_ft.py')
node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='_load_ckpt')
exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'))
original=JJ.Judgment.__init__

def wrapped(self,args,opt,scene,gaussians,*a,**kw):
    original(self,args,opt,scene,gaussians,*a,**kw)
    ckpt=_load_ckpt(self,gaussians,opt)
    self.E_calls=max(self.E_calls,1);self.cur_iter=15000;self.update_E(15000,gaussians)
    rows=[]
    for cam in self.train_cams:
        name=cam.image_name
        with torch.no_grad():pkg=self.render_fn(cam,gaussians,self.pipe,self.background)
        D=pkg['surf_depth'].detach().clone().requires_grad_(True)
        P,M,A=self.P[name],self.M[name],self.A[name];loc=self.lt_locations[name].long()
        has=(loc>=0)&(loc<len(self.lt_values['v_prior']))
        on=has&torch.isfinite(P)&(P>0)
        ids=loc[on];mm=torch.isfinite(M[on])&(M[on]>0)&(A[on]>0)&torch.isfinite(self.lt_values['v_mvs'][ids])
        row=dict(view=name,expected_prior=int(on.sum()),expected_mvs=int(mm.sum()))
        for mode in ['fixed','dynamic']:
            args.jbgs_sw_depth_loss=mode
            m,p,stats=self.losses(name,{'surf_depth':D})
            grad,=torch.autograd.grad(m+p,D,retain_graph=False)
            assert torch.isfinite(grad).all() and torch.isfinite(m+p)
            assert stats['prior_n']==row['expected_prior'] and stats['mvs_n']==row['expected_mvs']
            assert (grad.squeeze(0)[~on]==0).all()
            row[mode]=dict(**stats,loss_mvs=float(m),loss_prior=float(p),gradient_finite=True,no_patch_gradient_zero=True)
        rows.append(row)
        del pkg,D,grad
    record=dict(status='PASS',views=rows,checkpoint=ckpt,optimizer_steps=0,
        rule='eligibility counts, including exact-zero residuals, are compared; nonzero-gradient counts are not the eligibility mask',scientific_verdict=None)
    (OUTD/'depth_masks.json').write_text(json.dumps(record,indent=2)+'\n')
    print('fixed/dynamic actual checkpoint pixel masks PASS',len(rows),'views',flush=True)
    raise SystemExit(0)

JJ.Judgment.__init__=wrapped
sys.argv=['train.py']+train
runpy.run_path('/source/train.py',run_name='__main__')
