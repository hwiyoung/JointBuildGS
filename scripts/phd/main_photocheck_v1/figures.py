"""Requested development plots; GT is read only in this downstream presentation."""
import argparse,cv2
from matplotlib.collections import PolyCollection
from matplotlib.colors import ListedColormap,BoundaryNorm
from common import *
from cameras import Cameras
from projection_figures import plotting
from evaluate import join

COLORS=['#238b45','#d73027','#929292','#929292','#929292']
CELL=['#4292c6','#0072b2','#d55e00','#9e9ac8','#41ab5d','#a65628','#bdbdbd']
def belongs(p,b):
    return np.array([b in str(x).split(';') for x in p.get('building_ids',p['building'])])
def save(fig,path,metadata):
    path.parent.mkdir(parents=True,exist_ok=True);fig.savefig(path.with_suffix('.png'),dpi=300,bbox_inches='tight')
    dump(path.with_suffix('.json'),dict(**metadata,source='[이 발주에서 냄]',scientific_verdict=None))
def point_gt(d,pid):
    ids=np.flatnonzero((d['point_id']==pid)&d['gt_valid']);return float(np.median(d['gt_p'][ids])) if len(ids) else np.nan
def snippets(cam,p,i,h):
    off=np.stack(np.meshgrid(np.arange(25)*.02-.24,np.arange(25)*.02-.24),-1).reshape(-1,2)
    X=p['centre'][i]+h*p['normal'][i]+off[:,0,None]*p['tangent1'][i]+off[:,1,None]*p['tangent2'][i]
    result=[]
    for j,level in zip(p['selected_images'][i],p['pyramid_levels'][i]):
        if j<0:continue
        if not np.isfinite(h) or level<0:result.append((j,None));continue
        uv,z,valid=cam.project(X,int(j));im=cam.gray(int(j),int(level));H,W=im.shape
        u=((uv[:,0]+.5)*(W/cam.w)-.5).astype(np.float32).reshape(25,25);v=((uv[:,1]+.5)*(H/cam.h)-.5).astype(np.float32).reshape(25,25)
        if not valid.all() or u.min()<0 or u.max()>W-1 or v.min()<0 or v.max()>H-1:result.append((j,None));continue
        x0=np.floor(u).astype(int);y0=np.floor(v).astype(int);x1=np.minimum(x0+1,W-1);y1=np.minimum(y0+1,H-1);dx=u-x0;dy=v-y0
        result.append((j,(1-dx)*(1-dy)*im[y0,x0]+dx*(1-dy)*im[y0,x1]+(1-dx)*dy*im[y1,x0]+dx*dy*im[y1,x1]))
    return result
def curve_plot(ax,p,i,gt=np.nan,compact=False):
    h=p['heights'][i];s=p['curve'][i].astype(float);m=np.isfinite(h);order=np.argsort(h[m]);x=h[m][order];y=s[m][order]
    cuts=np.flatnonzero(np.diff(x)>.10001)+1
    for xx,yy in zip(np.split(x,cuts),np.split(y,cuts)):ax.plot(xx,yy,color='#225ea8',lw=.9)
    if len(x):ax.set_xlim(min(x.min(),gt) -.15 if np.isfinite(gt) else x.min()-.15,max(x.max(),gt)+.15 if np.isfinite(gt) else x.max()+.15)
    sigma=p['sigma'][i]
    if np.isfinite(sigma):ax.axvspan(-3*sigma,3*sigma,color='#a1d99b',alpha=.3)
    marks=[(0,'사전','#333333'),(p['mvs_p'][i],'MVS','#ff7f00'),(p['h_in'][i],'안','#238b45'),(p['h_out'][i],'밖','#d73027')]
    for value,label,color in marks:
        if np.isfinite(value):ax.axvline(value,color=color,ls='--',lw=.7,label=label)
    if np.isfinite(gt):ax.scatter([gt],[-.95],color='black',marker='o',s=12,label='참값 높이',zorder=8)
    ax.set_ylim(-1,1);ax.set_xlabel('h (m)');ax.set_ylabel('점수')
    if not compact:ax.legend(ncol=5,fontsize=7,loc='lower right')
