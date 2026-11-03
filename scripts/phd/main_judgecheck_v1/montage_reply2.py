"""Select wrong-photo components by the inherited 0.36m definition; no manual cause guesses."""
import json,sys
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from matplotlib.collections import PolyCollection
from shapely.geometry import Polygon
from shapely.ops import unary_union
from figures_reply2 import plt,BASE,D,C,Path,dump,now,sha,loadz,Cameras,rgb,val,EX
from photo_planes import tangent

def main(prior,scope='roofs'):
    files=sorted((BASE/'core_points').glob(f'*__{prior}__*.npz'));files=[p for p in files if scope=='all' or p.stem.endswith('__1')]
    keys=['patch_id','photo_point_id','building','centre','normal','prior_height_m','area','surf','kind','geometry','cell','photo_code'];parts=[loadz(p) for p in files];g={k:np.concatenate([p[k] for p in parts],axis=1 if k=='photo_code' else 0) for k in keys};g['tile']=np.concatenate([np.full(len(part['patch_id']),p.stem.split('__')[0]) for p,part in zip(files,parts)]);del parts
    candidates=[];small_count=0;small_area=0.
    for reason,cell,photo in [('틀린 지지',1,0),('틀린 반박',2,1)]:
        mask=(g['geometry']==1)&(g['cell']==cell)&(g['photo_code'][0]==photo)
        for bid in np.unique(g['building'][mask]):
            for kind in np.unique(g['kind'][mask&(g['building']==bid)]):
                ix=np.flatnonzero(mask&(g['building']==bid)&(g['kind']==kind));pairs=cKDTree(g['centre'][ix]).query_pairs(.36,output_type='ndarray')
                matrix=coo_matrix((np.ones(len(pairs)),(pairs[:,0],pairs[:,1])),shape=(len(ix),len(ix)));_,labels=connected_components(matrix,directed=False)
                for label in np.unique(labels):
                    take=ix[labels==label];area=float(g['area'][take].sum())
                    if area<1:small_count+=1;small_area+=area;continue
                    candidates.append(dict(reason=reason,building=str(bid),kind=int(kind),area_m2=area,indices=take))
    candidates.sort(key=lambda c:(-c['area_m2'],c['building'],c['reason'],str(g['patch_id'][c['indices'][0]])))
    chosen=[];counts={};builds={}
    for c in candidates:
        if len(chosen)>=4:break
        if builds.get(c['building'],0)>=2:continue
        chosen.append(c);counts[c['reason']]=counts.get(c['reason'],0)+1;builds[c['building']]=builds.get(c['building'],0)+1
    selection=dict(at=now(),prior=prior,scope=scope,component_rule='same reason, building, kind; 3D centre distance <=0.36m; take four per prior from the union of wrong support/refute in descending area, max two per building; eight across both priors',
        selected=[{k:(g['patch_id'][v].tolist() if k=='indices' else v) for k,v in c.items()} for c in chosen],below_1m2_count=small_count,below_1m2_area_m2=small_area,
        available_candidates=len(candidates),selected_count=len(chosen),unfilled_slots=4-len(chosen),excluded_shared_cores=EX,scientific_verdict=None)
    dump(C/f'figure2.{prior}.{scope}.selection.reply2.json',selection);cam=Cameras();outputs=[]
    for number,c in enumerate(chosen,1):
        ix=c['indices'];centre=np.average(g['centre'][ix],axis=0,weights=g['area'][ix]);represent=ix[np.argmin(np.linalg.norm(g['centre'][ix]-centre,axis=1))];pid=g['photo_point_id'][represent]
        targetfile=BASE/'photo_targets'/f'{g["tile"][represent]}__{prior}__{c["kind"]}.npz';old=loadz(targetfile);pi=int(np.flatnonzero(old['point_id']==pid)[0]);new=loadz(BASE/'photo_points'/targetfile.name);t=json.loads((C/f'photo_threshold.{prior}_{c["kind"]}.reply2.lock.json').read_text())['t']
        camera_sets=[]
        for tile in np.unique(g['tile'][ix]):
            members=np.unique(g['photo_point_id'][ix[g['tile'][ix]==tile]])
            for folder in ['photo_targets','photo_points']:
                with np.load(BASE/folder/f'{tile}__{prior}__{c["kind"]}.npz') as z:
                    take=np.isin(z['point_id'],members);camera_sets.append(z['selected_images'][take].ravel())
        candidates_camera=np.unique(np.concatenate(camera_sets));candidates_camera=candidates_camera[candidates_camera>=0]
        points=g['centre'][ix]+g['prior_height_m'][ix,None]*g['normal'][ix];best=None
        for j in candidates_camera:
            uv,_,ok=cam.project(points,int(j));ok&=(uv[:,0]>=0)&(uv[:,0]<cam.w)&(uv[:,1]>=0)&(uv[:,1]<cam.h)
            if not ok.any():continue
            size=np.ptp(uv[ok],axis=0);score=float(np.prod(size))
            if best is None or score>best[0]:best=(score,int(j))
        fig=plt.figure(figsize=(12.4,6.5));grid=fig.add_gridspec(2,2,width_ratios=[1.65,1],hspace=.42,wspace=.23);ax=fig.add_subplot(grid[:,0]);curveax=fig.add_subplot(grid[0,1]);barax=fig.add_subplot(grid[1,1]);camera=None;crop=None
        if best is not None:
            camera=best[1];e1,e2=tangent(np.mean(g['normal'][ix],axis=0)/np.linalg.norm(np.mean(g['normal'][ix],axis=0)));expanded=np.concatenate([points+u*3*e1+v*3*e2 for u,v in [(-1,-1),(-1,1),(1,-1),(1,1)]]);uv,_,ok=cam.project(expanded,camera)
            x0,y0=np.maximum(0,np.floor(uv[ok].min(0))).astype(int);x1,y1=np.minimum([cam.w,cam.h],np.ceil(uv[ok].max(0))).astype(int);im=rgb(cam,camera);ax.imshow(im[y0:y1,x0:x1],extent=[x0,x1,y1,y0]);crop=[int(x0),int(y0),int(x1),int(y1)]
            for take,color,width in [(np.flatnonzero((g['building']==c['building'])&(g['kind']==c['kind'])),'#ffffff',.18),(ix,'#ef3434',.65)]:
                polys=[]
                for k in take:
                    n=g['normal'][k]
                    if not np.isfinite(n).all() or not np.isfinite(g['prior_height_m'][k]):continue
                    a,b=tangent(n);p=g['centre'][k]+g['prior_height_m'][k]*n;corners=p+np.array([-1,1,1,-1])[:,None]*.125*a+np.array([-1,-1,1,1])[:,None]*.125*b;uv,_,ok=cam.project(corners,camera)
                    if ok.all():polys.append(uv)
                if polys:
                    union=unary_union([Polygon(p).buffer(0) for p in polys]);boundary=union.boundary
                    for line in getattr(boundary,'geoms',[boundary]):
                        xy=np.asarray(line.coords)
                        if len(xy):ax.plot(xy[:,0],xy[:,1],color=color,lw=width)
            ax.set_xlim(x0,x1);ax.set_ylim(y1,y0)
        else:ax.text(.5,.5,'고른 사진 없음',ha='center',va='center',transform=ax.transAxes)
        ax.set_xticks([]);ax.set_yticks([]);ax.set_title('흰색 사전 정보 · 빨강 틀린 덩어리')
        h=old['heights'][pi].astype(float);scores=old['curve'][pi].astype(float);hp=float(old['core_prior_height_median_m'][pi]) if prior=='ALS' else 0.;b=float(old['b_m'][pi]);dm=float(old['core_d_median_m'][pi])
        curveax.plot(h[:141],scores[:141],color='#526b8a',lw=1.4)
        if np.isfinite(h[141:]).any():curveax.plot(h[141:],scores[141:],color='#526b8a',lw=1.4,marker='.',ms=3)
        curveax.axvspan(hp-b,hp+b,color='#f4c56a',alpha=.3);curveax.axvline(hp+dm,color='#337acc',ls='--',lw=1.3);curveax.set_title('옛 곡선 · 띠는 사전 정보 범위');curveax.set_xlabel('높이 (m)');curveax.set_ylabel('사진 점수');curveax.grid(alpha=.15)
        v=new['best_score'][0,pi]
        for k,s in enumerate(v):
            if np.isfinite(s):barax.barh(k,s,color=['#f39b34','#3f88db'][k],height=.48)
            barax.text(max(0,float(s))+.02 if np.isfinite(s) else .02,k,f'{s:.3f}' if np.isfinite(s) else '확인 불가',ha='left',va='center')
        if t is not None:barax.axvline(t,color='#9e2830',ls='--',label=f'기준 {t:.3f}');barax.legend(frameon=False)
        barax.set_yticks([0,1],['사전 정보 면','MVS 면']);barax.invert_yaxis();barax.set_xlim(min(-.1,float(np.nanmin(v))-.1) if np.isfinite(v).any() else -.1,1.13);barax.set_title('고친 사진 점수');barax.set_xlabel('사진 점수')
        fig.suptitle(f'{"항공 LiDAR" if prior=="ALS" else "LoD2"} · {c["reason"]}: 두 면의 점수와 사진을 함께 확인',fontsize=14,y=.97);fig.text(.5,.03,f'{c["building"]} · {c["area_m2"]:.2f} m² · {"보존 / 칸 1" if c["reason"]=="틀린 지지" else "보정 / 칸 2"} · {"지붕" if c["kind"]==1 else "벽"}  |  수동 까닭: __________',ha='center',fontsize=9);fig.subplots_adjust(top=.88,bottom=.13)
        out=D/'figures'/f'그림2_{prior}_{scope}_{number:02d}';fig.savefig(out.with_suffix('.png'),dpi=300);plt.close(fig)
        record=val(dict(at=now(),prior=prior,scope=scope,reason=c['reason'],building=c['building'],kind=c['kind'],area_m2=c['area_m2'],patch_ids=g['patch_id'][ix].tolist(),photo_point_ids=g['photo_point_id'][ix].tolist(),representative_photo_point_id=str(pid),camera=cam.names[camera] if camera is not None else None,crop_pixels=crop,
            camera_candidates=candidates_camera.tolist(),camera_selection='maximum projected component bounding-box area among selected photos of all component points',outline='boundary of exact union of projected 0.25m core cells',old_heights=h.tolist(),old_curve=scores.tolist(),old_curve_uses_old_normal=True,prior_support_centre_m=hp,b_m=b,mvs_height_m=hp+dm,s_P=float(v[0]),s_M=float(v[1]),threshold=t,manual_cause=None,excluded_shared_cores=EX,scientific_verdict=None));dump(out.with_suffix('.json'),record);outputs.append(str(out.with_suffix('.png')));print('FIGURE_PHOTO',out.name,flush=True)
    dump(BASE/'figures'/f'{prior}_{scope}_montage.complete.json',dict(at=now(),files=outputs,selection=selection,scientific_verdict=None))
if __name__=='__main__':main(*sys.argv[1:])
