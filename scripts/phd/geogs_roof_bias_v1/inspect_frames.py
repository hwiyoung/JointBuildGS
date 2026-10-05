import sys,json
from pathlib import Path
import numpy as np
from plyfile import PlyData
sys.path.insert(0,'/source')
from scene.colmap_loader import read_extrinsics_binary
A=Path('/artifacts/JointBuildGS')
old=A/'phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1'
e=read_extrinsics_binary(str(old/'native_example/scene/sparse/0/images.bin'))
c=read_extrinsics_binary(str(A/'phase-payloads/p0-audit/data/work/mvs/colmap_dense/sparse/images.bin'))
cent=lambda im: -im.qvec2rotmat().T @ im.tvec
byname={x.name:x for x in c.values()}
a=[];b=[]
for im in e.values():
 if im.name in byname:a.append(cent(im));b.append(cent(byname[im.name]))
a=np.array(a);b=np.array(b)
print('matched cameras',len(a));print('example centers',a.min(0),a.max(0));print('common centers',b.min(0),b.max(0))
print('center deltas mean/std',np.mean(a-b,0),np.std(a-b,0))
for p in [old/'native_example/scene/lod2_pcd.ply',old/'native_example/scene/sparse_lod/0/points3D.ply']:
 v=PlyData.read(str(p))['vertex'];x=np.column_stack([v[k] for k in ('x','y','z')]);print(str(p),len(x),x.min(0),x.max(0),np.median(x,0))
