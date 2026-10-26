"""Public overview maps and photo/curve montages; no automatic material/cause labels."""
import argparse,cv2
from matplotlib.patches import Polygon
from common import *
from cameras import Cameras
from figures import plotting,save,curve_plot,COLORS
from evaluate import join

def overall(plt,d,prior,stage):
    split=load(W/'building_split.json');held=set(split['holdout']);blds=load(W/'inputs/lod2_context_buildings.json')
    if isinstance(blds,dict):blds=list(blds.values())
    for mode in ['all','unexplained']:
        m=(d['kind']==1)&(d['unexplained'] if mode=='unexplained' else True)
        fig,ax=plt.subplots(figsize=(11,11));ax.scatter(d['centre'][m,0],d['centre'][m,1],s=.3,c=np.array(COLORS)[d['judgment'][m,4]],marker='s',linewidths=0,rasterized=True)
        polygons=0
        for b in blds:
            if b['id'] not in held:continue
            for surf in b['surfaces']['ground']:
                xy=np.array(surf['ext'])[:,:2]-[690953,5336071];ax.add_patch(Polygon(xy,facecolor='#dedede',edgecolor='#888888',hatch='///',lw=.3));polygons+=1
        ax.set_aspect('equal');ax.set_xlabel('x (m)');ax.set_ylabel('y (m)');ax.set_title(f'{prior} · '+('정하는 곳' if mode=='all' else '차가 설명 안 되는 곳'))
        for color,label in [('#238b45','지지'),('#d73027','반박'),('#929292','모름')]:ax.scatter([],[],color=color,s=15,label=label)
        ax.legend();fig.tight_layout()
        save(fig,D/'figures'/stage/f'overall_{prior}_{mode}',dict(prior=prior,scope=mode,patch_ids=d['patch_id'][m],judgment=d['judgment'][m,4],holdout_display='grey hatching only',holdout_polygons=polygons));plt.close(fig)

def crop_component(cam,d,ids,p,pi):
    # Candidate photographs are exactly those selected for component points.
    choices=np.unique(p['selected_images'][pi]);q=d['centre'][ids]
    e1=d['tangent1'][ids];e2=d['tangent2'][ids]
    e1=e1/np.maximum(np.linalg.norm(e1,axis=1,keepdims=True),1e-15);e2=e2/np.maximum(np.linalg.norm(e2,axis=1,keepdims=True),1e-15)
    offsets=np.array([[-1,-1],[1,-1],[1,1],[-1,1]])
    quads=q[:,None,:]+.125*(offsets[None,:,0,None]*e1[:,None,:]+offsets[None,:,1,None]*e2[:,None,:])
    border=q[:,None,:]+3.125*(offsets[None,:,0,None]*e1[:,None,:]+offsets[None,:,1,None]*e2[:,None,:])
    ranked=[]
    for j in choices[choices>=0]:
        uv,z,guard=cam.project(quads,int(j));valid=guard.all(1)&(uv[:,:,0]>=0).all(1)&(uv[:,:,0]<cam.w).all(1)&(uv[:,:,1]>=0).all(1)&(uv[:,:,1]<cam.h).all(1)
        if not valid.all():continue
        area=.5*np.abs(np.sum(uv[:,:,0]*np.roll(uv[:,:,1],-1,axis=1)-uv[:,:,1]*np.roll(uv[:,:,0],-1,axis=1),axis=1)).sum()
        ranked.append((area,int(j),uv))
    if not ranked:return None,dict(status='확인 불가',reason='no selected camera contains the full component')
    _,j,uv=max(ranked,key=lambda x:x[0]);bu,_,bg=cam.project(border,j)
    if not bg.all():return None,dict(status='확인 불가',image=cam.names[j],reason='3m margin violates the fixed projection guard')
    rawlo=np.floor(bu.min((0,1))).astype(int);rawhi=np.ceil(bu.max((0,1))).astype(int)+1;lo=np.maximum(0,rawlo);hi=np.minimum([cam.w,cam.h],rawhi)
    rgb=cam.rgb(j)[lo[1]:hi[1],lo[0]:hi[0]].copy();mask=np.zeros(rgb.shape[:2],np.uint8)
    cv2.fillPoly(mask,[np.rint(u-lo).astype(np.int32) for u in uv],255);edge=mask-cv2.erode(mask,np.ones((3,3),np.uint8));rgb[edge>0]=[255,210,0]
    return rgb,dict(status='PASS',image=cam.names[j],image_index=j,crop_px=[*lo,*hi],margin_m=3.,crop_clipped=bool((lo!=rawlo).any() or (hi!=rawhi).any()),outline='0.25m patch support at prior plane, not GT')

