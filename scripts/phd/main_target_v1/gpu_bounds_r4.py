"""Reproduce float32 projection residuals and check a double-intermediate numerical correction."""
import sys
sys.path.insert(0,'/source')
import torch,numpy as np
import jbgs_target
from common import *

@torch.no_grad()
def corrected(x,anchor,normal,sigma):
    xd=x.double();a=anchor.double();n=normal.double()
    h=((xd-a)*n).sum(1);limit=(1.96*sigma).double()
    hclip=torch.maximum(torch.minimum(h,limit),-limit)
    return (xd+((hclip-h)/(n*n).sum(1))[:,None]*n).to(x.dtype)

@torch.no_grad()
def main():
    root=OUT/'r4/bounds_diagnosis';root.mkdir(exist_ok=False)
    p=OUT/'r4/runs/tg_B173nb_b10_ALS_s0/model/target_monitor/snapshot_6000.npz'
    with np.load(p) as z:
        ids=z['init_id'];x=torch.as_tensor(z['xyz'],device='cuda');a=torch.as_tensor(z['anchor'][ids],device='cuda')
        n=torch.as_tensor(z['normal'][ids],device='cuda');sigma=torch.as_tensor(z['sigma'][ids],device='cuda')
    rows=[];worst=None
    for shift in [0.,.01,-.01,1.,-1.,10.,-10.]:
        point=x+shift*n
        old=jbgs_target.normal_projection(point,a,n,sigma);new=corrected(point,a,n,sigma)
        for method,result in [('old_float32',old),('double_intermediate',new)]:
            e32=((result-a)*n).sum(1).abs()-1.96*sigma
            e64=((result.double()-a.double())*n.double()).sum(1).abs()-(1.96*sigma).double()
            row=dict(shift_m=shift,method=method,max_excess_float32_m=float(e32.max()),violations_float32=int((e32>3e-5).sum()),
                max_excess_float64_m=float(e64.max()),violations_float64=int((e64>3e-5).sum()))
            rows.append(row)
            if method=='old_float32' and (worst is None or row['max_excess_float32_m']>worst['excess']):
                i=int(e32.argmax());worst=dict(excess=row['max_excess_float32_m'],index=i,init_id=int(ids[i]),shift_m=shift,
                    before=point[i].cpu().tolist(),old=old[i].cpu().tolist(),corrected=new[i].cpu().tolist(),
                    anchor=a[i].cpu().tolist(),normal=n[i].cpu().tolist(),sigma=float(sigma[i]),normal_norm2=float((n[i].double()**2).sum()))
            if method=='double_intermediate':assert row['violations_float32']==0 and row['violations_float64']==0,row
    inside=(((x.double()-a.double())*n.double()).sum(1).abs()<=(1.96*sigma).double())
    assert torch.equal(corrected(x,a,n,sigma)[inside],x[inside])
    result=dict(at=stamp(),status='PASS_NUMERICAL_PROJECTION_CANDIDATE',rows=rows,worst_example=worst,
        unchanged_inside_count=int(inside.sum()),tolerance_m=3e-5,band_sigma_multiple=1.96,source_snapshot_sha256=sha(p),
        actual_6100_tensor='not saved; exact failing point cannot be recovered from the STOP scalar',
        conclusion='reproduction uses actual saved 6000 descendants with deterministic normal displacements, not a replay of iteration6100',
        training_steps=0,scientific_verdict=None)
    dump(root/'diagnosis.json',result);dump(DOC/'tables/normal_projection_diagnosis_r4.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
