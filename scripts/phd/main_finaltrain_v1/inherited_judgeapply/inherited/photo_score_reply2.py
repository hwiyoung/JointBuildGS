"""Packed float64 NCC, image-batched GPU work, decode-once pyramid cache."""
import json,time,sys,resource,collections
import numpy as np
import torch
import torch.nn.functional as F
from preflight import C,O,Path,sha,dump,now
from geometry import loadz,savez
from photo_cameras import Cameras
from photo_score import project,ncc_vectors
BASE=O/'r2'

class ImageCache:
    def __init__(self,cam,root,budget=10*2**30):
        self.cam=cam;self.root=root;root.mkdir(parents=True,exist_ok=True);self.budget=budget;self.used=0;self.ram={};self.paths={};self.decodes=0;self.decode_seconds=0.;self.spill_bytes=0
    def prepare(self,levels):
        inherited=Path('/art/phase-payloads/phd/main_photocheck_v1/PHD-MAIN-PHOTOCHECK-v1/image_cache')
        for number,(j,wanted) in enumerate(sorted(levels.items()),1):
            paths={k:self.root/f'{j}_{k}.npy' for k in range(6)}
            marker=self.root/f'{j}.complete.json'
            inherited_paths={k:inherited/f'{j:04d}_L{k}.npy' for k in wanted}
            if all(p.exists() for p in inherited_paths.values()):
                paths.update(inherited_paths)
            elif not marker.exists():
                t=time.monotonic();images=self.cam.gray_pyramid(int(j),set(range(6)));self.decode_seconds+=time.monotonic()-t;self.decodes+=1
                for k,im in images.items():np.save(paths[k],im)
                dump(marker,dict(camera=int(j),source_image=self.cam.names[j],levels=6,source_sha256=sha(Path(__file__).parent/'photo_cameras.py')))
                del images,im
            else:assert json.loads(marker.read_text())['source_sha256']==sha(Path(__file__).parent/'photo_cameras.py')
            images={k:np.load(paths[k],mmap_mode='r') for k in wanted}
            for k,im in images.items():
                key=(int(j),int(k))
                if self.used+im.nbytes<=self.budget:self.ram[key]=np.array(im);self.used+=im.nbytes
                else:
                    self.paths[key]=paths[k];self.spill_bytes+=im.nbytes
            if number%25==0:print('PHOTO_CACHE',number,len(levels),'RAM_GIB',self.used/2**30,flush=True)
    def get(self,j,k):return self.ram[(j,k)] if (j,k) in self.ram else np.load(self.paths[(j,k)],mmap_mode='r')

