"""Reproducible wall maps, registered source-face overlays and photo/curve examples."""
import cv2
from collections import defaultdict
from common import *
from cameras import Cameras
from wall_report import point_sets

COLORS=['#238b45','#d73027','#929292','#d3b76b','#c7c7c7']
def plotting():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family':'Noto Sans CJK JP','axes.unicode_minus':False,'font.size':9})
    return plt
@locked_public
def save(plt,fig,path,meta):
    path.parent.mkdir(parents=True,exist_ok=True);fig.savefig(path.with_suffix('.png'),dpi=300,bbox_inches='tight');plt.close(fig)
    dump(path.with_suffix('.json'),{**meta,'provenance':'[이 발주에서 냄]','scientific_verdict':None,'config_sha256':sha(C/'wallphoto_v1.json')})
def curve(ax,p,i):
    h=p['heights'][i];s=p['curve'][i].astype(float);m=np.isfinite(h)&np.isfinite(s);order=np.argsort(h[m]);ax.plot(h[m][order],s[m][order],color='#243b53',lw=1)
    if not m.any():ax.text(.5,.5,'유효 점수 없음',ha='center',transform=ax.transAxes)
    ax.axvspan(-3*p['sigma'][i],3*p['sigma'][i],color='#238b45',alpha=.12);ax.axvline(0,color='black',lw=.7)
    if np.isfinite(p['mvs_p'][i]):ax.axvline(p['mvs_p'][i],color='#e08214',ls='--',lw=.8)
    ax.set(xlabel='법선 거리 h (m)',ylabel='사진 점수',ylim=(-1,1));ax.grid(alpha=.2)
def concatenate(parts):return {k:np.concatenate([x[k] for x in parts]) for k in parts[0]}
def wall_triangles(tile,faces):
    md=W/'holdout/internal/prior_tiles'/tile;m=npz(md/'lod2_mesh.npz');shift=np.array(load(W/'holdout/internal/registration'/tile/'LoD2/summary.json')['registration']['shift_applied'])
    take=np.isin(m['tri_surface'],faces)
    return (m['V']+shift)[m['F'][take]]
def outlines(cam,p,ids,j):
    tris=[]
    for tile in np.unique(p['tile'][ids]):
        use=ids[p['tile'][ids]==tile];tris.append(wall_triangles(str(tile),np.unique(p['face_ext'][use])))
    if not tris:return np.empty((0,3,2))
    xyz=np.concatenate(tris);uv,z,guard=cam.project(xyz,j)
    valid=guard.all(1)&(uv[:,:,0]>=0).all(1)&(uv[:,:,0]<cam.w).all(1)&(uv[:,:,1]>=0).all(1)&(uv[:,:,1]<cam.h).all(1)
    return uv[valid]
def rank_photos(cam,p,ids):
    candidates=np.unique(p['selected_images'][ids]);rank=[]
    for j in candidates[candidates>=0]:
        # Fixed selected photograph set, projected wall support area; no truth.
        q=p['centre'][ids,None,:]+np.array([[-1,-1],[1,-1],[1,1],[-1,1]])[None,:,0,None]*.25*p['tangent1'][ids,None,:]+np.array([[-1,-1],[1,-1],[1,1],[-1,1]])[None,:,1,None]*.25*p['tangent2'][ids,None,:]
        uv,z,guard=cam.project(q,int(j));good=guard.all(1)&(uv[:,:,0]>=0).all(1)&(uv[:,:,0]<cam.w).all(1)&(uv[:,:,1]>=0).all(1)&(uv[:,:,1]<cam.h).all(1)
        area=.5*np.abs(np.sum(uv[good,:,0]*np.roll(uv[good,:,1],-1,axis=1)-uv[good,:,1]*np.roll(uv[good,:,0],-1,axis=1),axis=1)).sum()
        if area>0:rank.append((float(area),int(j)))
    return sorted(rank,reverse=True)
def photo_crop(cam,p,ids,j,centre=None):
    uv=outlines(cam,p,ids,j)
    if not len(uv):return None,dict(status='확인 불가',reason='no source wall triangles inside fixed camera guards')
    if centre is None:lo=np.maximum(0,np.floor(uv.min((0,1))-100).astype(int));hi=np.minimum([cam.w,cam.h],np.ceil(uv.max((0,1))+100).astype(int))
    else:
        i=centre;offset=np.array([[-3.25,-3.25],[3.25,-3.25],[3.25,3.25],[-3.25,3.25]])
        corners=p['centre'][i]+offset[:,0,None]*p['tangent1'][i]+offset[:,1,None]*p['tangent2'][i];cu,_,guard=cam.project(corners,j)
        if not guard.all():return None,dict(status='확인 불가',reason='3m crop outside projection guard')
        lo=np.maximum(0,np.floor(cu.min(0)).astype(int));hi=np.minimum([cam.w,cam.h],np.ceil(cu.max(0)).astype(int))
    if (hi<=lo).any():return None,dict(status='확인 불가',reason='empty crop')
    rgb=cam.rgb(j)[lo[1]:hi[1],lo[0]:hi[0]].copy();mask=np.zeros(rgb.shape[:2],np.uint8)
    cv2.fillPoly(mask,[np.rint(u-lo).astype(np.int32) for u in uv],255)
    contours,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE);cv2.drawContours(rgb,contours,-1,(255,210,0),max(2,int(max(rgb.shape[:2])/1000)))
    return rgb,dict(status='PASS',image=cam.names[j],image_index=j,crop_px=[*lo,*hi],source='registered original LoD2 triangles; face_ext membership; no GT shift',triangle_count=len(uv))

