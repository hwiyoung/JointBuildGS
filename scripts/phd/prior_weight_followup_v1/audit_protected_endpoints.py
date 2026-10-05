"""CPU endpoint audit of order-preserved protected primitives; not render attribution."""
import gc,hashlib,json,sys
from pathlib import Path
import numpy as np
import torch

assert Path('/.dockerenv').exists()
p=Path('/payload');out=Path('/out');cfg=json.loads((out/'config.json').read_text())
b=p/cfg['bundle'];base=p/cfg['base_root'];g=p/cfg['global_root']
files={}
def record(path):files[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();return path
def stats(a):
 a=np.asarray(a,dtype=float)
 return dict(n=a.size,mean=float(a.mean()),median=float(np.median(a)),p95=float(np.quantile(a,.95))) if a.size else dict(n=0)
def load(path):
 record(path);s=torch.load(path,map_location='cpu',weights_only=False);mask=s['frozen_mask'].bool();model=s['model']
 row=dict(iteration=s['iteration'],total=model[1].shape[0],protected=int(mask.sum()),hook=s['hook_state'])
 for key,index in [('xyz',1),('scale_log',4),('rotation',5),('opacity_logit',6)]:row[key]=model[index].detach().cpu()[mask].numpy().copy()
 del s,model;gc.collect();return row
anchor=base/'runs/P1/D005_Pnative/model/jbgs_complete/iteration_8000/checkpoint.pth'
current=b/'P1/train/alpha_4/model/jbgs_complete/iteration_30000/checkpoint.pth'
a,z=load(anchor),load(current)
assert a['protected']==z['protected'] and not a['hook']['release'] and not z['hook']['release']
# Protected order survives append-only densification and stable-filter pruning, which exclude protected entries.
source=b/'P1/source/scene/gaussian_model.py';text=record(source).read_text()
assert 'prune_mask = torch.logical_and(prune_mask, ~self.frozen_mask)' in text
assert text.count('selected_pts_mask = torch.logical_and(selected_pts_mask, ~self.frozen_mask)')==2
binding=json.loads(record(g/'inputs_v2/P1/bindings.json').read_text());c=binding['train'][0]
assert c['name']=='DJI_20241217084553_0100_D.JPG'
labels=np.load(record(b/'P1/mask/r1_mask.npz'))['region_id']
xc=a['xyz']@np.array(c['R']).T+np.array(c['t']);uvh=xc@np.array(c['K']).T;uv=np.rint(uvh[:,:2]/uvh[:,2:]).astype(int)
inside=(xc[:,2]>0)&(uv[:,0]>=0)&(uv[:,1]>=0)&(uv[:,0]<labels.shape[1])&(uv[:,1]<labels.shape[0])
r1=np.zeros(len(inside),bool);r1[inside]=labels[uv[inside,1],uv[inside,0]]==1
opacity_a=torch.sigmoid(torch.from_numpy(a['opacity_logit'])).numpy().ravel();opacity_z=torch.sigmoid(torch.from_numpy(z['opacity_logit'])).numpy().ravel()
result=dict(status='PASS_PROTECTED_ENDPOINT_AUDIT',scientific_verdict=None,scope='Protected cohort only; R1 is initial-center projection, not a visibility or prior-surface attribution mask',
    correspondence='Source-verified preserved relative order among protected primitives; equal protected counts checked',
    anchor=dict(iteration=a['iteration'],total=a['total'],protected=a['protected']),final=dict(iteration=z['iteration'],total=z['total'],protected=z['protected']),cohorts={})
for name,s in [('all_protected',np.ones(len(r1),bool)),('initial_center_in_0100_R1',r1)]:
 d=z['xyz'][s]-a['xyz'][s]
 result['cohorts'][name]=dict(displacement_m=stats(np.linalg.norm(d,axis=1)),signed_z_change_m=stats(d[:,2]),
   opacity_anchor=stats(opacity_a[s]),opacity_final=stats(opacity_z[s]),opacity_change=stats(opacity_z[s]-opacity_a[s]),
   final_opacity_below_001=float((opacity_z[s]<.01).mean()),final_opacity_below_01=float((opacity_z[s]<.1).mean()),
   max_axis_scale_ratio=stats(np.exp(z['scale_log'][s]-a['scale_log'][s]).max(axis=1)))
result.update(inputs=files,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),config_sha256=hashlib.sha256((out/'config.json').read_bytes()).hexdigest(),torch=torch.__version__,python=sys.version)
(out/'endpoint_audit.json').write_text(json.dumps(result,indent=2,allow_nan=False));print(json.dumps({k:result[k] for k in ['anchor','final','cohorts']},indent=2))
