"""Separate raw rendered sky, extracted geometry, and viewer height cropping."""
import json
from pathlib import Path
import hashlib
import numpy as np
from PIL import Image

def read(p):return json.loads(Path(p).read_text())
cfg=read('/config.json');root=Path(cfg['root']);legacy=Path(cfg['legacy']);out=Path('/out')
binding=read(legacy/'mesh_recovery.json')
folders={'mvs':legacy/binding['relative']/'extract_final',
         'da3':root/'R1/extract_da3','local_prior0':root/'R1/extract_local_prior0'}
def vertices(p):
    types={'float':'<f4','float32':'<f4','double':'<f8','uchar':'u1','uint8':'u1','int':'<i4','uint':'<u4'}
    with p.open('rb') as f:
        fields=[];active=False;count=None
        while True:
            line=f.readline().decode('ascii').strip();words=line.split()
            if line=='end_header':break
            if words[:1]==['format']:assert words[1]=='binary_little_endian'
            if words[:1]==['element']:
                active=words[1]=='vertex'
                if active:count=int(words[2])
            if active and words[:1]==['property']:
                assert words[1]!='list';fields.append((words[2],types[words[1]]))
        offset=f.tell()
    return np.memmap(p,dtype=np.dtype(fields),mode='r',offset=offset,shape=(count,))
theta=np.deg2rad(70);u=np.array([np.cos(theta),np.sin(theta)]);v=np.array([u[1],-u[0]])
current_max=-1.8353849649429321
result=dict(scientific_verdict=None,depth={},raw_mesh={},
    legacy_crop_z=[-90,80],new_branch_v4_crop_z=[-81.28596496582031,current_max],
    sky_camera='DJI_20241217101349_0027_D.JPG',sky_rectangle=[100,50,1250,400],depth_trunc_m=116.63611589285539)
reference=None
for name,folder in folders.items():
    gt=np.asarray(Image.open(folder/'model/train/ours_30000/gt/00370.png'))
    if reference is None:reference=gt
    else:assert np.array_equal(reference,gt)
    dpath=folder/'model/train/ours_30000/vis/depth_00370.tiff';d=np.asarray(Image.open(dpath))[50:400,100:1250]
    valid=np.isfinite(d)&(d>0)
    result['depth'][name]=dict(valid=int(valid.sum()),pixels=int(d.size),median=float(np.median(d[valid])),
        within_tsdf=int((valid&(d<=result['depth_trunc_m'])).sum()),
        sha256=hashlib.sha256(dpath.read_bytes()).hexdigest())
    meshrec=read(folder/'receipt.json')['surfaces']['fuse.ply'];path=folder/meshrec['path'];verts=vertices(path)
    row=dict(total_vertices=len(verts),in_R1_xy=0,above_v4_max_in_xy=0,above_v4_max_within_legacy_z=0,
             z_min=1e30,z_max=-1e30,source_sha256=meshrec['sha256'])
    for start in range(0,len(verts),500000):
        vv=verts[start:start+500000];xy=np.column_stack([vv['x'],vv['y']]);uu=xy@u;minus_v=-xy@v;zz=vv['z']
        inside=(uu>=-135)&(uu<=70)&(minus_v>=-35)&(minus_v<=65)
        row['in_R1_xy']+=int(inside.sum());row['above_v4_max_in_xy']+=int((inside&(zz>current_max)).sum())
        row['above_v4_max_within_legacy_z']+=int((inside&(zz>current_max)&(zz<=80)).sum())
        if inside.any():row['z_min']=min(row['z_min'],float(zz[inside].min()));row['z_max']=max(row['z_max'],float(zz[inside].max()))
    result['raw_mesh'][name]=row
result['status']='PASS_DISPLAY_CROP_MISMATCH_CONFIRMED'
(out/'receipt.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