def maps(plt,p,stage,buildings):
    # Join only public patch values after all measurement results are frozen.
    rows=[]
    for tile in np.unique(p['tile']):
        raw=npz(W/'patch_values'/f'{tile}__LoD2__R1.5.npz');mp=npz(O/'geometry'/f'{tile}__LoD2__mapping.npz');pp=np.flatnonzero(p['tile']==tile);lookup={int(p['geometry_index'][i]):i for i in pp}
        keep=np.array([int(i) in lookup for i in mp['point_index']]);src=mp['source_index'][keep];pi=np.array([lookup[int(i)] for i in mp['point_index'][keep]])
        d={k:raw[k][src] for k in ['patch_id','centre','normal','tangent1','tangent2','building','face_ext','area','cell','gt_p','gt_status','roof_type','kind','u_mvs','u_prior']};sp,_=sigmas(d,'LoD2')
        d.update(tile=np.full(len(src),tile),judgment=p['judgment'][pi,4],prior_right=np.where((d['gt_status']==0)&np.isfinite(d['gt_p']),(abs(d['gt_p'])<=3*sp).astype(int),-1));rows.append(d)
    d=concatenate(rows)
    for b in buildings:
        ids=np.flatnonzero(d['building']==b)
        if not len(ids):continue
        facekeys=np.array([f'{d["tile"][i]}:{d["face_ext"][i]}' for i in ids]);groups=[ids[facekeys==f] for f in np.unique(facekeys)]
        # Up to four face strips per row, common metric scale across all three panels.
        uv=np.full((len(d['area']),2),np.nan);labels=[];x0=y0=0.;rowheight=0.
        for fi,g in enumerate(groups):
            if fi and fi%4==0:y0-=rowheight+3.;x0=0.;rowheight=0.
            frame_ok=(np.linalg.norm(d['tangent1'][g],axis=1)>1e-8)&(np.linalg.norm(d['tangent2'][g],axis=1)>1e-8)
            if not frame_ok.any():
                labels.append(dict(face_ext=int(d['face_ext'][g[0]]),tile=str(d['tile'][g[0]]),origin=None,patches=len(g),status='확인 불가: source tangents absent'));continue
            first=g[np.flatnonzero(frame_ok)[0]]
            t1=d['tangent1'][first];t2=d['tangent2'][first];t1=t1/np.linalg.norm(t1);t2=t2/np.linalg.norm(t2)
            xy=np.c_[d['centre'][g]@t1,d['centre'][g]@t2];xy-=xy.min(0);height=float(np.ptp(xy[:,1]));uv[g]=xy+[x0,y0-height]
            labels.append(dict(face_ext=int(d['face_ext'][g[0]]),tile=str(d['tile'][g[0]]),origin=[x0,y0-height],tangent_horizontal=t1.tolist(),tangent_vertical=t2.tolist(),patches=len(g)))
            x0+=float(np.ptp(xy[:,0]))+3.;rowheight=max(rowheight,float(np.ptp(xy[:,1])))
        fig,axes=plt.subplots(1,3,figsize=(18,max(6,min(18,3*len(groups)/4))));fig.suptitle(b+' · 벽 펼침',fontsize=12)
        palette1=np.array(COLORS);palette2=np.array(['#aaaaaa','#d73027','#238b45']);palette3=np.array(['#4daf4a','#e41a1c','#377eb8','#984ea3','#ff7f00','#a65628','#aaaaaa'])
        for ax,title,color in [(axes[0],'사진 판단 (δ 0.10, s_min 0.3)',palette1[d['judgment'][ids]]),(axes[1],'사전 정보가 맞나 (참값 3σ)',palette2[d['prior_right'][ids]+1]),(axes[2],'넓히기 칸 (0–6)',palette3[d['cell'][ids]])]:
            ax.scatter(uv[ids,0],uv[ids,1],s=1.5,marker='s',c=color,linewidths=0,rasterized=True);ax.set_aspect('equal');ax.set_title(title);ax.set(xlabel='면 접선 가로 (m)',ylabel='면 접선 세로 (m)')
            for r in labels:
                if r['origin'] is not None:ax.text(*r['origin'],str(r['face_ext']),fontsize=5)
        from matplotlib.patches import Patch
        axes[0].legend(handles=[Patch(color=COLORS[i],label=LABELS[i]) for i in range(5)],loc='lower center',fontsize=6)
        axes[1].legend(handles=[Patch(color=c,label=l) for c,l in zip(palette2,['확인 불가','틀림','맞음'])],loc='lower center',fontsize=6)
        axes[2].legend(handles=[Patch(color=palette3[i],label=str(i)) for i in range(7)],loc='lower center',ncol=7,fontsize=6)
        fig.tight_layout();save(plt,fig,D/'figures'/stage/('wall_map_'+b),dict(building=b,patch_ids=d['patch_id'][ids],face_frames=labels,layout='source tangent coordinates per (tile,face_ext); four strips per row',judgment=d['judgment'][ids],prior_right=d['prior_right'][ids],cell=d['cell'][ids]))

