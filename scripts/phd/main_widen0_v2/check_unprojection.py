"""Replay original depth samples against stored UNCERT MVS coordinates."""
import json
from pathlib import Path
import struct
import numpy as np
from scipy.spatial import cKDTree
from preflight import PH,DENSE,images,dump,sha
from image_inventory import rotation

def main():
    rows=images(DENSE/'sparse/images.bin')
    with (DENSE/'sparse/cameras.bin').open('rb') as f:
        nc,=struct.unpack('<Q',f.read(8));assert nc==1
        cid,model,iw,ih=struct.unpack('<iiQQ',f.read(24));assert model==1
        fx,fy,cx,cy=struct.unpack('<4d',f.read(32))
    K=np.array([[fx*1024/iw,0,cx*1024/iw-.5],[0,fy*741/ih,cy*741/ih-.5],[0,0,1.]])
    f32=np.float32;p00,p11=f32(2*K[0,0]/1024),f32(2*K[1,1]/741)
    p02,p12=f32((2*K[0,2]+1-1024)/1024),f32((2*K[1,2]+1-741)/741)
    fx,fy=float(f32(f32(1024/2)*p00)),float(f32(f32(741/2)*p11))
    cx=float(f32(f32(f32(1024/2)*p02)+f32((1024-1)/2)));cy=float(f32(f32(f32(741/2)*p12)+f32((741-1)/2)))
    output=[]
    for site in ['B0_b10','B173nb_b10','R1rep_b10']:
        S0=PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1';P=PH/'main_uncert_v1/PHD-MAIN-UNCERT-v1/points'/site
        meta=json.loads((P/'mvs_a.json').read_text());cal=json.loads((S0/'fork_inputs/s61'/site/'scene_LoD2/jbgs_calibration.json').read_text())
        vv=np.load(P/'mvs_a_view.npy',mmap_mode='r');xyz=np.load(P/'mvs_a_xyz.npy',mmap_mode='r')
        for vi in [0,len(meta['camera_names'])//2,len(meta['camera_names'])-1]:
            stem=meta['camera_names'][vi];j=np.flatnonzero(vv==vi)[:1000]
            if not len(j):continue
            delta=float(np.max(np.abs(np.array(cal['images'][stem]['K'])-K)))
            if delta>=1e-10:print('intrinsic difference',site,stem,'task',K.tolist(),'historical',cal['images'][stem]['K'],flush=True)
            assert delta<1e-10,delta
            dep=np.load(S0/'s61/export'/site/'LoD2/mvs'/f'{stem}.npy');valid=dep>0
            v,u=np.nonzero(valid);dd=dep[v,u].astype(float);cam=np.column_stack([(u-cx)/fx*dd,(v-cy)/fy*dd,dd])
            name=stem+'.JPG';row=rows[name];W=np.eye(4,dtype=np.float32);W[:3,:3]=rotation(row['q']);W[:3,3]=row['t']
            C=np.linalg.inv(W.astype(float));new=(cam@C[:3,:3].T+C[:3,3]).astype(np.float32)
            dist=cKDTree(new).query(xyz[j],workers=8)[0]
            output.append(dict(site=site,image=stem,samples=len(j),intrinsics_max_difference=delta,coordinate_max_difference_m=float(dist.max()),exact_equal=int((dist==0).sum())))
            assert np.all(dist<=1e-5),(site,stem,float(dist.max()))
    result=dict(status='PASS',rows=output,integer_pixel_centres=True,point_producer_sha256=sha(Path(__file__).with_name('mvs_points.py')),scientific_verdict=None)
    dump(Path('/docs/tables/unprojection_replay.json'),result);dump(Path('/out/gates/unprojection.json'),result)
    print('unprojection replay PASS',len(output),'images')
if __name__=='__main__':main()
