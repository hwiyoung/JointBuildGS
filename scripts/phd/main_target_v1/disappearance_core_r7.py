"""CPU development/holdout disappearance; unit is inherited building identity, no GT reads."""
import sys,warnings,json,struct
from functools import lru_cache
import numpy as np
from scipy.spatial import cKDTree
from common import *
from disappearance_r7 import nearest,areas
def test_groups(d,cameras,read_depth):
    n=len(d['region']);ids=np.flatnonzero(d['region']==0);points=d['centre'][ids].astype(float)
    valid_u=np.isfinite(d['u'])&~d['u_replaced'];donors=d['u'][valid_u]
    trees={};medians={}
    for unit in np.unique(d['unit'][ids]):
        selected=np.flatnonzero(d['unit']==unit);donor=selected[valid_u[selected]];assert len(donor),'NO_ORIGINAL_U_DONORS'
        medians[int(unit)]=float(np.median(d['u'][donor]));assert medians[int(unit)]>0
        trees[int(unit)]=(selected,cKDTree(d['centre'][selected].astype(float)))
    count=np.zeros((n,4),np.int32);ref=np.zeros_like(count)
    # Columns: through, occluded, surface, no evidence (in-frame tested views only).
    fallback=np.zeros(n,np.int64);samples=np.zeros(n,np.int64);windows=np.zeros(n,np.int32);fallback_windows=np.zeros(n,np.int32)
    reasons=np.zeros(3,np.int64);rows=[];binding={}
    for j,cam in enumerate(cameras):
        K=np.asarray(cam['K'],float);M=np.asarray(cam['W2C'],float);q=points@M[:3,:3].T+M[:3,3];z=q[:,2]
        with np.errstate(divide='ignore',invalid='ignore'):
            uf=K[0,0]*q[:,0]/z+K[0,2];vf=K[1,1]*q[:,1]/z+K[1,2]
        visible=(z>=.2)&(z<=300)&np.isfinite(uf)&np.isfinite(vf)&(uf>=0)&(vf>=0)&(uf<cam['W'])&(vf<cam['H'])
        local=np.flatnonzero(visible);dest=ids[local]
        if not len(dest):continue
        dep,conf,paths=read_depth(cam['name']);binding.update({str(p):sha(p) for p in paths})
        assert dep.shape==(cam['H'],cam['W']) and conf.shape==dep.shape
        uv=np.rint(np.c_[uf[local],vf[local]]).astype(int)
        offs=np.array([(u,v) for v in [-1,0,1] for u in [-1,0,1]])
        pixels=uv[:,None,:]+offs;px,py=pixels[:,:,0],pixels[:,:,1]
        inside=(px>=0)&(py>=0)&(px<cam['W'])&(py<cam['H']);xx=np.clip(px,0,cam['W']-1);yy=np.clip(py,0,cam['H']-1)
        depth=dep[yy,xx].astype(float);valid=inside&np.isfinite(depth)&(depth>0)&(conf[yy,xx]>0)
        vu,vv=px[valid],py[valid];dd=depth[valid]
        xyz=np.c_[(vu-K[0,2])/K[0,0]*dd,(vv-K[1,2])/K[1,1]*dd,dd]
        inv=np.linalg.inv(M);world=xyz@inv[:3,:3].T+inv[:3,3]
        units=np.broadcast_to(d['unit'][dest,None],valid.shape)[valid];distance=np.full(len(world),np.inf);owner=np.zeros(len(world),np.int64);fill=np.zeros(len(world))
        for unit in np.unique(units):
            selected,tree=trees[int(unit)];loc=np.flatnonzero(units==unit)
            # Duplicate window samples query the identical MVS pixel once per unit/view.
            keys=vv[loc]*cam['W']+vu[loc];unique,first,inverse=np.unique(keys,return_index=True,return_inverse=True)
            dist,ix=nearest(tree,d['centre'][selected],world[loc[first]])
            distance[loc]=dist[inverse];owner[loc]=selected[ix[inverse]];fill[loc]=medians[int(unit)]
        missing=distance>1;replaced=(~missing)&d['u_replaced'][owner];bad=(~missing)&~replaced&~np.isfinite(d['u'][owner]);use=missing|replaced|bad
        u=np.where(use,fill,d['u'][owner]);sigma=np.full(depth.shape,np.nan);sigma[valid]=np.hypot(u,.0275)
        depth[~valid]=np.nan
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',RuntimeWarning);dm=np.nanmedian(depth,axis=1);sm=np.nanmedian(sigma,axis=1)
        margin=1.96*np.hypot(sm,d['sigma_p'][dest]);reference=1.96*np.sqrt(d['u'][dest]**2+.0275**2+d['sigma_p'][dest]**2)
        good=np.isfinite(dm)&np.isfinite(margin);delta=dm-z[local]
        for counts,m in [(count,margin),(ref,reference)]:
            cls=np.full(len(dest),3,np.int8);cls[good]=2;cls[good&(delta>m)]=0;cls[good&(delta < -m)]=1
            counts[dest,cls]+=1
        rep=np.zeros_like(valid);rep[valid]=use;fallback[dest]+=rep.sum(1);samples[dest]+=valid.sum(1)
        windows[dest]+=good;fallback_windows[dest]+=good&rep.any(1);reasons+=np.array([missing.sum(),replaced.sum(),bad.sum()])
        rows.append(dict(camera=cam['name'],tested=len(dest),evidence=int(good.sum()),valid_samples=int(valid.sum()),fallback_samples=int(use.sum())))
        if j%40==0:print('DISAPPEAR',j+1,len(cameras),len(ids),flush=True)
    disappears=(count[:,0]>=2)&(count[:,0]*2>count[:,:3].sum(1))&(d['region']==0)
    reference=(ref[:,0]>=2)&(ref[:,0]*2>ref[:,:3].sum(1))&(d['region']==0)
    data=dict(votes=count,reference_votes=ref,disappeared=disappears,reference_disappeared=reference,fallback_samples=fallback,valid_samples=samples,evidence_windows=windows,fallback_windows=fallback_windows)
    return data,dict(u_median_by_unit=medians,original_u_donors=len(donors),valid_samples=int(samples.sum()),fallback_samples=int(fallback.sum()),fallback_fraction=float(fallback.sum()/samples.sum()) if samples.sum() else None,
        fallback_reason_counts=dict(zip(['no_neighbour','replaced_neighbour','missing_u'],reasons.tolist())),views=rows,files=binding,GT_loaded_before_decision=False)

