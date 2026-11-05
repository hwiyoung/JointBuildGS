"""One figure script for all six scenes and all diagnostic training arms."""
import sys,gc
import numpy as np
from common import *
from geometry_add1 import inherit,read_surface,section_segments,section_points
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.collections import LineCollection
font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc')
plt.rcParams.update({'font.family':'Noto Sans CJK JP','axes.unicode_minus':False,'font.size':10})
RCFG=json.loads((R/'configs/phd/main_recount_v1/recount_v1.json').read_text())['figures']
COL=RCFG['map_colors'];STAT=RCFG['status_colors']
CASE={0:'둘 다 맞음',1:'영상만 맞음',2:'사전 정보만 맞음',4:'영상 없음',3:'둘 다 틀림',-1:'사전 정보 면 없음'}
JUDGE={0:'일치',1:'보존',2:'보정',4:'결측',3:'보정(빈 공간)',9:'미판정'}
JC={0:COL['0'],1:COL['2'],2:COL['1'],4:COL['4'],3:COL['3'],9:'#dddddd'}
DIST=[('−τ보다 작음','#2166ac'),('−τ~+τ','#ffffff'),('+τ보다 큼','#b2182b'),('면 없음','#999999')]
choose_section=inherit(R/'scripts/phd/main_recount_v1/recount.py',['choose_section'],dict(np=np,cKDTree=cKDTree,coo_matrix=coo_matrix,connected_components=connected_components))['choose_section']

def colors(s,tau):
    out=np.full(len(s),'#ffffff',dtype='U8');out[s < -tau]='#2166ac';out[s>tau]='#b2182b';out[~np.isfinite(s)]='#999999';return out
def legend(ax,items,cols=2):
    ax.legend(handles=[Line2D([],[],marker='s',linestyle='',markeredgecolor='#777777',color=c,label=n,markersize=6) for n,c in items],
        loc='upper center',bbox_to_anchor=(.5,-.17),ncol=cols,fontsize=9,frameon=False)
def save(fig,name,meta,sources):
    p=D/'figures'/name;p.parent.mkdir(parents=True,exist_ok=True);fig.savefig(p.with_suffix('.png'),dpi=300,facecolor='white');plt.close(fig)
    dump(p.with_suffix('.json'),dict(at=now(),**meta,dpi=300,crs='EPSG:25832; inherited local XY [690953,5336071]',
        sources=[dict(path=str(x),sha256=sha(x)) for x in sources],script_sha256=sha(__file__),scientific_verdict=None))
def section(site,prior):
    stem=f'{site}__{prior}';p=O/'scenes'/stem/'section.json'
    if p.exists():return json.loads(p.read_text())
    old=RC/'scenes'/stem/'section.json'
    if old.exists():rec=json.loads(old.read_text());rec.update(reused_source=str(old),reused_sha256=sha(old))
    else:
        z=loadz(O/'scenes'/stem/'rows.npz');rec=choose_section(z['xyz'],z['score_cell_1p0'],RCFG)
        rec.update(small_component=rec.get('component_n_gt',0)<200)
    dump(p,rec);return rec
def selected(P,sec):
    a,b=np.array(sec['start']),np.array(sec['end']);d=(b-a)/np.linalg.norm(b-a);delta=P[:,:2]-a;s=delta@d
    return (s>=0)&(s<=np.linalg.norm(b-a))&(abs(delta[:,0]*d[1]-delta[:,1]*d[0])<=sec['half_width'])
def segments(site,prior,method,sec,tag='main'):
    root=O/'scenes'/f'{site}__{prior}';p=root/'section_cache'/f'{method}_{tag}.npz'
    if not p.exists():
        meta=json.loads((root/'distances'/f'{method}.json').read_text());V,F=read_surface(meta['mesh']);seg=section_segments(V,F,sec);savez(p,segments=seg);del V,F;gc.collect()
    return loadz(p)['segments']
def map_ax(ax,P,c,title,sec=None):
    order=np.argsort(P[:,2],kind='stable');ax.set_facecolor('#eeeeeb');ax.scatter(P[order,0],P[order,1],c=np.asarray(c)[order],s=1.1,linewidths=0,rasterized=True)
    ax.set_aspect('equal');ax.set(xlabel='지역 X (m)',ylabel='지역 Y (m)',title=title)
    if sec and sec['status']=='PASS':
        a,b=np.array(sec['start']),np.array(sec['end']);ax.plot([a[0],b[0]],[a[1],b[1]],'k-',lw=1)