def montages(plt,cam,d,p,prior,stage):
    rows=load(D/'tables'/stage/f'{prior}_components.json')['rows'];lab=npz(O/'evaluation'/stage/f'{prior}_components.npz');assert np.array_equal(d['patch_id'],lab['patch_id'])
    pid_to_i={pid:i for i,pid in enumerate(p['point_id'])};out=[]
    for group in ['false_refute','missed_refute','support_mvs_diff']:
        choices=sorted([r for r in rows if r['group']==group],key=lambda r:(-r['area_m2'],r['building'],r['component_id']));used={};selected=[]
        for r in choices:
            buildings=r.get('building_ids',r['building']).split(';')
            if any(used.get(b,0)>=3 for b in buildings):continue
            selected.append(r)
            for b in buildings:used[b]=used.get(b,0)+1
            if len(selected)==20:break
        for page in range(max(1,(len(selected)+4)//5)):
            subset=selected[page*5:(page+1)*5];fig,axs=plt.subplots(5,2,figsize=(12,17),gridspec_kw={'width_ratios':[2,1]});records=[]
            for k,(left,right) in enumerate(axs):
                if k>=len(subset):left.axis('off');right.axis('off');continue
                r=subset[k];ids=np.flatnonzero(lab[group]==r['component_id']);pids=np.unique(d['point_id'][ids]);pi=np.array([pid_to_i[x] for x in pids]);centre=np.average(d['centre'][ids],weights=d['area'][ids],axis=0);i=pi[np.argmin(np.linalg.norm(p['centre'][pi]-centre,axis=1))]
                rgb,meta=crop_component(cam,d,ids,p,pi)
                if rgb is not None:left.imshow(rgb)
                else:left.text(.5,.5,'사진 확인 불가',ha='center',va='center')
                left.axis('off');curve_plot(right,p,i,compact=True)
                line=f'{r["building"]} · {r["area_m2"]:.2f} m² · {LABELS[int(p["judgment"][i,4])]}\n안 {p["s_in"][i]:.3f} · 밖 {p["s_out"][i]:.3f}'
                left.set_title(line,fontsize=8)
                records.append(dict(**r,photo=meta,patch_ids=d['patch_id'][ids],point_ids=pids,centre_point=p['point_id'][i],s_in=p['s_in'][i],s_out=p['s_out'][i],judgment=p['judgment'][i,4]))
            title={'false_refute':'거짓 반박','missed_refute':'놓친 반박','support_mvs_diff':'지지 · MVS 다름'}[group]
            fig.suptitle(f'{prior} · {title} · {page+1}',fontsize=11);fig.tight_layout(rect=[0,0,1,.98]);save(fig,D/'figures'/stage/f'montage_{prior}_{group}_{page+1}',dict(rows=records,available_components=len(choices),selected_components=len(selected),max_per_building=3));plt.close(fig);out.extend(records)
    dump(D/'tables'/stage/f'{prior}_montage_selection.json',dict(rows=out,scientific_verdict=None))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pilot','full']);a=ap.parse_args();plt=plotting();cam=Cameras()
    for prior in ['LoD2','ALS']:
        d,p=join(prior,a.stage)
        if a.stage=='full':overall(plt,d,prior,a.stage)
        montages(plt,cam,d,p,prior,a.stage);print('maps and montages complete',prior,a.stage,flush=True)
if __name__=='__main__':main()