def score(g,root,device='cuda',chunk_rows=900000,batch_rows=8192):
    torch.set_num_threads(4);start=time.monotonic();cam=Cameras();N=len(g['point_id']);P=2*N;planes=g['row_plane'];height=g['row_height'];H=len(height)
    sel=g['selected_images'].reshape(P,10).copy();sel[~g['available'].reshape(P)]=-1
    centres=g['centres'].reshape(P,3);normals=g['normals'].reshape(P,3);e1=g['tangent1'].reshape(P,3);e2=g['tangent2'].reshape(P,3)
    counts=(sel>=0).sum(1);work=np.flatnonzero((counts[planes]>=3)|((height==0)&(counts[planes]>0)))
    # Required pyramid levels are determined once for all rows/planes in tile.
    levels=np.full((P,10),-1,np.int8);need={}
    for j in np.unique(sel[sel>=0]):
        pp,slots=np.where(sel==j);dist=np.linalg.norm(centres[pp]-cam.centres[j],axis=1);gsd=dist/np.sqrt(cam.p[0]*cam.p[1])
        lev=np.argmin(abs(gsd[:,None]*2.**np.arange(6)-.02),axis=1);lev[gsd>=.02]=0;levels[pp,slots]=lev;need[int(j)]=set(lev.tolist())
    cache=ImageCache(cam,BASE/'image_cache');ct=time.monotonic();cache.prepare(need);cache_seconds=time.monotonic()-ct
    dev=torch.device(device);to=lambda a:torch.as_tensor(np.asarray(a),device=dev,dtype=torch.float64)
    cp=to(cam.p);R=to(cam.R);tr=to(cam.t);xyz=to(centres);normal=to(normals);a=to(e1);b=to(e2)
    offsets=to(np.stack(np.meshgrid(np.arange(25)*.02-.24,np.arange(25)*.02-.24,indexing='xy'),-1).reshape(625,2));corners=to([[-.25,-.25],[.25,-.25],[.25,.25],[-.25,.25]])
    scores=np.full((2,H),np.nan);valid_counts=np.zeros((2,H),np.uint8);textures=np.full((2,P,10),np.nan)
    timings=[];gpu_seconds=0.;upload_seconds=0.;blocks=0;total_calls=0;rows_per_call=[];arithmetic_start=time.monotonic()
    with torch.inference_mode():
        for begin in range(0,len(work),chunk_rows):
            ids=work[begin:begin+chunk_rows];rp=planes[ids];rh=to(height[ids]);M=len(ids);blocks+=1
            acc=torch.zeros((2,M,625),device=dev,dtype=torch.float64);normsum=torch.zeros((2,M),device=dev,dtype=torch.float64)
            count=torch.zeros((2,M),device=dev);zero=torch.zeros((2,M),device=dev)
            selected=sel[rp];pyramid=levels[rp]
            for j in np.unique(selected[selected>=0]):
                local,slot=np.where(selected==j);tt=time.monotonic()
                for level in np.unique(pyramid[local,slot]):
                    keep=pyramid[local,slot]==level;loc=local[keep];slots=slot[keep];tup=time.monotonic()
                    image=cache.get(int(j),int(level));ih,iw=image.shape;im=torch.as_tensor(np.array(image,copy=True),device=dev,dtype=torch.float64)[None,None];del image
                    if device=='cuda':torch.cuda.synchronize()
                    upload_seconds+=time.monotonic()-tup
                    for k in range(0,len(loc),batch_rows):
                        ii=loc[k:k+batch_rows];ss=slots[k:k+batch_rows];ix=torch.as_tensor(ii,device=dev);pi=torch.as_tensor(rp[ii],device=dev)
                        cc=xyz[pi]+rh[ix,None]*normal[pi]
                        X=cc[:,None]+offsets[None,:,0,None]*a[pi,None]+offsets[None,:,1,None]*b[pi,None]
                        u,v,guard=project(X,R[j],tr[j],cp,cam.w,cam.h)
                        cornerX=cc[:,None]+corners[None,:,0,None]*a[pi,None]+corners[None,:,1,None]*b[pi,None]
                        cu,cv,cg=project(cornerX,R[j],tr[j],cp,cam.w,cam.h)
                        good=cg.all(-1)&(cu>=0).all(-1)&(cu<cam.w-1).all(-1)&(cv>=0).all(-1)&(cv<cam.h-1).all(-1)&guard.all(-1)
                        u=(u+.5)*(iw/cam.w)-.5;v=(v+.5)*(ih/cam.h)-.5
                        good&=(u>=0).all(-1)&(u<=iw-1).all(-1)&(v>=0).all(-1)&(v<=ih-1).all(-1)
                        grid=torch.stack([2*u/(iw-1)-1,2*v/(ih-1)-1],-1)[None];grid=torch.nan_to_num(grid,nan=-3.,posinf=3.,neginf=-3.)
                        values=F.grid_sample(im,grid,mode='bilinear',padding_mode='zeros',align_corners=True).reshape(len(ii),625)
                        masks=torch.as_tensor(np.unpackbits(g['mask_bits'][ids[ii]],axis=1,count=625).astype(bool),device=dev)
                        for mode in range(2):
                            mask=masks if mode==0 else torch.ones_like(masks);vec,std,npixels=ncc_vectors(values,mask)
                            gv=good&(npixels>=313);nonzero=std>1e-6;vec=torch.where((gv&nonzero)[:,None],vec,0.)
                            acc[mode,ix]+=vec;normsum[mode,ix]+=vec.square().sum(-1);count[mode,ix]+=gv;zero[mode,ix]+=gv&~nonzero
                            zi=np.flatnonzero(height[ids[ii]]==0)
                            if len(zi):textures[mode,rp[ii[zi]],ss[zi]]=torch.where(gv[zi],std[zi],torch.nan).cpu().numpy()
                        total_calls+=1;rows_per_call.append(len(ii));del X,u,v,grid,values,vec,cornerX,masks
                    del im
                if device=='cuda':torch.cuda.synchronize()
                gpu_seconds+=time.monotonic()-tt
            out=(acc.square().sum(-1)-normsum)/(count*(count-1)).clamp_min(1.)
            scores[:,ids]=torch.where((count>=3)&(zero==0),out,torch.nan).cpu().numpy();valid_counts[:,ids]=count.cpu().numpy().astype(np.uint8)
            del acc,normsum,count,zero,out
            print('PACKED_SCORE',root.name,min(begin+chunk_rows,len(work)),len(work),'rows','seconds',time.monotonic()-start,flush=True)
    best=np.full((2,P),np.nan);best_h=best.copy();texture=best.copy()
    for pi in range(P):
        left,right=g['plane_row_ptr'][pi:pi+2]
        for mode in range(2):
            s=scores[mode,left:right]
            if np.isfinite(s).any():j=int(np.nanargmax(s));best[mode,pi]=s[j];best_h[mode,pi]=height[left+j]
            v=textures[mode,pi];v=v[np.isfinite(v)]
            if len(v):texture[mode,pi]=np.median(v)
    timing=dict(at=now(),points=N,packed_rows=H,computed_rows=len(work),camera_count=len(need),original_image_decodes=cache.decodes,
        decode_seconds=cache.decode_seconds,image_cache_total_seconds=cache_seconds,image_cache_ram_gib=cache.used/2**30,image_cache_spill_gib=cache.spill_bytes/2**30,
        gpu_batched_seconds=gpu_seconds,upload_seconds=upload_seconds,arithmetic_and_reduction_seconds=time.monotonic()-arithmetic_start,
        total_seconds=time.monotonic()-start,row_blocks=blocks,batch_rows=batch_rows,gpu_calls=total_calls,
        rows_per_call_quantiles=np.quantile(rows_per_call,[0,.25,.5,.75,1]).tolist() if rows_per_call else [],
        peak_cpu_rss_gib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2,
        peak_gpu_gib=torch.cuda.max_memory_allocated()/2**30 if device=='cuda' else None,
        numeric_precision='float64 projection interpolation NCC',scientific_verdict=None)
    return dict(point_id=g['point_id'],curves=scores,valid_image_count=valid_counts,best_score=best.reshape(2,N,2),best_height=best_h.reshape(2,N,2),
        texture=texture.reshape(2,N,2),texture_by_view=textures.reshape(2,N,2,10),pyramid_levels=levels.reshape(N,2,10)),timing