def main(site,prior,stage):
    cfg();stem=f'{site}__{prior}';root=O/'scenes'/stem;row=loadz(root/'rows.npz');P=row['xyz'];tau=row['row_tau_m'];sec=section(site,prior)
    if stage=='2':preservation_samples(site,prior);return
    cell=loadz(root/'stage1_cells.npz');ft=loadz(root/'distances/FINALTRAIN_30000.npz');sources=[root/'rows.npz',root/'stage1_cells.npz',root/'section.json',root/'distances/FINALTRAIN_30000.npz']
    title=f'{site} · {prior} · 정답 판단 진단'
    if stage=='01':
        fig,axes=plt.subplots(1,2,figsize=(14,7.5));fig.subplots_adjust(bottom=.23,top=.87,wspace=.22)
        for ax,k,t in zip(axes,['row_nearest_signed','row_s'],['최근접 거리 · 비교용','법선 측정선 거리']):
            map_ax(ax,P,colors(ft[k],tau),t,sec);legend(ax,DIST)
        fig.suptitle(title);save(fig,stem+'_stage0_distance_maps',dict(stage=0,section=sec),sources)
        fig,axes=plt.subplots(1,3,figsize=(20,7.5));fig.subplots_adjust(bottom=.27,top=.87,wspace=.23)
        maps=[np.array([COL[str(x)] for x in cell['case_id']]),np.array([JC.get(int(x),'#dddddd') for x in cell['judge_gt']]),
              np.where(cell['row_owner']>=0,np.where(cell['judge_gt']==cell['judge_original'],STAT['correct'],STAT['wrong']),STAT['excluded'])]
        titles=['(가) 경우','(나) 정답 판단','(다) 본 방법 판단과 정답 판단']
        items=[[(CASE[k],COL[str(k)]) for k in [0,1,2,4,3,-1]],[(JUDGE[k],JC[k]) for k in [0,1,2,4,3,9]], [('같음',STAT['correct']),('다름',STAT['wrong']),('미소속',STAT['excluded'])]]
        for ax,c,t,it in zip(axes,maps,titles,items):map_ax(ax,P,c,t,sec);legend(ax,it)
        fig.suptitle(title);save(fig,stem+'_stage1_case_judgment_maps',dict(stage=1,case_basis=json.loads((O/'targets_gt'/f'{stem}.json').read_text())['case_basis']),sources)
        fig,axes=plt.subplots(2,1,figsize=(14,8),sharex=True);fig.subplots_adjust(bottom=.17,top=.87,hspace=.35)
        if sec['status']=='PASS':
            take=selected(P,sec);points=section_points(P,sec)
            for ax,k,t in zip(axes,['row_nearest_signed','row_s'],['최근접 · 비교용','법선 측정선']):
                for method,col in [('prior','#D85A30'),('mvs','#1D9E75'),('FINALTRAIN_30000','#4B2E8A')]:
                    ax.add_collection(LineCollection(segments(site,prior,method,sec),colors=col,lw=.8,label=method))
                passed=np.isfinite(ft[k][take])&(abs(ft[k][take])<=tau[take]);ax.scatter(points[:,0],points[:,1],c=np.where(passed,'#222222','#e69f00'),s=5,label='참값: 검정 τ 안 / 주황 τ 밖',zorder=5)
                ax.autoscale_view();ax.set(xlim=(0,sec['length_m']),ylabel='지역 높이 (m)',title=t);ax.grid(alpha=.2)
            axes[-1].set_xlabel('단면 거리 (m)');axes[-1].legend(loc='upper center',bbox_to_anchor=(.5,-.21),ncol=4,frameon=False)
        else:
            for ax in axes:ax.text(.5,.5,sec['reason'],ha='center',transform=ax.transAxes)
        fig.suptitle(title+f" · 단면 {sec.get('component_n_gt',0):,}행"+(' · 200행 미만' if sec.get('component_n_gt',0)<200 else ''))
        save(fig,stem+'_stage0_section',dict(stage=0,section=sec),sources)
    else:
        methods=['FINALTRAIN_30000']+[m for m in ['A1','A2'] if (root/'distances'/f'{m}.npz').exists()]
        dist={m:loadz(root/'distances'/f'{m}.npz') for m in methods};pres=cell['case_id']==2
        sources += [root/'distances'/f'{m}.npz' for m in methods if m!='FINALTRAIN_30000']
        fig,axes=plt.subplots(1,len(methods),figsize=(7*len(methods),7.5),squeeze=False);fig.subplots_adjust(bottom=.23,top=.87)
        for ax,m in zip(axes[0],methods):
            s=dist[m]['row_s'];cc=np.where(np.isfinite(s)&(abs(s)<=tau),STAT['correct'],STAT['wrong']);map_ax(ax,P[pres],cc[pres],m,sec);legend(ax,[('τ 안',STAT['correct']),('τ 밖',STAT['wrong'])])
        fig.suptitle(title+' · 보존 칸');save(fig,stem+'_'+stage+'_preservation_maps',dict(stage=3,methods=methods),sources)
        fig,ax=plt.subplots(figsize=(14,6));fig.subplots_adjust(bottom=.22,top=.85)
        if sec['status']=='PASS':
            for m,c in zip(methods,['#4B2E8A','#009e73','#d55e00']):ax.add_collection(LineCollection(segments(site,prior,m,sec),colors=c,lw=1,label=m))
            pp=section_points(P,sec);ax.scatter(pp[:,0],pp[:,1],s=4,color='black',label='참값');ax.autoscale_view();ax.set(xlim=(0,sec['length_m']),xlabel='단면 거리 (m)',ylabel='지역 높이 (m)');ax.legend(loc='upper center',bbox_to_anchor=(.5,-.15),ncol=4)
        fig.suptitle(title);save(fig,stem+'_'+stage+'_section',dict(stage=3,methods=methods,section=sec),sources)
        multiview(site,prior,stage,methods,sec,sources)
    print('FIGURES_DONE',stem,stage,flush=True)