def figures(stage='pilot'):
    plt=plotting();parts=[p for _,p in point_sets(stage)]
    if not parts:return
    p=concatenate(parts);cam=Cameras();rng=np.random.default_rng(20261028);rows=[]
    if stage=='full':
        totals=defaultdict(float)
        for tile in np.unique(p['tile']):
            raw=npz(W/'patch_values'/f'{tile}__LoD2__R1.5.npz');sp,sm=sigmas(raw,'LoD2');m=(raw['kind']==2)&(abs(raw['mvs_p'])>3*np.sqrt(sp**2+sm**2))
            for b in np.unique(raw['building'][m]):totals[str(b)]+=float(raw['area'][m&(raw['building']==b)].sum())
        maps(plt,p,stage,sorted(totals,key=lambda b:(-totals[b],b))[:10]);return
    maps(plt,p,stage,EXAMPLES)
    for b in EXAMPLES:
        ids=np.flatnonzero(p['building']==b);rank=rank_photos(cam,p,ids) if len(ids) else []
        for k,(_,j) in enumerate(rank[:2]):
            rgb,meta=photo_crop(cam,p,ids,j);fig,ax=plt.subplots(figsize=(9,7));ax.axis('off')
            if rgb is not None:ax.imshow(rgb)
            else:ax.text(.5,.5,'확인 불가',ha='center')
            ax.set_title(b+' · '+cam.names[j]);save(plt,fig,D/'figures/projection'/f'{b}_{k+1}',dict(building=b,**meta));rows.append(dict(building=b,**meta))
        if len(rank)<2:rows.append(dict(building=b,status='확인 불가',reason='fewer than two selected photographs',available=len(rank)))
    dump(D/'tables/projection_photos.json',dict(rows=rows,scientific_verdict=None))
    for judgment in range(5):
        ids=np.flatnonzero(p['judgment'][:,4]==judgment);selected=rng.choice(ids,min(3,len(ids)),replace=False)
        for k,i in enumerate(selected):
            fig,ax=plt.subplots(figsize=(6,4));curve(ax,p,int(i));ax.set_title(LABELS[judgment]+' · '+p['building'][i]);save(plt,fig,D/'figures/pilot'/f'curve_{judgment}_{k+1}',dict(point_id=p['point_id'][i],judgment=judgment,heights=p['heights'][i],curve=p['curve'][i],seed=20261028))
    for judgment in [1,2]:
        ids=np.flatnonzero(p['judgment'][:,4]==judgment);ids=rng.permutation(ids);selected=[];used=defaultdict(int)
        for i in ids:
            b=str(p['building'][i])
            if used[b]>=3:continue
            rank=rank_photos(cam,p,np.array([i]))
            if not rank:continue
            selected.append((int(i),rank[0][1]));used[b]+=1
            if len(selected)==10:break
        for page in range(max(1,(len(selected)+4)//5)):
            subset=selected[page*5:(page+1)*5];fig,axs=plt.subplots(5,2,figsize=(12,16),gridspec_kw={'width_ratios':[2,1]});meta=[]
            if not subset:axs[0,0].text(.5,.5,'조건에 맞는 사진 확인 불가',ha='center')
            for row,(left,right) in enumerate(axs):
                left.axis('off')
                if row>=len(subset):right.axis('off');continue
                i,j=subset[row];rgb,record=photo_crop(cam,p,np.array([i]),j,centre=i)
                if rgb is not None:left.imshow(rgb)
                else:left.text(.5,.5,'확인 불가',ha='center')
                curve(right,p,i);left.set_title(f'{p["building"][i]} · {p["area"][i]:.2f} m² · {LABELS[judgment]}\n안 {p["s_in"][i]:.3f} · 밖 {p["s_out"][i]:.3f}',fontsize=8)
                meta.append(dict(point_id=p['point_id'][i],building=p['building'][i],area_m2=p['area'][i],s_in=p['s_in'][i],s_out=p['s_out'][i],photo=record))
            fig.suptitle('벽 · '+LABELS[judgment]);fig.tight_layout(rect=[0,0,1,.98]);save(plt,fig,D/'figures/pilot'/f'montage_{judgment}_{page+1}',dict(rows=meta,available_points=len(ids),selected_points=len(selected),max_per_building=3,margin_m=3,seed=20261028))
    print('wall figures complete',stage,flush=True)
if __name__=='__main__':
    import sys
    figures(sys.argv[1] if len(sys.argv)>1 else 'pilot')
