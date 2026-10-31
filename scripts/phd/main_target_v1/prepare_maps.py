"""Exact target-disc camera depth; unchanged confidence-masked MVS in uncovered pixels."""
import sys,ctypes,subprocess,time
import numpy as np
from common import *
sys.path.insert(0,str(REPO/'scripts/phd/main_axes71_v2'))
import mvs_surface as MS


def rasterizer():
    src=Path(__file__).with_name('target_discs.cpp');lib=OUT/'tmp/target_discs.so'
    subprocess.run(['g++','-std=c++17','-O3','-shared','-fPIC',str(src),'-o',str(lib)],check=True)
    fn=ctypes.CDLL(str(lib)).target_discs
    A=np.ctypeslib.ndpointer(dtype=np.float64,flags='C_CONTIGUOUS')
    F=np.ctypeslib.ndpointer(dtype=np.float32,flags='C_CONTIGUOUS');I=np.ctypeslib.ndpointer(dtype=np.int32,flags='C_CONTIGUOUS')
    fn.argtypes=[ctypes.c_int,A,A,A,A,ctypes.c_int,ctypes.c_int,F,I];fn.restype=None
    return fn


def draw(fn,points,cam):
    H,W=int(cam['H']),int(cam['W']);M=np.asarray(cam['W2C'],np.float64)
    K=np.array([[cam['fx'],0,cam['cx']],[0,cam['fy'],cam['cy']],[0,0,1]],np.float64)
    depth=np.empty((H,W),np.float32);owner=np.empty((H,W),np.int32)
    fn(len(points),np.ascontiguousarray(points),np.ascontiguousarray(M[:3,:3]),np.ascontiguousarray(M[:3,3]),K,H,W,depth,owner)
    depth[owner<0]=np.nan
    return depth,owner,K,M


def main():
    cfg,lock=training_locked();fn=rasterizer();sites=sys.argv[1:] or cfg['sites']+cfg['deferred_sites']
    for site in sites:
        cams,camrec=MS.cameras(site)
        for prior in cfg['priors']:
            root=OUT/'stage1'/f'{site}_{prior}'/'maps';root.mkdir(parents=True,exist_ok=True)
            if (root/'index.json').exists():continue
            with np.load(OUT/'targets'/f'{site}_{prior}.npz') as z:d={k:z[k] for k in z.files}
            with np.load(OUT/'stage0_r1/inputs'/f'{site}_{prior}.npz') as z:
                raw=z['mvs_a_u'];donors=raw[(z['kind']==1)&np.isfinite(raw)]
            assert len(donors) and np.median(donors)>0
            bg_u=float(np.median(donors));bg_sigma=float(np.hypot(bg_u,.0275))
            valid=d['region']>=0;ids=np.flatnonzero(valid)
            points=np.c_[d['target'][ids],d['normal'][ids],np.sqrt(d['area'][ids]/np.pi),ids].astype(np.float64)
            index={'site':site,'prior':prior,'at':stamp(),'views':{},'camera_source':camrec,'background_u_median':bg_u,
                'background_sigma_replaced':True,'target_sha256':sha(OUT/'targets'/f'{site}_{prior}.npz'),
                'config_sha256':lock['config_sha256'],'scientific_verdict':None}
            for j,cam in enumerate(cams):
                name=cam['name'];depth,owner,K,M=draw(fn,points,cam);has=owner>=0
                sigma=np.full(depth.shape,np.nan,np.float32);sigma[has]=d['sigma'][owner[has]]
                old=S0/'fork_inputs/s61'/site/'maps';mvs=np.load(old/'mvs'/f'{name}.npy');conf=np.load(old/'conf'/f'{name}.npy')
                assert mvs.shape==depth.shape and conf.shape==depth.shape
                bg=(~has)&np.isfinite(mvs)&(mvs>0)&(conf>0)
                depth[bg]=mvs[bg];sigma[bg]=bg_sigma;good=np.isfinite(depth)&np.isfinite(sigma)&(sigma>0)
                ref=float(np.median(sigma[good])) if good.any() else None;weight=np.zeros(depth.shape,np.float32)
                if ref is not None:weight[good]=np.clip((ref/sigma[good])**2,.1,10)
                # Independent normal-height reconstruction on a fixed pixel stride.
                vv,uu=np.nonzero(has);take=np.arange(0,len(vv),max(1,len(vv)//2000));v,u=vv[take],uu[take];pid=owner[v,u]
                camxyz=np.c_[(u-K[0,2])/K[0,0],(v-K[1,2])/K[1,1],np.ones(len(v))]*depth[v,u,None]
                world=(camxyz-M[:3,3])@M[:3,:3]
                h=((world-d['centre'][pid])*d['normal'][pid]).sum(1)
                error=np.abs(h-d['h'][pid]);median=float(np.median(error)) if len(error) else None
                if median is not None:assert median<=.01,('TARGET_MAP_HEIGHT_GATE',site,prior,name,median)
                dest=root/f'{name}.npz';np.savez_compressed(dest,depth=depth,sigma=sigma,weight=weight,owner=owner)
                index['views'][name]=dict(file=dest.name,sha256=sha(dest),prior_pixels=int(has.sum()),background_pixels=int(bg.sum()),
                    total_target_pixels=int(good.sum()),sigma_ref=ref,height_reconstruction_samples=len(error),height_error_median_m=median,
                    height_error_max_m=float(error.max()) if len(error) else None,K=K.tolist(),W2C=M.tolist())
                if (j+1)%40==0:print('TARGET_MAPS',site,prior,j+1,'/',len(cams),flush=True)
            dump(root/'index.json',index);print('TARGET_MAPS_COMPLETE',site,prior,len(cams),flush=True)

if __name__=='__main__':main()
