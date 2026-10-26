"""Two native-photo prior outlines per example/prior; no judgment or GT selection."""
import cv2
from common import *
from cameras import Cameras
from run_measure import selected_geometry

def plotting():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family':'Noto Sans CJK JP','axes.unicode_minus':False,'font.size':9})
    return plt
def main():
    plt=plotting();cam=Cameras();records=[];dest=D/'figures/projection';dest.mkdir(parents=True,exist_ok=True)
    for prior in ['LoD2','ALS']:
        gs=[];ss=[]
        for t in load(W/'inputs/tiles.json'):
            f=O/'work/pilot'/f'{t["id"]}__{prior}_selection.npz'
            if not f.exists():continue
            g,_=selected_geometry('pilot',t['id'],prior);gs.append(g);ss.append(npz(f))
        g={k:np.concatenate([d[k] for d in gs]) for k in gs[0]};s={k:np.concatenate([d[k] for d in ss]) for k in ss[0]}
        for building in EXAMPLES:
            mask=(g['building']==building)&(g['kind']==1)&g['geometry_valid'];idx=np.flatnonzero(mask)
            if not len(idx):continue
            c=g['centre'][idx];e1=g['tangent1'][idx];e2=g['tangent2'][idx]
            q=c[:,None,:]+np.array([[-.25,-.25],[.25,-.25],[.25,.25],[-.25,.25]])[None,:,0,None]*e1[:,None,:]+np.array([[-.25,-.25],[.25,-.25],[.25,.25],[-.25,.25]])[None,:,1,None]*e2[:,None,:]
            candidates=np.unique(s['selected_images'][idx]);rank=[]
            for j in candidates[candidates>=0]:
                uv,z,guard=cam.project(q,int(j));valid=guard.all(1)&(uv[:,:,0]>=0).all(1)&(uv[:,:,0]<cam.w).all(1)&(uv[:,:,1]>=0).all(1)&(uv[:,:,1]<cam.h).all(1)
                if valid.mean()<.95:continue
                u=uv[valid];a=.5*np.abs(np.sum(u[:,:,0]*np.roll(u[:,:,1],-1,axis=1)-u[:,:,1]*np.roll(u[:,:,0],-1,axis=1),axis=1)).sum();rank.append((a,int(j)))
            rank=sorted(rank,reverse=True)[:2]
            for k,(_,j) in enumerate(rank):
                uv,z,guard=cam.project(q,j);valid=guard.all(1)&(uv[:,:,0]>=0).all(1)&(uv[:,:,0]<cam.w).all(1)&(uv[:,:,1]>=0).all(1)&(uv[:,:,1]<cam.h).all(1);uv=uv[valid]
                lo=np.maximum(0,np.floor(uv.min((0,1))-100).astype(int));hi=np.minimum([cam.w,cam.h],np.ceil(uv.max((0,1))+100).astype(int))
                rgb=cam.rgb(j)[lo[1]:hi[1],lo[0]:hi[0]].copy();maskim=np.zeros(rgb.shape[:2],np.uint8)
                cv2.fillPoly(maskim,[np.rint(u-lo).astype(np.int32) for u in uv],255)
                edge=maskim-cv2.erode(maskim,np.ones((3,3),np.uint8));rgb[edge>0]=[255,210,0]
                fig,ax=plt.subplots(figsize=(9,7));ax.imshow(rgb);ax.axis('off');ax.set_title(f'{building} · {prior}\n{cam.names[j]}')
                fig.tight_layout();name=f'{building}_{prior}_{k+1}';fig.savefig(dest/f'{name}.png',dpi=300);plt.close(fig)
                rec=dict(building=building,prior=prior,image=cam.names[j],image_index=j,crop_px=[*lo,*hi],point_ids=g['point_id'][idx],projected_points=int(valid.sum()),total_points=len(idx),outline='prior-plane 0.50m point support square union; no GT shift',source='[이 발주에서 냄]')
                dump(dest/f'{name}.json',rec);records.append({k:v for k,v in rec.items() if k!='point_ids'})
            if len(rank)<2:records.append(dict(building=building,prior=prior,status='확인 불가',reason='fewer than 2 selected training views contain 95% of example roof points',available=len(rank)))
    dump(D/'tables/projection_photos.json',dict(rows=records,scientific_verdict=None));print('projection photos',len(records))
if __name__=='__main__':main()