def multiview(site,prior,stage,methods,sec,sources):
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    if sec['status']!='PASS':return
    stem=f'{site}__{prior}';root=O/'scenes'/stem;ends=np.array([sec['start'],sec['end']]);lo=ends.min(0)-2;hi=ends.max(0)+2
    # Same ROI and exact three cameras for every method. Face colours take the nearest
    # saved 400/m² result-side cylinder sample, without a new scoring population.
    fig=plt.figure(figsize=(6*len(methods),15));zlims=[];axes=[]
    for j,m in enumerate(methods):
        meta=json.loads((root/'distances'/f'{m}.json').read_text());V,F=read_surface(meta['mesh']);mid=V[F].mean(1);keep=((mid[:,:2]>=lo)&(mid[:,:2]<=hi)).all(1);tri=V[F[keep]];del V,F,mid;gc.collect()
        if m=='FINALTRAIN_30000':P=loadz(score_dir(site,prior,m)/'points.npz',['sample_xyz'])['sample_xyz']
        else:P=loadz(root/'distances'/f'{m}_samples.npz',['xyz'])['xyz']
        z=loadz(root/'distances'/f'{m}.npz');ii=cKDTree(P).query(tri.mean(1),workers=4)[1];cc=colors(z['sample_s'][ii],z['sample_tau'][ii]);zlims.extend([float(tri[:,:,2].min()),float(tri[:,:,2].max())])
        for i,(elev,azim) in enumerate([(90,-90),(35,-55),(35,125)]):
            ax=fig.add_subplot(3,len(methods),i*len(methods)+j+1,projection='3d');ax.add_collection3d(Poly3DCollection(tri,facecolors=cc,edgecolors='none',rasterized=True));ax.view_init(elev,azim);ax.set(xlim=(lo[0],hi[0]),ylim=(lo[1],hi[1]),title=m+f' · 시점 {i+1}');axes.append(ax)
        del tri,P,z;gc.collect()
    for ax in axes:ax.set_zlim(min(zlims)-.2,max(zlims)+.2);ax.set_box_aspect((hi[0]-lo[0],hi[1]-lo[1],max(zlims)-min(zlims)+.4))
    fig.suptitle(stem+' · 정답 판단 결과 메시 · 흰색 τ 안 / 파랑 음 / 빨강 양 / 회색 면 없음');fig.subplots_adjust(top=.95,wspace=.15,hspace=.15)
    save(fig,stem+'_'+stage+'_mesh_views',dict(stage=3,methods=methods,section=sec,face_color='nearest saved result-side cylinder sample',camera_angles=[[90,-90],[35,-55],[35,125]]),sources)