def packed_reference():
    g=loadz(O/'r1/photo_benchmark/planes.npz');N=len(g['point_id']);rp=[];hh=[];mask=[];ptr=[0]
    for i in range(N):
        for k in range(2):
            valid=np.isfinite(g['heights'][i]) if g['available'][i,k] else np.zeros(len(g['heights'][i]),bool)
            n=int(valid.sum());rp.append(np.full(n,2*i+k,np.int32));hh.append(g['heights'][i,valid]);mask.append(np.packbits(g['masks'][i,k,valid],axis=1));ptr.append(ptr[-1]+n)
    g.update(row_plane=np.concatenate(rp),row_height=np.concatenate(hh),mask_bits=np.concatenate(mask),plane_row_ptr=np.array(ptr));return g

def subset(g,group):
    ix=np.flatnonzero(g['group']==group);N=len(g['point_id']);planes=np.stack([2*ix,2*ix+1],axis=1).ravel()
    lengths=np.diff(g['plane_row_ptr'])[planes];rows=np.concatenate([np.arange(g['plane_row_ptr'][p],g['plane_row_ptr'][p+1]) for p in planes]) if len(planes) else np.empty(0,int)
    out={k:v[ix] for k,v in g.items() if k not in ['row_plane','row_height','mask_bits','plane_row_ptr'] and len(v)==N}
    out.update(row_plane=np.repeat(np.arange(2*len(ix),dtype=np.int32),lengths),row_height=g['row_height'][rows],mask_bits=g['mask_bits'][rows],plane_row_ptr=np.r_[0,np.cumsum(lengths)])
    return out

