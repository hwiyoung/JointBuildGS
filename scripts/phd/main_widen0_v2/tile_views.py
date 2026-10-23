"""Projection part of the inherited candidate rule, independent of new MVS results."""
import json
from pathlib import Path
import numpy as np
from preflight import DENSE,dump,images
from image_inventory import rotation
from common import read_cameras_bin
O=Path('/out')

def main():
    fused=Path('/art/phase-payloads/p2/mvs_native_textured_mesh_preflight_v1/P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v2/work/mvs/openmvs/dim_dense.ply')
    with fused.open('rb') as f:
        header=b''
        while not header.endswith(b'end_header\n'):header+=f.readline()
    n=int(next(s.split()[-1] for s in header.decode().splitlines() if s.startswith('element vertex')))
    typ=np.dtype([('x','<f4'),('y','<f4'),('z','<f4'),('r','u1'),('g','u1'),('b','u1')])
    a=np.memmap(fused,dtype=typ,mode='r',offset=len(header),shape=(n,))[::16]
    X=np.column_stack([a[k] for k in ['x','y','z']]);X=X[np.isfinite(X).all(1)&(X[:,2]>=-90)&(X[:,2]<80)]
    _,idx=np.unique(np.floor(X).astype(np.int32),axis=0,return_index=True);X=X[np.sort(idx)].astype(float)
    tiles=json.loads((O/'inputs/tiles.json').read_text());refs={}
    for tile in tiles:
        x0,y0,x1,y1=tile['buffer_global'];x0-=690953.;x1-=690953.;y0-=5336071.;y1-=5336071.
        refs[tile['id']]=X[(X[:,0]>=x0)&(X[:,0]<x1)&(X[:,1]>=y0)&(X[:,1]<y1)]
    names=json.loads((O/'image_split.json').read_text())['train'];ims=images(DENSE/'sparse/images.bin')
    cam=next(iter(read_cameras_bin(DENSE/'sparse/cameras.bin').values()));fx,fy,cx,cy=cam['p']
    fx*=1024/cam['w'];cx*=1024/cam['w'];fy*=741/cam['h'];cy*=741/cam['h']
    rec={tid:dict(reference_points=len(P),minimum=max(10,int(np.ceil(.01*len(P)))),projected_candidates=[]) for tid,P in refs.items()}
    for name in names:
        R=rotation(ims[name]['q']);t=np.array(ims[name]['t'])
        for tid,P in refs.items():
            Q=P@R.T+t;pos=Q[:,2]>1e-6;z=np.where(pos,Q[:,2],1.)
            u=np.floor(fx*Q[:,0]/z+cx+.5);v=np.floor(fy*Q[:,1]/z+cy+.5)
            cnt=int((pos&(u>=0)&(u<1024)&(v>=0)&(v<741)).sum())
            if cnt>=rec[tid]['minimum']:rec[tid]['projected_candidates'].append(name)
    dump(O/'inputs/projected_tile_views.json',dict(tiles=rec,scientific_verdict=None,rule='Inherited 9/15 projected sparse-reference branch. Final candidate list also includes >=100 new native geometric points in the tile context. All are in the global training split.'))
    print('tile projection lists written',len(tiles))

if __name__=='__main__':main()