def curve_figure(plt,cam,d,p,i,path,reason):
    n=max(1,int(p['selected_count'][i]));fig=plt.figure(figsize=(max(8,n*1.3),6.3));grid=fig.add_gridspec(3,n,height_ratios=[1,1,1.5])
    details=[]
    for row,h in enumerate([0.,p['h_out'][i]]):
        snippets0=snippets(cam,p,i,h)
        for k in range(n):
            ax=fig.add_subplot(grid[row,k]);ax.axis('off')
            if k<len(snippets0):
                j,im=snippets0[k]
                if im is not None:ax.imshow(im,cmap='gray',vmin=0,vmax=255,interpolation='nearest')
                else:ax.text(.5,.5,'확인 불가',ha='center',va='center')
                ax.set_title(f'{j} · h={h:.2f}' if np.isfinite(h) else f'{j} · h 없음',fontsize=7)
            else:ax.text(.5,.5,'사진 없음',ha='center',va='center')
    ax=fig.add_subplot(grid[2,:]);gt=point_gt(d,p['point_id'][i]);curve_plot(ax,p,i,gt)
    value=lambda x:f'{x:.3f}' if np.isfinite(x) else '없음'
    title=f'{p["building"][i]} · {p["prior"][i]} · {LABELS[int(p["judgment"][i,4])]} · 안 {value(p["s_in"][i])} · 밖 {value(p["s_out"][i])} · 시차 {p["parallax"][i]:.2f}'
    fig.suptitle(title,fontsize=9);fig.tight_layout(rect=[0,0,1,.95])
    save(fig,path,dict(point_id=p['point_id'][i],selected_images=p['selected_images'][i],image_names=[cam.names[j] for j in p['selected_images'][i] if j>=0],heights=p['heights'][i],curve=p['curve'][i].astype(float),sigma=p['sigma'][i],mvs_p=p['mvs_p'][i],gt_p_display_median=gt,reason=reason,judgment=int(p['judgment'][i,4]),s_in=p['s_in'][i],s_out=p['s_out'][i],h_in=p['h_in'][i],h_out=p['h_out'][i],parallax=p['parallax'][i]));plt.close(fig)

def examples(plt,d,p,prior,stage):
    folder=D/'figures'/stage
    for b in EXAMPLES:
      for kind in ([1,2] if b==EXAMPLES[5] else [1]):
        ids=np.flatnonzero((d['building']==b)&(d['kind']==kind))
        if not len(ids):continue
        truth=np.where(d['gt_valid'][ids],d['prior_right'][ids].astype(int),2);cells=d['cell'][ids]
        xyz=d['centre'][ids];x=xyz[:,0];y=xyz[:,1]
        if kind==2:
            centre=xyz[:,:2].mean(0);_,v=np.linalg.eigh((xyz[:,:2]-centre).T@(xyz[:,:2]-centre));x=(xyz[:,:2]-centre)@v[:,-1];y=xyz[:,2]
        fig,axs=plt.subplots(1,3,figsize=(14,4.8))
        vals=[d['judgment'][ids,4],np.array(truth),np.array(cells)];cmaps=[COLORS,['#d73027','#238b45','#929292'],CELL]
        titles=['사진 판단','사전 정보 맞음','넓히기 칸']
        for ax,vs,cs,title in zip(axs,vals,cmaps,titles):
            ax.scatter(x,y,c=np.array(cs)[vs],s=2,marker='s',linewidths=0);ax.set_aspect('equal');ax.set_title(title);ax.set_xlabel('거리 (m)' if kind==2 else 'x (m)');ax.set_ylabel('높이 (m)' if kind==2 else 'y (m)')
        for color,label in zip(COLORS[:3],['지지','반박','모름']):axs[0].scatter([],[],c=color,label=label,s=10)
        for color,label in zip(cmaps[1],['틀림','맞음','확인 불가']):axs[1].scatter([],[],c=color,label=label,s=10)
        for k,color in enumerate(CELL):axs[2].scatter([],[],c=color,label=str(k),s=10)
        for ax in axs:ax.legend(fontsize=6,ncol=3,loc='lower center',bbox_to_anchor=(.5,-.35))
        fig.suptitle(f'{b} · {prior} · {"지붕" if kind==1 else "비탈 관찰"}',fontsize=10);fig.tight_layout()
        save(fig,folder/f'map_{b}_{prior}_{kind}',dict(patch_ids=d['patch_id'][ids],point_ids=d['point_id'][ids],xy=np.c_[x,y],judgment=vals[0],truth_display=vals[1],cells=vals[2],truth_display_rule='source patch abs(gt_p)<=3*patch sigma; unavailable=2',kind=kind));plt.close(fig)

