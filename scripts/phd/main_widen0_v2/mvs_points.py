"""Unproject training-only geometric depth using the inherited integer-pixel convention.

CPU only. Point order before random sorting is image, row, column, as UNCERT-v1.
"""
import json
from pathlib import Path
import struct
import time
import numpy as np
from preflight import images,sha,dump,DENSE
from image_inventory import depth,rotation

O=Path('/out');ROOT=O/'holdout/internal';WS=O/'mvs/full'
DT=np.dtype([('x','<f4'),('y','<f4'),('z','<f4'),('view','<i2')])

def main():
    t0=time.monotonic();receipt=json.loads((WS/'colmap_receipt.json').read_text())
    assert receipt['exit_code']==0
    replay=json.loads((O/'gates/unprojection.json').read_text())
    assert replay['status']=='PASS' and replay['point_producer_sha256']==sha(Path(__file__)), 'unprojection replay required for the current producer'
    split=json.loads((O/'image_split.json').read_text());names=split['train']
    assert not set(names)&set(split['evaluation'])
    tiles=json.loads((O/'inputs/tiles.json').read_text());cfg=json.loads(Path('/cfg/widen0_v2.json').read_text())
    rows=images(WS/'sparse/images.bin');assert sorted(rows)==sorted(names)
    with (WS/'sparse/cameras.bin').open('rb') as f:
        nc,=struct.unpack('<Q',f.read(8));assert nc==1
        cid,model,iw,ih=struct.unpack('<iiQQ',f.read(24));assert model==1
        fx,fy,cx,cy=struct.unpack('<4d',f.read(32))
    fx,fy,cx,cy=fx*1024/iw,fy*741/ih,cx*1024/iw,cy*741/ih
    # jbgs_calibration uses integer-centre coordinates: COLMAP's scaled
    # corner-coordinate principal point is reduced by half a pixel.
    cx-=.5;cy-=.5
    # Match mvs_surface.cameras: the training projection and NDC-to-pixel
    # arithmetic use float32, even though unprojection itself is float64.
    f32=np.float32
    p00,p11=f32(2*fx/1024),f32(2*fy/741)
    p02,p12=f32((2*cx+1-1024)/1024),f32((2*cy+1-741)/741)
    fx,fy=float(f32(f32(1024/2)*p00)),float(f32(f32(741/2)*p11))
    cx=float(f32(f32(f32(1024/2)*p02)+f32((1024-1)/2)))
    cy=float(f32(f32(f32(741/2)*p12)+f32((741-1)/2)))
    stamp=ROOT/'mvs_points_partition.json'
    if not stamp.exists():
        handles={};counts={t['id']:{} for t in tiles};missing=[]
        for tile in tiles:
            d=ROOT/'points'/tile['id'];d.mkdir(parents=True,exist_ok=True)
            handles[tile['id']]=(d/'mvs_a_unsorted.bin').open('wb')
        for i,name in enumerate(names):
            p=WS/'stereo/depth_maps'/f'{name}.geometric.bin'
            if not p.exists():missing.append(name);continue
            z=depth(p);assert z.shape==(741,1024)
            vv,uu=np.nonzero(np.isfinite(z)&(z>0));dd=z[vv,uu].astype(float)
            cam=np.column_stack([(uu-cx)/fx*dd,(vv-cy)/fy*dd,dd])
            v=rows[name];W=np.eye(4,dtype=np.float32);W[:3,:3]=rotation(v['q']);W[:3,3]=v['t']
            C=np.linalg.inv(W.astype(float));X=(cam@C[:3,:3].T+C[:3,3]).astype(np.float32)
            for tile in tiles:
                x0,y0,x1,y1=tile['buffer_global'];x0-=690953.;x1-=690953.;y0-=5336071.;y1-=5336071.
                m=(X[:,0]>=x0)&(X[:,0]<x1)&(X[:,1]>=y0)&(X[:,1]<y1)
                n=int(m.sum());counts[tile['id']][name]=n
                if n:
                    out=np.empty(n,DT);out['x'],out['y'],out['z']=X[m].T;out['view']=i
                    out.tofile(handles[tile['id']])
            if i%100==0:print('geometric unprojection',i,len(names),flush=True)
        for f in handles.values():f.close()
        dump(stamp,dict(per_tile_view_counts=counts,missing_depth_images=missing,view_order=names,
            integer_pixels=True,world_to_camera_float32=True,point_storage_float32=True,scientific_verdict=None))
    for idx,tile in enumerate(tiles):
        d=ROOT/'points'/tile['id']
        if (d/'mvs_a.json').exists():continue
        raw=d/'mvs_a_unsorted.bin';n=raw.stat().st_size//DT.itemsize
        if n:
            a=np.memmap(raw,mode='r',dtype=DT)
            keys=np.random.default_rng([cfg['split']['seed'],idx,0]).random(n)
            order=np.argsort(keys,kind='stable')
            out=np.lib.format.open_memmap(d/'mvs_a_xyz.npy',mode='w+',dtype=np.float32,shape=(n,3))
            vo=np.lib.format.open_memmap(d/'mvs_a_view.npy',mode='w+',dtype=np.int16,shape=(n,))
            ko=np.lib.format.open_memmap(d/'mvs_a_key.npy',mode='w+',dtype=np.float64,shape=(n,))
            for b in range(0,n,1_000_000):
                ids=order[b:b+1_000_000];out[b:b+len(ids)]=np.column_stack([a[k][ids] for k in ['x','y','z']])
                vo[b:b+len(ids)]=a['view'][ids];ko[b:b+len(ids)]=keys[ids]
            out.flush();vo.flush();ko.flush();del out,vo,ko,a,keys,order
        else:
            np.save(d/'mvs_a_xyz.npy',np.empty((0,3),np.float32));np.save(d/'mvs_a_view.npy',np.empty(0,np.int16));np.save(d/'mvs_a_key.npy',np.empty(0))
        dump(d/'mvs_a.json',dict(tile=tile['id'],points=n,seed=[cfg['split']['seed'],idx,0],
            config_sha256=sha('/cfg/widen0_v2.json'),scientific_verdict=None))
        print('MVS source prepared',tile['id'],flush=True)
    print('MVS point preparation complete',time.monotonic()-t0,flush=True)

if __name__=='__main__':main()