def cameras_full():
    sys.path.insert(0,'/source')
    from scene.colmap_loader import read_extrinsics_binary,read_intrinsics_binary,qvec2rotmat
    w=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2';f=w/'mvs/full';poses=read_extrinsics_binary(str(f/'sparse/images.bin'));intr=read_intrinsics_binary(str(f/'sparse/cameras.bin'))
    train=set(json.loads((w/'image_split.json').read_text())['train']);cams=[]
    for pose in sorted(poses.values(),key=lambda e:e.name):
        if pose.name not in train:continue
        ci=intr[pose.camera_id];assert ci.model=='PINHOLE';fx,fy,cx,cy=ci.params*np.array([1024/ci.width,741/ci.height,1024/ci.width,741/ci.height]);cx-=.5;cy-=.5
        f32=np.float32;fx=f32(f32(512)*f32(2*fx/1024));fy=f32(f32(741/2)*f32(2*fy/741));cx=f32(f32(f32(512)*f32((2*cx+1-1024)/1024))+f32(1023/2));cy=f32(f32(f32(741/2)*f32((2*cy+1-741)/741))+f32(740/2))
        M=np.eye(4,dtype='f4');M[:3,:3]=qvec2rotmat(pose.qvec);M[:3,3]=pose.tvec
        cams.append(dict(name=pose.name,W=1024,H=741,K=[[float(fx),0,float(cx)],[0,float(fy),float(cy)],[0,0,1]],W2C=M))
    assert {c['name'] for c in cams}==train
    return cams,f

def read_bin(p):
    raw=p.read_bytes();end=0
    for _ in range(3):end=raw.find(b'&',end,100)+1
    w,h,c=map(int,raw[:end].split(b'&')[:3]);assert c==1
    return np.frombuffer(raw,dtype='<f4',offset=end,count=w*h).reshape((w,h),order='F').T

def main():
    split,prior=sys.argv[1:3];assert split in ['development','holdout'];sealed=split=='holdout'
    assert sha(CFG/'target_v1.r7.stage0.json')==json.loads((CFG/'target_v1.r7.stage0.lock.json').read_text())['config_sha256']
    source=OUT/('holdout/r2/stage0' if sealed else 'r2/stage0/development');jn=JN/'holdout' if sealed else JN
    output=OUT/('holdout/r7/stage0' if sealed else 'r7/stage0/development');output.mkdir(parents=True,exist_ok=True)
    files=sorted(source.glob(f'*__{prior}.npz'));parts=[];offsets=[];n=0;binding={}
    keys=['region','u','u_replaced','sigma_p','area','kind','any_replaced','building']
    for p in files:
        with np.load(p) as z:d={k:z[k] for k in keys};patch=z['patch_id']
        geom=jn/'core_points'/p.name
        with np.load(geom) as z:assert np.array_equal(patch,z['patch_id']);d['centre']=z['centre']
        d['in_eval']=np.ones(len(patch),bool);parts.append(d);offsets.append((p.name,n,n+len(patch)));n+=len(patch)
        binding[str(p)]=sha(p);binding[str(geom)]=sha(geom)
    d={k:np.concatenate([x[k] for x in parts]) for k in parts[0]};del parts
    units,d['unit']=np.unique(d.pop('building'),return_inverse=True)
    cams,base=cameras_full()
    def read(name):
        path=base/'stereo/depth_maps'/f'{name}.geometric.bin'
        if not path.exists():return np.full((741,1024),np.nan,'f4'),np.zeros((741,1024),'u1'),[]
        depth=read_bin(path);return depth,(np.isfinite(depth)&(depth>0)).astype('u1'),[path]
    a,record=test_groups(d,cams,read)
    for name,start,end in offsets:
        dest=output/name;assert not dest.exists();np.savez_compressed(dest,**{k:v[start:end] for k,v in a.items()})
    record.update(at=stamp(),split=split,prior=prior,input_files=binding,units=units.tolist(),config_sha256=sha(CFG/'target_v1.r7.stage0.json'),scientific_verdict=None)
    dump(output/f'{prior}.complete.json',record)
    rr=areas(d,a,'aggregate',prior,split);dump(DOC/'tables'/f'disappearance_{split}_{prior}_r7.json',dict(rows=rr,public_fields='aggregate counts areas ratios only',scientific_verdict=None))
    print('CORE_DISAPPEAR_COMPLETE',split,prior,len(d['region']),int(a['disappeared'].sum()),flush=True)
if __name__=='__main__':main()