def sections(plt,d,p,prior,stage):
    cfg=load(C/'photocheck_v1.json')
    for q in [q for q in cfg['sections'] if q['prior']==prior]:
        a=np.array(q['a']);b=np.array(q['b']);v=b-a;L=np.linalg.norm(v);v/=L;perp=np.array([-v[1],v[0]]);xy=p['centre'][:,:2]-a
        along=xy@v;across=xy@perp;m=(along>=0)&(along<=L)&(abs(across)<=q['half_width'])&belongs(p,q['building']);ids=np.flatnonzero(m)
        fig,axs=plt.subplots(3,1,figsize=(12,7),height_ratios=[8,1,1],sharex=True);verts=[];scores=[];truth=[];cell=[]
        for i in ids:
            h=p['heights'][i];s=p['curve'][i];finite=np.isfinite(h)&np.isfinite(s);hh=h[finite];ss=s[finite].astype(float);dh=np.where(abs(hh)<=.5,.02,.1)/2
            zlo=p['centre'][i,2]+(hh-dh)*p['normal'][i,2];zhi=p['centre'][i,2]+(hh+dh)*p['normal'][i,2]
            for lo,hi,val in zip(zlo,zhi,ss):verts.append([[along[i]-.12,lo],[along[i]+.12,lo],[along[i]+.12,hi],[along[i]-.12,hi]]);scores.append(val)
            truth.append(point_gt(d,p['point_id'][i]));ii=np.flatnonzero(d['point_id']==p['point_id'][i]);cc,nn=np.unique(d['cell'][ii],return_counts=True);cell.append(cc[np.argmax(nn)])
        pc=PolyCollection(verts,array=np.asarray(scores),cmap='viridis',clim=(-1,1),edgecolors='none');axs[0].add_collection(pc);axs[0].autoscale_view();fig.colorbar(pc,ax=axs[0],label='점수')
        order=ids[np.argsort(along[ids])];axs[0].plot(along[order],p['centre'][order,2],c='#d73027',lw=.8,label='사전')
        axs[0].scatter(along[ids],p['centre'][ids,2]+p['mvs_p'][ids]*p['normal'][ids,2],s=6,c='#ff7f00',label='MVS')
        axs[0].scatter(along[ids],p['centre'][ids,2]+np.array(truth)*p['normal'][ids,2],s=5,c='white',edgecolors='black',linewidths=.25,label='참값');axs[0].legend(fontsize=7);axs[0].set_ylabel('높이 (m)')
        for ax,values,colors,label in [(axs[1],p['judgment'][ids,4],COLORS,'사진'),(axs[2],np.array(cell,dtype=int),CELL,'칸')]:
            ax.scatter(along[ids],np.zeros(len(ids)),c=np.array(colors)[values],marker='s',s=30);ax.set_yticks([]);ax.set_ylabel(label,rotation=0,labelpad=15)
        axs[2].set_xlabel('단면 거리 (m)');axs[0].set_title(q['name']+' · '+prior);axs[0].set_xlim(0,L);fig.tight_layout()
        save(fig,D/'figures'/stage/f'section_{q["building"]}_{prior}',dict(section=q,point_ids=p['point_id'][ids],distance_m=along[ids],judgment=p['judgment'][ids,4],cells=cell,gt_display=truth));plt.close(fig)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pilot','full']);ap.add_argument('--only',choices=['all','curves'],default='all');a=ap.parse_args();plt=plotting();cam=Cameras();cfg=load(C/'photocheck_v1.json')
    for prior in ['LoD2','ALS']:
        d,p=join(prior,a.stage)
        if a.only=='all':examples(plt,d,p,prior,a.stage);sections(plt,d,p,prior,a.stage)
        for b in EXAMPLES:
            ids=np.flatnonzero(belongs(p,b)&(p['kind']==1))
            if not len(ids):continue
            sect=[x for x in cfg['sections'] if x['building']==b and x['prior']==prior]
            if not sect:sect=[x for x in cfg['sections'] if x['building']==b]
            if sect:targets=[np.array(sect[0]['a'])*.6+np.array(sect[0]['b'])*.4,np.array(sect[0]['a'])*.4+np.array(sect[0]['b'])*.6]
            else:
                centre=np.average(p['centre'][ids,:2],weights=p['area'][ids],axis=0);targets=[centre+[-1,0],centre+[1,0]]
            used=set()
            for j,target in enumerate(targets):
                choices=ids[np.argsort(np.linalg.norm(p['centre'][ids,:2]-target,axis=1))];i=next(int(k) for k in choices if k not in used);used.add(i)
                curve_figure(plt,cam,d,p,i,D/'figures'/a.stage/f'curve_{b}_{prior}_{j+1}','nearest to locked section 40%/60%, or geometric centre +/-1m; no GT or score selection')
        supplement=load(C/'figure_site_supplement.json')
        for site in supplement['sites']:
            if site['prior']!=prior:continue
            ids=np.flatnonzero(belongs(p,site['building'])&(p['kind']==1)&(p['surf']==site['surface'])&(p['tile']==site['tile']))
            used=set()
            for j,target in enumerate(site['targets_xy_m']):
                choices=ids[np.argsort(np.linalg.norm(p['centre'][ids,:2]-target,axis=1))];i=next(int(k) for k in choices if k not in used);used.add(i)
                curve_figure(plt,cam,d,p,i,D/'figures'/a.stage/f'curve_{site["id"]}_{prior}_{j+1}',site['selection_reason'])
        if a.stage=='full':
            # A point enters the requested patch-defined scope if at least one
            # original roof patch satisfies the frozen difference rule. No GT filter.
            scoped_ids=np.unique(d['point_id'][(d['kind']==1)&d['unexplained']])
            unexplained=np.isin(p['point_id'],scoped_ids)&(p['kind']==1)
            rng=np.random.default_rng(cfg['seed'])
            selections=[]
            for label in range(5):
                ids=np.flatnonzero(unexplained&(p['judgment'][:,4]==label));chosen=rng.choice(ids,size=min(3,len(ids)),replace=False)
                selections.append(dict(judgment=label,eligible_points=len(ids),selected_points=len(chosen),point_ids=p['point_id'][chosen]))
                for j,i in enumerate(chosen):curve_figure(plt,cam,d,p,int(i),D/'figures'/a.stage/f'curve_random_{prior}_{label}_{j+1}','seed 20261026; uniform points with at least one unexplained source roof patch; display judgment group; no GT filter')
            dump(D/'figures'/a.stage/f'random_selection_{prior}.json',dict(seed=cfg['seed'],rows=selections,scope='points with an unexplained source roof patch; no GT filter',source='[이 발주에서 냄]',scientific_verdict=None))
        print('figures complete',a.stage,prior,flush=True)
if __name__=='__main__':main()