def main(tile):
    group=None
    if ':' in tile:tile,group=tile.split(':');group=int(group)
    root=BASE/'photo_scores'/tile;root.mkdir(parents=True,exist_ok=True)
    if tile=='verify':g=packed_reference()
    else:
        assert json.loads((BASE/'photo_scores/verify/complete.json').read_text())['status']=='PASS_PACKED_PHOTO_PARITY'
        if tile=='benchmark':tile=json.loads((BASE/'target_census.json').read_text())['benchmark_tile'];root=BASE/'photo_scores'/tile;root.mkdir(parents=True,exist_ok=True)
        g=loadz(BASE/'photo_prepared'/f'{tile}.npz')
        if group is not None:
            g=subset(g,group);root=BASE/'photo_scores'/tile/f'group{group}';root.mkdir(parents=True,exist_ok=True)
    if (root/'complete.json').exists():print('PHOTO_SCORE_REUSE',root);return
    lock=C/'photo_score.reply2.lock.json';src={p.name:sha(p) for p in [Path(__file__),Path(__file__).parent/'photo_score.py',Path(__file__).parent/'photo_cameras.py']}
    if not lock.exists():dump(lock,dict(at=now(),config_sha256=sha(C/'judgecheck_v1.json'),sources=src,chunk_rows=900000,batch_rows=8192,
        image_read_rule='decode each unique image once for this revision; persist all six exact pyramid levels; bounded RAM cache reused across row blocks and roof/wall stages',scientific_verdict=None))
    else:
        previous=json.loads(lock.read_text())
        if previous['sources']!=src:
            saved=C/'revisions/r2/photo_score.initial_cache.lock.json'
            assert saved.exists() and previous==json.loads(saved.read_text())
            before=sha(C/'judgecheck_v1.json');cfg=json.loads((C/'judgecheck_v1.json').read_text());at=now()
            (C/'revisions/r2/judgecheck_v1.before_cache_reuse.json').write_bytes((C/'judgecheck_v1.json').read_bytes())
            (C/'revisions/r2/judgecheck_v1.reply2.before_cache_reuse.lock.json').write_bytes((C/'judgecheck_v1.reply2.lock.json').read_bytes())
            cfg['amendments'].append(dict(at=at,reason='Avoid duplicate raw-image decode and 6-level disk writes by reusing frozen PHOTOCHECK float32 gray cache read-only. Three decoded images matched byte-for-byte; full 200-point parity required before census.',previous_config_sha256=before,score_arithmetic_changed=False))
            cfg['execution']['photo_image_cache']='prefer immutable PHOTOCHECK grayscale NPY; task-local decode-once six-level cache for misses; 10GiB bounded memory cache'
            dump(C/'judgecheck_v1.json',cfg);current=json.loads((C/'judgecheck_v1.reply2.lock.json').read_text());current.update(at=at,config_sha256=sha(C/'judgecheck_v1.json'),previous_config_sha256=before);dump(C/'judgecheck_v1.reply2.lock.json',current)
            previous.update(at=at,config_sha256=sha(C/'judgecheck_v1.json'),sources=src,previous_lock_sha256=sha(saved),cache_amendment='read-only reuse of identical inherited grayscale cache; initial cache-only run interrupted before scoring')
            dump(lock,previous)
    result,timing=score(g,root)
    if tile=='verify':
        old=loadz(O/'r1/photo_benchmark/scores_cuda.npz');errors={}
        for name in ['best_score','best_height','texture','texture_by_view']:
            x=result[name];y=old[name];assert np.array_equal(np.isfinite(x),np.isfinite(y)),name;v=np.isfinite(x);err=float(np.max(abs(x[v]-y[v]))) if v.any() else 0
            assert err<(2e-4 if name.startswith('texture') else 2e-5),(name,err);errors[name]=err
        # Compare every stored height, including unavailable values.
        errs=[]
        for i in range(len(g['point_id'])):
            valid=np.isfinite(g['heights'][i])
            for k in range(2):
                l,r=g['plane_row_ptr'][2*i+k:2*i+k+2]
                if r==l:continue
                x=result['curves'][:,l:r];y=old['curves'][:,i,k][:,valid]
                assert np.array_equal(np.isfinite(x),np.isfinite(y));m=np.isfinite(x)
                if m.any():errs.append(float(np.max(abs(x[m]-y[m]))))
        assert max(errs)<2e-5;timing.update(status='PASS_PACKED_PHOTO_PARITY',errors=errors,max_curve_difference=max(errs))
    savez(root/'scores.npz',**result);timing['output_sha256']=sha(root/'scores.npz');dump(root/'complete.json',timing)
    print('PHOTO_COMPLETE',tile,json.dumps(timing),flush=True)

if __name__=='__main__':main(sys.argv[1])
