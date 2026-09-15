"""Locate saved rendered depths that support the observed Z06 floater."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def read(p):
    return json.loads(Path(p).read_text())


cfg=read('/config.json');root=Path(cfg['root']);legacy=Path(cfg['r1run']);inputs=Path(cfg['inputs']);out=Path('/out')
manifest=read(root/'viewer/data/manifest.json');region=next(r for r in manifest['regions'] if r['id']=='R1')
meta=next(c for c in region['candidates'] if c['id']=='local_prior0_mesh')['mesh']['xyz']
p=root/'viewer/data'/meta['url'].removeprefix('/data/');data=p.read_bytes();assert hashlib.sha256(data).hexdigest()==meta['sha256']
xyz=np.frombuffer(data,dtype=meta['dtype']).reshape(meta['shape'])
lo,hi=np.array(cfg['box']);xyz=xyz[((xyz>=lo)&(xyz<=hi)).all(1)]
xyz=xyz[np.linspace(0,len(xyz)-1,min(len(xyz),600)).astype(int)].astype(float)
theta=np.deg2rad(70);basis=np.array([[np.cos(theta),np.sin(theta)],[np.sin(theta),-np.cos(theta)]])
xyz[:,1]*=-1;xyz[:,:2]=xyz[:,:2]@basis
binding=read(legacy/'mesh_recovery.json')
extracts={'mvs':legacy/binding['relative']/'extract_final','local_prior0':root/'R1/extract_local_prior0','da3':root/'R1/extract_da3'}
split=read(inputs/'scene/split_manifest.json');views=sorted(split['train'],key=lambda v:v['name'])
rows=[]
for index,v in enumerate(views):
    R=np.array(v['R']);t=np.array(v['t']);K=np.array(v['K']);w,h=v['width'],v['height'];cam=xyz@R.T+t
    with np.errstate(divide='ignore',invalid='ignore'):
        x=np.rint(K[0,0]*cam[:,0]/cam[:,2]+K[0,2]).astype(int)
        y=np.rint(K[1,1]*cam[:,1]/cam[:,2]+K[1,2]).astype(int)
    valid=(cam[:,2]>.2)&(x>=0)&(x<w)&(y>=0)&(y<h)
    if not valid.any():continue
    x,y,z=x[valid],y[valid],cam[valid,2]
    coords,ix=np.unique(np.column_stack([y,x]),axis=0,return_index=True);x,y,z=x[ix],y[ix],z[ix]
    depths={k:np.asarray(Image.open(d/'model/train/ours_30000/vis'/f'depth_{index:05d}.tiff'))[y,x] for k,d in extracts.items()}
    support=np.abs(depths['local_prior0']-z)<cfg['support_tolerance_m']
    changed=support&(np.abs(depths['mvs']-depths['local_prior0'])>cfg['minimum_control_difference_m'])
    if not changed.any():continue
    name=Path(v['name']).stem;mask=np.load(root/'R1/masks'/f'{name}.npy',mmap_mode='r')
    selected=np.flatnonzero(changed);j=selected[np.argmax(np.abs(depths['mvs'][selected]-depths['local_prior0'][selected]))]
    row=dict(index=index,name=name,in_frame=len(x),support=int(support.sum()),changed_support=int(changed.sum()),
             changed_masked=int(mask[y[changed],x[changed]].sum()),pixel=[int(x[j]),int(y[j])],
             floater_camera_z=float(z[j]),depth={k:float(d[j]) for k,d in depths.items()},
             pixel_prior_disabled=bool(mask[y[j],x[j]]),camera=v)
    rows.append(row)
rows.sort(key=lambda r:(r['changed_support'],abs(r['depth']['mvs']-r['depth']['local_prior0'])),reverse=True)
assert rows,'No saved real-camera depth support found; inspect extraction virtual views next'
result=dict(status='PASS_SAVED_DEPTH_SUPPORT_TRACE',scientific_verdict=None,config=cfg,mesh_xyz_sha256=meta['sha256'],
            sampled_vertices=len(xyz),views=rows,selected=rows[:cfg['selected_views']],
            meaning='Saved render support for existing TSDF floater; CPU splat attribution follows; no training changes')
(out/'depth_support.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:result[k] for k in ['status','sampled_vertices']}));print([(r['name'],r['changed_support'],r['depth'],r['pixel']) for r in result['selected']])
