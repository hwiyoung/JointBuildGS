"""Confidence-masked own-unit MVS background, excluded by exact prior cylinders."""
import sys, subprocess
import numpy as np
from PIL import Image
from common import *
sys.path.insert(0,str(REPO/'scripts/phd/main_axes71_v2'))
import mvs_surface as MS


def main():
    cfg,lock=locked_r2();site=sys.argv[1]
    root=OUT/'r2/background'/site;root.mkdir(parents=True,exist_ok=True)
    binding=CFG/'background_r2.lock.json'
    if not binding.exists():
        dump(binding,dict(at=stamp(),config_sha256=lock['config_sha256'],
            thinning='first original UNCERT random-key point per floor(local XYZ/0.25) voxel after exact cylinder exclusion',
            normal='cross product of central finite differences of confidence-masked depth in source training view, outward toward camera, else vertical up',
            uncertainty='unchanged own-unit UNCERT ring1.5m; missing uses same-kind median of valid background point-patches and same-prior raw patches in the same unit; no zero',
            rgb='source training image at the reprojected MVS pixel; calibrated image dimensions',
            code_sha256=sha(__file__),exclusion_sha256=sha(Path(__file__).with_name('exclude_cylinders_r2.cpp')),scientific_verdict=None))
    b=json.loads(binding.read_text());assert b['code_sha256']==sha(__file__)
    binary=root/'exclude_cylinders'
    subprocess.run(['g++','-O3','-std=c++17',str(Path(__file__).with_name('exclude_cylinders_r2.cpp')),'-o',str(binary)],check=True)
    source=(OUT/'b173_uncert_r1' if site=='B173_b0' else UN)/'points'/site
    xyzfile=source/'mvs_a_xyz.npy';x=np.load(xyzfile,mmap_mode='r');view=np.load(source/'mvs_a_view.npy',mmap_mode='r')
    cams,_=MS.cameras(site)
    with xyzfile.open('rb') as f:
        v=np.lib.format.read_magic(f);np.lib.format._read_array_header(f,v);offset=f.tell()
    for prior in cfg['priors']:
        pr=root/prior;pr.mkdir(exist_ok=True);dest=pr/'background.npz'
        if dest.exists():continue
        with np.load(OUT/'stage0_r1/inputs'/f'{site}_{prior}.npz') as z:d={k:z[k] for k in z.files}
        radius=np.array([cfg['inherited_radius'][prior][str(int(k))]['radius_m'] or np.nan for k in d['kind']])
        cores=pr/'cylinders.bin';np.c_[d['centre'],d['normal'],np.where(d['kind']==1,10.,5.),radius].astype('<f8').tofile(cores)
        maskfile=pr/'excluded.bin'
        subprocess.run([str(binary),str(xyzfile),str(offset),str(len(x)),str(cores),str(len(radius)),str(maskfile)],check=True)
        excluded=np.fromfile(maskfile,dtype=np.uint8).astype(bool);ix=np.flatnonzero(~excluded)
        voxel=np.floor(x[ix].astype(float)/.25).astype(np.int32)
        _,first=np.unique(voxel,axis=0,return_index=True);ix=ix[np.sort(first)];del voxel,first
        pos=np.array(x[ix]);vi=np.array(view[ix]);norm=np.zeros_like(pos);norm[:,2]=1;norm_missing=np.ones(len(ix),bool)
        rgb=np.zeros_like(pos)
        for i in np.unique(vi):
            cam=cams[i];sel=np.flatnonzero(vi==i);M=np.array(cam['W2C'],float)
            q=pos[sel].astype(float)@M[:3,:3].T+M[:3,3]
            uu=np.rint(cam['fx']*q[:,0]/q[:,2]+cam['cx']).astype(int);vv=np.rint(cam['fy']*q[:,1]/q[:,2]+cam['cy']).astype(int)
            depth=np.load(S0/'fork_inputs/s61'/site/'maps/mvs'/f"{cam['name']}.npy")
            conf=np.load(S0/'fork_inputs/s61'/site/'maps/conf'/f"{cam['name']}.npy")
            assert ((uu>=0)&(uu<cam['W'])&(vv>=0)&(vv<cam['H'])).all()
            assert (conf[vv,uu]>0).all() and (depth[vv,uu]>0).all()
            assert np.max(np.abs(depth[vv,uu]-q[:,2]))<.001
            paths=list((S0/'fork_inputs/s61'/site/'scene_LoD2/images').glob(cam['name']+'.*'));assert len(paths)==1
            im=np.asarray(Image.open(paths[0]).convert('RGB').resize((cam['W'],cam['H']),Image.Resampling.BILINEAR))
            rgb[sel]=im[vv,uu]/255.
            inside=(uu>0)&(uu<cam['W']-1)&(vv>0)&(vv<cam['H']-1);ss=sel[inside];u=uu[inside];v=vv[inside]
            def back(u,v):
                dep=depth[v,u].astype(float)
                return np.c_[(u-cam['cx'])/cam['fx']*dep,(v-cam['cy'])/cam['fy']*dep,dep]
            a=back(u+1,v)-back(u-1,v);b=back(u,v+1)-back(u,v-1);n=np.cross(a,b);ln=np.linalg.norm(n,axis=1)
            good=np.isfinite(n).all(1)&(ln>1e-10)
            for du,dv in [(1,0),(-1,0),(0,1),(0,-1)]:good&=(conf[v+dv,u+du]>0)&np.isfinite(depth[v+dv,u+du])&(depth[v+dv,u+du]>0)
            n[good]/=ln[good,None];n[(n*q[inside]).sum(1)>0]*=-1
            norm[ss[good]]=n[good]@M[:3,:3];norm_missing[ss[good]]=False
        # Geometric ring uncertainty; no reference geometry is loaded.
        sys.path.insert(0,str(REPO/'scripts/phd/main_uncert_v1'))
        import uc_common as U
        U.SITE_ID['B173_b0']=3;U.PTS=source.parent;U.WORK=pr/'uncert';U.WORK.mkdir(exist_ok=True)
        roof=np.abs(norm[:,2])>=np.cos(np.radians(45));kind=np.where(roof,1,2)
        np.savez_compressed(U.WORK/f'patches_{site}_{prior}.npz',centre=pos.astype(float),normal=norm.astype(float),roof_like=roof)
        import u2_run as run
        run.run(site,prior,'mvs_a',[1.5],4)
        with np.load(U.WORK/f'val_{site}_{prior}_mvs_a_R1.5.npz') as z:
            u=z['u'].copy();u[z['status']!=0]=np.nan
        replaced=~np.isfinite(u);med=[]
        for k in [1,2]:
            donor=np.r_[u[(kind==k)&np.isfinite(u)],d['mvs_a_u'][(d['kind']==k)&np.isfinite(d['mvs_a_u'])]]
            missing=(kind==k)&replaced
            if missing.any():
                assert len(donor) and np.median(donor)>0,('BACKGROUND_U_UNAVAILABLE',site,prior,k)
                median=float(np.median(donor));u[missing]=median;med.append(dict(kind=k,median=median,replaced=int(missing.sum()),donors=len(donor)))
        np.savez_compressed(dest,xyz=pos,normal=norm,rgb=rgb,sigma=np.hypot(u,.0275),source_index=ix,view=vi,normal_missing=norm_missing,u_replaced=replaced)
        dump(pr/'receipt.json',dict(at=stamp(),site=site,prior=prior,raw_points=len(x),excluded=int(excluded.sum()),background_points=len(ix),
            normal_missing=int(norm_missing.sum()),u_replaced=int(replaced.sum()),medians=med,sha256=sha(dest),
            source_sha256=sha(xyzfile),config_sha256=lock['config_sha256'],binding_sha256=sha(binding),scientific_verdict=None))
        print('BACKGROUND_COMPLETE',site,prior,len(ix),flush=True)


if __name__=='__main__':main()
