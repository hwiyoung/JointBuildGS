"""Read-only mask endpoint/ray audit; no geometry truth or training modification."""
import hashlib
import json
from pathlib import Path
import numpy as np
from matplotlib.path import Path as Polygon
from scipy.spatial import cKDTree

def read(p):
    return json.loads(Path(p).read_text())
def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

cfg = read('/config.json')
root, inputs, review, out = [Path(cfg[k]) for k in ['root', 'inputs', 'review', 'out']]
r = read(root/'R1/masks/receipt.json')
assert sha(root/'R1/masks/receipt.json') == read(root/'R1/local_prior0/local_mask_binding.json')['receipt_sha256']
views = {Path(v['name']).stem: v for v in read(inputs/'scene/split_manifest.json')['train']}
zones = read(review/'config.json')['zones']
theta=np.deg2rad(70);basis=np.array([[np.cos(theta),np.sin(theta)],[np.sin(theta),-np.cos(theta)]])
def zone_ids(points):
    uv=points[:,:2]@basis.T;z=np.zeros(len(points),np.uint8)
    for row in zones[1:]:
        z[Polygon(row['polygon']).contains_points(uv,radius=1e-9)] = int(row['id'][1:])
    return z

j=np.load(review/'surface_judgments.npz');result=dict(scientific_verdict=None,
    mask_receipt_sha256=sha(root/'R1/masks/receipt.json'),source_samples={},endpoints={},rays={})
for src, label in [(0,'mvs'),(1,'prior')]:
    q=(j['source']==src)&(j['judgment']==2)
    result['source_samples'][label]={str(k):int(v) for k,v in zip(*np.unique(j['zone'][q],return_counts=True))}
roof=j['xyz'][(j['source']==0)&(j['zone']==6)&(j['part']==1)]
roof_z=float(np.median(roof[:,2]));result['z06_reference_roof_z']=roof_z
counts={k:np.zeros(14,np.int64) for k in ['prior','mvs']};bounds={k:[] for k in counts}
raycounts={str(dz):0 for dz in [0,5,10,20]};focus_counts={str(z):0 for z in [-18,-15,-12]};total=0;verified=0
for row in r['masks']:
    file=root/'R1/masks'/row['path'];assert sha(file)==row['sha256'];verified+=1
    if not row['pixels']:continue
    mask=np.load(file);y,x=np.nonzero(mask);assert len(y)==row['pixels'];total+=len(y)
    v=views[row['name']];K=np.array(v['K']);R=np.array(v['R']);t=np.array(v['t']);center=-t@R
    pd=np.load(inputs/'prior/raw_depth'/file.name,mmap_mode='r')[y,x]
    md=np.load(inputs/'mvs_rgb/raw_depth'/file.name,mmap_mode='r')[y,x]
    assert np.all(np.isfinite(pd)&(pd>0)&np.isfinite(md)&(md>pd+1))
    for label,offset,depth in [('prior',.5,pd),('mvs',0,md)]:
        direction=np.column_stack([x+offset,y+offset,np.ones(len(x))])@np.linalg.inv(K).T@R
        xyz=center+direction*depth[:,None];counts[label]+=np.bincount(zone_ids(xyz),minlength=14)
        bounds[label].append([xyz.min(0),xyz.max(0)])
        if label=='prior':
            for dz in [0,5,10,20]:
                distance=(roof_z+dz-center[2])/direction[:,2]
                p=center+direction*distance[:,None]
                raycounts[str(dz)]+=int(((distance>0)&(zone_ids(p)==6)).sum())
            for z in [-18,-15,-12]:
                distance=(z-center[2])/direction[:,2];p=center+direction*distance[:,None];uv=p[:,:2]@basis.T
                inside=(uv[:,0]>=-40)&(uv[:,0]<=-10)&(uv[:,1]>=-42)&(uv[:,1]<=-24)
                focus_counts[str(z)]+=int(((distance>0)&inside).sum())
assert total==r['total_pixels']
result.update(status='PASS_MASK_EXTENT_AUDIT',verified_mask_files=verified,total_mask_pixels=total,
              contributing_views=r['contributing_views'])
for label in counts:
    a=np.array(bounds[label]);result['endpoints'][label]=dict(zone_counts=counts[label].tolist(),
         min=a[:,0].min(0).tolist(),max=a[:,1].max(0).tolist())
result['rays']=dict(z06_intersections_at_roof_z_plus_m=raycounts,
    floater_focus_intersections_at_absolute_local_z=focus_counts,
    meaning='Masked image rays intersect Z06 XY at these diagnostic horizontal planes; not proof of rendered contribution or causal origin.')
with (out/'mask_extent.json').open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False))
