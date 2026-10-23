"""Apply the inherited 9/15 candidate/split rule to the full frozen scope; read XMP."""
import datetime as dt
import json
from pathlib import Path
import re
import struct
import time
import zipfile
import numpy as np
from preflight import images, sha, dump, DENSE, PH

O,D=Path('/out'),Path('/docs')

def rotation(q):
    w,x,y,z=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],
        [2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],
        [2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]])

def depth(p):
    raw=p.read_bytes();end=0
    for _ in range(3):end=raw.find(b'&',end,100)+1
    w,h,c=map(int,raw[:end].split(b'&')[:3]);assert c==1
    return np.frombuffer(raw,dtype='<f4',offset=end,count=w*h).reshape((w,h),order='F').T

def main():
    if (O/'image_split.lock.json').exists():raise SystemExit('image split already frozen')
    t0=time.monotonic();cov=np.load(O/'inputs/coverage.npz')
    common=cov['common'];ny,nx=common.shape
    e0,n0,res=float(cov['e0']),float(cov['n0']),float(cov['res'])
    shift=np.array([690953.,5336071.,604.])
    def inside(X):
        ix=np.floor((X[:,0]+shift[0]-e0)/res).astype(np.int64)
        iy=np.floor((X[:,1]+shift[1]-n0)/res).astype(np.int64)
        m=(ix>=0)&(ix<nx)&(iy>=0)&(iy<ny)
        sel=np.flatnonzero(m);m[sel]=common[iy[sel],ix[sel]]
        return m
    fused=Path('/art/phase-payloads/p2/mvs_native_textured_mesh_preflight_v1/P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v2/work/mvs/openmvs/dim_dense.ply')
    with fused.open('rb') as f:
        header=b''
        while not header.endswith(b'end_header\n'):header+=f.readline()
    n=int(next(x.split()[-1] for x in header.decode().splitlines() if x.startswith('element vertex')))
    typ=np.dtype([('x','<f4'),('y','<f4'),('z','<f4'),('r','u1'),('g','u1'),('b','u1')])
    pts=np.memmap(fused,dtype=typ,mode='r',offset=len(header),shape=(n,))[::16]
    X=np.column_stack([pts[k] for k in ['x','y','z']])
    X=X[np.isfinite(X).all(1)&(X[:,2]>=-90)&(X[:,2]<80)]
    _,first=np.unique(np.floor(X).astype(np.int32),axis=0,return_index=True)
    X=X[np.sort(first)];X=X[inside(X)].astype(float)
    threshold=max(10,int(np.ceil(len(X)*.01)))
    with (DENSE/'sparse/cameras.bin').open('rb') as f:
        nc,=struct.unpack('<Q',f.read(8));assert nc==1
        cid,model,iw,ih=struct.unpack('<iiQQ',f.read(24));assert model==1
        fx,fy,cx,cy=struct.unpack('<4d',f.read(32))
    fx,fy,cx,cy=fx*1024/iw,fy*741/ih,cx*1024/iw,cy*741/ih
    yy,xx=np.indices((741,1024),dtype=float)
    rays=np.stack([(xx-cx)/fx,(yy-cy)/fy,np.ones_like(xx)],-1).reshape(-1,3)
    views=images(DENSE/'sparse/images.bin');rows=[]
    for i,(name,v) in enumerate(sorted(views.items())):
        R=rotation(v['q']);t=np.array(v['t']);Q=X@R.T+t
        pos=Q[:,2]>1e-6;z=np.where(pos,Q[:,2],1.)
        u=np.floor(fx*Q[:,0]/z+cx+.5);vv=np.floor(fy*Q[:,1]/z+cy+.5)
        projected=int((pos&(u>=0)&(u<1024)&(vv>=0)&(vv<741)).sum())
        p=DENSE/'stereo/depth_maps'/f'{name}.geometric.bin'
        native=None
        if p.is_file():
            dep=depth(p).ravel();valid=np.isfinite(dep)&(dep>0)
            back=(rays[valid]*dep[valid,None]-t)@R
            native=int(((back[:,2]>=-90)&(back[:,2]<80)&inside(back)).sum())
        selected=projected>=threshold or (native is not None and native>=100)
        axis=R.T@np.array([0.,0.,1.])
        tilt=float(np.degrees(np.arccos(np.clip(-axis[2],-1,1))))
        rows.append(dict(name=name,projected_reference_points=projected,native_depth_points=native,
            selected=bool(selected),tilt_deg=tilt,nadir=tilt<=20.,camera_centre_local=(-R.T@t).tolist()))
        if i%200==0:print('candidate views',i,len(views),flush=True)
    selected=[r['name'] for r in rows if r['selected']]
    ev=selected[::8];train=[n for i,n in enumerate(selected) if i%8]
    trainset=set(train);evset=set(ev)
    zpath=Path('/art/phase-payloads/p0-audit/data/raw/uav/Images.zip')
    with zipfile.ZipFile(zpath) as z:
        members={Path(n).stem:n for n in z.namelist() if n.lower().endswith('.jpg')}
        for r in rows:
            r['split']='train' if r['name'] in trainset else ('evaluation' if r['name'] in evset else 'outside_scope')
            member=members.get(Path(r['name']).stem)
            r['original_zip_member']=member
            r['xmp']={}
            if member:
                with z.open(member) as f:raw=f.read(250000)
                for key in ['UTCAtExposure','RelativeAltitude','AbsoluteAltitude','GimbalPitchDegree']:
                    m=re.search(('drone-dji:'+key+'="([^"]*)"').encode(),raw)
                    r['xmp'][key]=m.group(1).decode() if m else None
            tm=r['xmp'].get('UTCAtExposure')
            clock=tm[11:19] if tm else None
            r['flight']='nadir' if clock and '07:42:00'<=clock<'08:13:00' else ('manual' if clock and '08:37:00'<=clock<'09:37:00' else 'unknown')
    split=dict(train=train,evaluation=ev,candidates=selected,reference_points=len(X),minimum_projected=threshold,
        rule='9/15: >= max(10, ceil(1% of reference)) projected points OR >=100 native depth points; name order 0::8 evaluation',
        original_zip=str(zpath),scientific_verdict=None)
    dump(O/'image_split.json',split)
    dump(O/'inputs/image_inventory.json',dict(rows=rows,scientific_verdict=None))
    lock=dict(made=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),image_split_sha256=sha(O/'image_split.json'),
        config_sha256=sha('/cfg/widen0_v2.json'),scientific_verdict=None)
    dump(O/'image_split.lock.json',lock)
    grouped=[]
    for part in ['train','evaluation']:
        for flight in ['nadir','manual','unknown']:
            rr=[r for r in rows if r['split']==part and r['flight']==flight]
            def nums(key):
                out=[]
                for r in rr:
                    try:out.append(float(r['xmp'].get(key)))
                    except (TypeError,ValueError):pass
                return dict(n=len(out),min=min(out) if out else None,median=float(np.median(out)) if out else None,max=max(out) if out else None)
            times=[r['xmp']['UTCAtExposure'] for r in rr if r['xmp'].get('UTCAtExposure')]
            grouped.append(dict(split=part,flight=flight,images=len(rr),nadir=sum(r['nadir'] for r in rr),oblique=sum(not r['nadir'] for r in rr),
                utc_first=min(times) if times else None,utc_last=max(times) if times else None,
                relative_altitude_m=nums('RelativeAltitude'),absolute_altitude_m=nums('AbsoluteAltitude')))
    pflight=json.loads((O/'input_preflight.json').read_text())
    rate=pflight['mvs_estimate']['seconds_per_selected_image']
    estimate=dict(selected_training_images=len(train),seconds_per_image=rate,single_gpu_hours=len(train)*rate/3600,
                  two_gpu_ideal_hours=len(train)*rate/7200,over_48_hours=len(train)*rate/3600>48,
                  source='input_preflight.json: four completed runs, selected inputs denominator')
    dump(D/'tables/image_inventory.json',dict(groups=grouped,model_images=len(rows),candidates=len(selected),train=len(train),evaluation=len(ev),
        image_split_lock=lock,mvs_estimate=estimate,seconds=time.monotonic()-t0,scientific_verdict=None))
    print(json.dumps(dict(candidates=len(selected),train=len(train),evaluation=len(ev),estimate=estimate),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
