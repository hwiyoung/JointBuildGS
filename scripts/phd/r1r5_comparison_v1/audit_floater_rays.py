"""Test masked rays against a displayed floater mesh crop; diagnostic, not causality."""
import hashlib
import json
from pathlib import Path
import numpy as np
import open3d as o3d
from plyfile import PlyData

def read(p):return json.loads(Path(p).read_text())
cfg=read('/out/plot_config.json');root=Path(cfg['root']);r1=Path(cfg['r1run']);inputs=Path(cfg['inputs'])
manifest=read(root/'viewer/data/manifest.json');entry=next(r for r in manifest['regions'] if r['id']=='R1')
theta=np.deg2rad(70);basis=np.array([[np.cos(theta),np.sin(theta)],[np.sin(theta),-np.cos(theta)]])
def display(xyz):
    xyz=xyz.copy();xyz[:,:2]=xyz[:,:2]@basis.T;xyz[:,1]*=-1;return xyz
lo=np.array([-40,24,-18]);hi=np.array([-10,42,-12])
def inside(xyz):return ((xyz>=lo)&(xyz<=hi)).all(1)
result=dict(scientific_verdict=None,focus_box=dict(min=lo.tolist(),max=hi.tolist()),gaussian_centers={})
for label,folder,it in [('anchor',r1/'anchor',8000),('mvs',r1/'refinement',30000),('local_prior0',root/'R1/local_prior0',30000)]:
    path=folder/'model/jbgs_complete'/f'iteration_{it}'/'point_cloud.ply'
    v=PlyData.read(path,mmap='r')['vertex'].data
    xyz=display(np.column_stack([v[k] for k in ['x','y','z']]).astype(float));mask=inside(xyz)
    opacity=1/(1+np.exp(-np.clip(v['opacity'][mask],-30,30)))
    result['gaussian_centers'][label]=dict(in_focus=int(mask.sum()),opacity_gt_01=int((opacity>.1).sum()),opacity_gt_05=int((opacity>.5).sum()),
        meaning='Center/opacity presence only; not rendered contribution')
del v,xyz,mask,opacity
c=next(c for c in entry['candidates'] if c['id']=='local_prior0_mesh')['mesh']
def array(d):
    p=root/'viewer/data'/d['url'].removeprefix('/data/');assert hashlib.sha256(p.read_bytes()).hexdigest()==d['sha256']
    return np.fromfile(p,dtype=d['dtype']).reshape(d['shape'])
xyz=array(c['xyz']);tri=array(c['indices']);selected=inside(xyz);tri=tri[selected[tri].all(1)]
ids,inv=np.unique(tri,return_inverse=True);verts=xyz[ids];tri=inv.reshape(-1,3).astype(np.uint32)
scene=o3d.t.geometry.RaycastingScene(nthreads=2)
scene.add_triangles(o3d.core.Tensor(verts.astype(np.float32)),o3d.core.Tensor(tri))
result['focus_mesh']=dict(vertices=len(verts),triangles=len(tri),selection='All triangle vertices inside focus box')
views={Path(v['name']).stem:v for v in read(inputs/'scene/split_manifest.json')['train']}
counts={str(o):dict(hits=0,views=0,in_front_of_prior_target=0) for o in [0,.5]}
for row in read(root/'R1/masks/receipt.json')['masks']:
    if not row['pixels']:continue
    y,x=np.nonzero(np.load(root/'R1/masks'/row['path']));v=views[row['name']]
    R=np.array(v['R']);t=np.array(v['t']);K=np.array(v['K']);center=display((-t@R)[None,:])[0]
    pd=np.load(inputs/'prior/raw_depth'/row['path'],mmap_mode='r')[y,x]
    for offset in [0,.5]:
        dirs=display(np.column_stack([x+offset,y+offset,np.ones(len(x))])@np.linalg.inv(K).T@R)
        rays=np.column_stack([np.tile(center,(len(x),1)),dirs]).astype(np.float32)
        hit=scene.cast_rays(o3d.core.Tensor(rays),nthreads=2)['t_hit'].numpy();valid=np.isfinite(hit)
        record=counts[str(offset)];record['hits']+=int(valid.sum());record['views']+=int(valid.any())
        record['in_front_of_prior_target']+=int((valid&(hit<pd)).sum())
result['masked_ray_mesh_intersections']=counts
result['limitation']='Mesh intersection proves a geometric line-of-sight overlap, not actual Gaussian gradient contribution or counterfactual causation.'
Path('/out/floater_rays.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