def preservation_samples(site,prior):
    from preservation import cameras,full_image
    stem=f'{site}__{prior}';root=O/'scenes'/stem;row=loadz(root/'rows.npz');f=loadz(root/'preservation_features.npz');P=row['xyz'];cam=cameras(site)
    target=loadz(FT/'targets'/f'{stem}.npz',['target','surface_exists']);records=[]
    for feature in ['textureless','edge']:
        ids=np.flatnonzero(f['preservation']&f[feature]);unique,inv,counts=np.unique(P[ids],axis=0,return_inverse=True,return_counts=True)
        if not len(ids):records.append(dict(feature=feature,status='없음',n=0));continue
        pairs=cKDTree(unique).query_pairs(.6,output_type='ndarray');graph=coo_matrix((np.ones(len(pairs),'u1'),(pairs[:,0],pairs[:,1])),shape=(len(unique),len(unique)))
        nc,labels=connected_components(graph,directed=False);sizes=np.bincount(labels,weights=counts)
        for rank,k in enumerate(np.argsort(-sizes,kind='stable')[:2],1):
            selected_ids=ids[labels[inv]==k];part=P[selected_ids];sec=choose_section(part,np.full(len(part),2),RCFG);tag=feature+str(rank)
            # Use the training view nearest to nadir at the anchor; all candidates were
            # already accepted by the same <=20 degree test used for texture.
            center=part.mean(0);anchor=selected_ids[np.argmin(np.linalg.norm(part-center,axis=1))];j=int(f['best_camera'][anchor])
            fig,(ax,secax)=plt.subplots(1,2,figsize=(15,6));fig.subplots_adjust(bottom=.20,top=.85,wspace=.22);imgrec=None
            if j>=0:
                im,imgrec=full_image(cam,j);uv,_,guard=cam.project(part,j);inside=guard&(uv[:,0]>=0)&(uv[:,0]<cam.w)&(uv[:,1]>=0)&(uv[:,1]<cam.h)
                uv=uv[inside]
                if len(uv):
                    lo=np.maximum(np.floor(uv.min(0)-60).astype(int),0);hi=np.minimum(np.ceil(uv.max(0)+60).astype(int),[cam.w,cam.h]);ax.imshow(im);ax.scatter(uv[:,0],uv[:,1],s=3,c='#d55e00',linewidths=0);ax.set(xlim=(lo[0],hi[0]),ylim=(hi[1],lo[1]),title=cam.names[j]+' · 보존 칸 참값');ax.axis('off')
            else:ax.text(.5,.5,'수직에 가까운 학습 영상 없음',ha='center',transform=ax.transAxes);ax.axis('off')
            for m,c in [('prior','#D85A30'),('mvs','#1D9E75'),('FINALTRAIN_30000','#4B2E8A')]:secax.add_collection(LineCollection(segments(site,prior,m,sec,tag),colors=c,lw=1,label=m))
            for pts,c,mark,label in [(P,'black','.','참값'),(target['target'][target['surface_exists']],'#CC79A7','x','FINALTRAIN 목표')]:
                pp=section_points(pts,sec);secax.scatter(pp[:,0],pp[:,1],c=c,s=6,marker=mark,label=label)
            secax.autoscale_view();secax.set(xlim=(0,sec['length_m']),xlabel='단면 거리 (m)',ylabel='지역 높이 (m)');secax.legend(loc='upper center',bbox_to_anchor=(.5,-.17),ncol=3,fontsize=8,frameon=False)
            name=stem+'_stage2_'+tag;meta=dict(stage=2,site=site,prior=prior,feature=feature,rank=rank,n_gt=len(part),section=sec,image=imgrec,view_name=cam.names[j] if j>=0 else None)
            fig.suptitle(stem+f' · {feature} {rank} · {len(part):,}행');save(fig,name,meta,[root/'rows.npz',root/'preservation_features.npz',FT/'targets'/f'{stem}.npz']);records.append(meta)
    dump(root/'preservation_samples.json',dict(records=records,scientific_verdict=None));print('PRESERVATION_SAMPLES_DONE',stem,len(records),flush=True)
if __name__=='__main__':main(*sys.argv[1:])
