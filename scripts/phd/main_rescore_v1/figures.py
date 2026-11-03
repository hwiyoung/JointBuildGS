"""All RESCORE scientific figures; replace method keys after FINALTRAIN.
Images use actual triangle intersections and inherited GT distances. Tables always
refer to the whole correct-cell region, never just a representative crop.
"""
import sys,gc,argparse
from common import *
from geometry import context,MeshScene,columns,patch_basis,SiteGT
from surface_tau import by_wall
from scipy.spatial import cKDTree
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.collections import LineCollection,PolyCollection
from matplotlib.lines import Line2D
font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc');plt.rcParams.update({'font.family':'Noto Sans CJK JP','axes.unicode_minus':False,'font.size':10,'savefig.dpi':300})
COL=dict(mvs='#1D9E75',prior='#D85A30',within='#CFCDC4',uncovered='#2457B0',outlier='#C2187A',method='#4B2E8A',fusion='#B9A5E0',gt='#000000')
CELL={0:'일치가 맞는 곳',1:'보정이 맞는 곳',2:'보존이 맞는 곳',3:'두 자료가 모두 틀린 곳',4:'결측이 맞는 곳'}
SITE='B173nb_b10'

def color(code):return np.array(matplotlib.colors.to_rgb(COL[code]))
def key(prior,family,method):return method if family=='method' else f'{SITE}__{prior}__{family}'
def value(prior,family,method):return json.loads((O/'scores'/key(prior,family,method)/'values.json').read_text())
def read_surface(p):
 import open3d as o3d
 p=Path(p)
 if p.suffix=='.npz':z=loadz(p,['V','F']);return z['V'].astype(float),z['F']
 m=o3d.io.read_triangle_mesh(str(p));return np.asarray(m.vertices).copy(),np.asarray(m.triangles).copy()
def frame(box,W=900,H=650):
 # azimuth -60, elevation 35, orthographic. Bounds fixed from input scope.
 az,el=np.deg2rad([-60,35]);out=np.array([np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)]);forward=-out;right=np.cross(forward,[0,0,1.]);right/=np.linalg.norm(right);up=np.cross(right,forward);basis=np.stack([right,up,forward]);center=(box[0]+box[1])/2;corners=np.array(np.meshgrid(*zip(box[0],box[1]))).T.reshape(-1,3);uv=(corners-center)@basis[:2].T;span=uv.max(0)-uv.min(0);width=max(span[0],span[1]*W/H)*1.05;height=width*H/W;origin=center-100*forward
 return dict(basis=basis,center=center,origin=origin,width=width,height=height,W=W,H=H)
def project(P,f):
 q=(P-f['center'])@f['basis'].T;u=(q[:,0]/f['width']+.5)*f['W'];v=(.5-q[:,1]/f['height'])*f['H'];return np.c_[u,v,q[:,2]]
def gt_image(P,dist,tau,f,background=None,only_missing=False):
 im=np.ones((f['H'],f['W'],3)) if background is None else background.copy();q=project(P,f);ix=np.floor(q[:,0]).astype(int);iy=np.floor(q[:,1]).astype(int);good=(ix>=0)&(ix<f['W'])&(iy>=0)&(iy<f['H']);good&=(dist>tau) if only_missing else True;ids=np.flatnonzero(good);order=np.argsort(q[ids,2],kind='stable');ids=ids[order];pixel=iy[ids]*f['W']+ix[ids];_,first=np.unique(pixel,return_index=True);ids=ids[first];rgb=np.where((dist[ids]<=tau[ids])[:,None],color('within'),color('uncovered'));im[iy[ids],ix[ids]]=rgb;return im

def render_mesh(scene,ctx,f,folder):
 W,H=f['W'],f['H'];yy,xx=np.meshgrid(np.arange(H),np.arange(W),indexing='ij');u=((xx+.5)/W-.5)*f['width'];v=(.5-(yy+.5)/H)*f['height'];orig=f['origin']+u[...,None]*f['basis'][0]+v[...,None]*f['basis'][1];dist=scene.cast(orig.reshape(-1,3),f['basis'][2]);ok=np.isfinite(dist);P=orig.reshape(-1,3)[ok]+dist[ok,None]*f['basis'][2];_,nd,lat,near=ctx['ref'].query(P);tau=by_wall(ctx,ctx['gt'].G['vert_gt_points'][ctx['gt'].bs_idx][near].astype(bool));rgb=np.where((nd<=tau)[:,None],color('within'),color('outlier'));rgb[~np.isfinite(nd)|(lat>.5)|~ctx['gt'].in_cells(P)]=1.;im=np.ones((H*W,3));im[ok]=rgb;return im.reshape(H,W,3)
def section_segments(V,F,row):
 a,b=np.array(row['start']),np.array(row['end']);direction=(b-a)/np.linalg.norm(b-a);side=np.array([-direction[1],direction[0]]);length=np.linalg.norm(b-a);segments=[]
 for start in range(0,len(F),500000):
  tri=V[F[start:start+500000]];off=(tri[:,:,:2]-a)@side;hit=(off.min(1)<=0)&(off.max(1)>=0);tri=tri[hit];off=off[hit]
  if not len(tri):continue
  coords=np.full((len(tri),3,2),np.nan);valid=np.zeros((len(tri),3),bool)
  for edge in range(3):
   j=(edge+1)%3;mask=(off[:,edge]*off[:,j]<=0)&(off[:,edge]!=off[:,j]);t=np.zeros(len(tri));t[mask]=off[mask,edge]/(off[mask,edge]-off[mask,j]);p=tri[:,edge]+t[:,None]*(tri[:,j]-tri[:,edge]);coords[:,edge]=np.c_[(p[:,:2]-a)@direction,p[:,2]];valid[:,edge]=mask
  for e,j in [(0,1),(0,2),(1,2)]:
   mask=valid[:,e]&valid[:,j];s=np.stack([coords[mask,e],coords[mask,j]],1);keep=(s[:,:,0].max(1)>=0)&(s[:,:,0].min(1)<=length);segments.append(s[keep])
 return np.concatenate(segments) if segments else np.empty((0,2,2))
def section_points(P,row):
 a,b=np.array(row['start']),np.array(row['end']);d=(b-a)/np.linalg.norm(b-a);delta=P[:,:2]-a;s=delta@d;off=abs(delta[:,0]*d[1]-delta[:,1]*d[0]);take=(s>=0)&(s<=np.linalg.norm(b-a))&(off<=row['half_width']);return np.c_[s[take],P[take,2]]
def roi_box(row,gt):
 a,b=np.array(row['start']),np.array(row['end']);xy=np.array([np.minimum(a,b)-row['roi_half_width'],np.maximum(a,b)+row['roi_half_width']]);sel=((gt[:,:2]>=xy[0])&(gt[:,:2]<=xy[1])).all(1);z=gt[sel,2];return np.array([[*xy[0],float(np.percentile(z,5)-1)],[*xy[1],float(np.percentile(z,99)+(6 if row['id']=='A' else 1.5))]])
def serial_frame(f):return {k:v.tolist() if isinstance(v,np.ndarray) else v for k,v in f.items()}
def artifact(fig,name,meta):
 path=D/'figures';path.mkdir(exist_ok=True);fig.savefig(path/(name+'.png'),dpi=300,facecolor='white');plt.close(fig);dump(path/(name+'.json'),dict(meta,colors=COL,dpi=300,source_tag='[이 발주에서 냄]',scientific_verdict=None))
def prepare(prior,method):
 cfg();start=time.monotonic();ctx=context(SITE,prior);gt=ctx['gt'].Gb;places=json.loads((C/'representatives_v1.json').read_text())['rows'];box=np.array(json.loads((O/'meshes/B173nb_b10__ALS__r8_30000/final_work/inputs/meta.json').read_text())['box']);frames={'all':frame(box)};frames.update({r['id']:frame(roi_box(r,gt),650,500) for r in places});cache=O/'figure_cache'/prior/method;cache.mkdir(parents=True,exist_ok=True);dump(cache/'frames.json',{k:serial_frame(v) for k,v in frames.items()})
 for family in ['prior','mvs','fusion','method','baseline_30000']:
  v=value(prior,family,method);points=loadz(O/'scores'/key(prior,family,method)/'points.npz',['scene_distance_m','scene_tau_m']);V,F=read_surface(v['mesh']);scene=MeshScene(V,F);data={};data['all_gt']=gt_image(gt,points['scene_distance_m'],points['scene_tau_m'],frames['all']);data['all_result']=render_mesh(scene,ctx,frames['all'],cache/(family+'_all_columns'))
  for row in places:
   im=render_mesh(scene,ctx,frames[row['id']],cache/(family+'_'+row['id']+'_columns'));data[row['id']+'_image']=gt_image(gt,points['scene_distance_m'],points['scene_tau_m'],frames[row['id']],im,True);data[row['id']+'_section']=section_segments(V,F,row)
  savez(cache/(family+'.npz'),**data);del V,F,scene;gc.collect();print('FIGURE_CACHE',prior,family,flush=True)
 savez(cache/'reference.npz',**{r['id']+'_gt':section_points(gt,r) for r in places});dump(cache/'receipt.json',dict(status='PASS',method=method,prior=prior,places_sha256=sha(C/'representatives_v1.json'),source_sha256=sha(__file__),seconds=time.monotonic()-start,scientific_verdict=None));timing('figure_prepare_'+prior+'_'+method,start)

def draw_early(prior,method):
 places=json.loads((C/'representatives_v1.json').read_text())['rows'];cache=O/'figure_cache'/prior/method;frames=json.loads((cache/'frames.json').read_text());data={f:loadz(cache/(f+'.npz')) for f in ['prior','mvs','fusion','method']};ref=loadz(cache/'reference.npz');provisional='r8_' in method;method_label='본 방법 · r8 임시' if provisional else '본 방법 · '+method;names=['사전 정보','MVS','결합',method_label];families=list(data);records=[]
 # Crop only blank display margins; the frozen orthographic camera is unchanged.
 occupied=np.any(data['prior']['all_gt']<.999,axis=2);yy,xx=np.nonzero(occupied);display=[max(0,int(xx.min())-50),min(occupied.shape[1],int(xx.max())+51),max(0,int(yy.min())-50),min(occupied.shape[0],int(yy.max())+51)]
 fig,axes=plt.subplots(2,4,figsize=(17,7.5),layout='constrained')
 for j,family in enumerate(families):
  v=value(prior,family,method);records.append(v);f={k:np.array(x) if isinstance(x,list) else x for k,x in frames['all'].items()}
  for i,k in enumerate(['all_gt','all_result']):
   ax=axes[i,j];ax.imshow(data[family][k]);ax.set_xlim(display[:2]);ax.set_ylim(display[3],display[2]);ax.axis('off');ax.set_title(names[j]+' · '+('참값의 완전성' if i==0 else '결과의 정확성'))
   for row in places:
    q=project(np.c_[[row['start'],row['end']],[row.get('anchor_xyz',[0,0,-26.398806341042654])[2]]*2],f);low=q[:,:2].min(0)-10;high=q[:,:2].max(0)+10;ax.add_patch(plt.Rectangle(low,*(high-low),fill=False,edgecolor='black',linewidth=.8));ax.annotate(row['id'],xy=(low+high)/2,xytext={'A':(22,-26),'B':(-25,23),'C':(-14,20)}[row['id']],textcoords='offset points',fontsize=10,fontweight='bold',ha='center',bbox=dict(facecolor='white',edgecolor='none',alpha=.9),arrowprops=dict(arrowstyle='-',color='black',linewidth=.6))
   ax.text(.5,-.035,('완전성' if i==0 else '정확성')+f" {100*v['scene']['completeness' if i==0 else 'accuracy']:.2f}%",transform=ax.transAxes,ha='center',va='top')
 fig.suptitle(f'그림 7.3 · {prior} · 장면 전체의 완전성과 정확성\n회색: τ 안   파랑: 덮지 못한 참값   자주: τ 밖 결과',fontsize=15);artifact(fig,f'그림7_3_{prior}',dict(title='장면 전체의 완전성과 정확성',method=method,provisional=provisional,views=frames['all'],display_crop_px=display,places=places,table='b173_table3',source_scores=[r['key'] for r in records],surface_color_rule='actual orthographic triangle hits; same reference normal distance, lateral eligibility, new tau/columns as scorer'))
 fig,axes=plt.subplots(3,5,figsize=(21,12),layout='constrained')
 meta=[]
 for i,row in enumerate(places):
  cell=row['labels_by_prior'][prior]['cell'];metrics=[]
  for j,family in enumerate(families):
   ax=axes[i,j];ax.imshow(data[family][row['id']+'_image']);ax.axis('off');v=value(prior,family,method);m=next(r for r in v['cells'] if r['cell']==cell);metric='gt_mean_m' if row['id']=='C' else 'completeness';val=m[metric]*100 if m[metric] is not None else None;label='참값 거리' if row['id']=='C' else '완전성';unit='cm' if row['id']=='C' else '%';ax.set_title(names[j] if i==0 else '');ax.text(.5,-.035,f"영역 전체 {label} {val:.2f}{unit}" if val is not None else '확인 불가',transform=ax.transAxes,ha='center',va='top',fontsize=10,bbox=dict(facecolor='white',edgecolor='none',pad=1.5));metrics.append(dict(family=family,cell=cell,metric=metric,value=m[metric],n_gt=m['n_gt']))
   if j==0:ax.text(-.02,.5,f"{row['id']} {row['name']}\n{CELL[cell]}",transform=ax.transAxes,rotation=90,va='center',ha='right',fontsize=11)
  ax=axes[i,4];P=ref[row['id']+'_gt'];ax.scatter(P[:,0],P[:,1],s=.3,c=COL['gt'],rasterized=True,label='참값')
  for family in families:
   segments=data[family][row['id']+'_section']
   if family=='mvs':
    pp=segments.reshape(-1,2);ax.scatter(pp[:,0],pp[:,1],s=.4,c=COL['mvs'],rasterized=True,label='MVS')
   else:ax.add_collection(LineCollection(segments,colors=COL[family],linewidths=.6,linestyles='dashed' if family=='fusion' else 'solid',label=names[families.index(family)]))
  ax.set_xlim(0,np.linalg.norm(np.array(row['end'])-row['start']));box=roi_box(row,np.c_[np.zeros((len(P),2)),P[:,1]]) if False else None
  if len(P):ax.set_ylim(np.percentile(P[:,1],5)-1,np.percentile(P[:,1],99)+(6 if row['id']=='A' else 1.5))
  ax.set_xlabel('단면 거리 (m)');ax.set_ylabel('지역 원점 기준 높이 (m)');ax.grid(alpha=.2);meta.append(dict(place=row,metrics_entire_cell=metrics))
 axes[0,4].legend(fontsize=8,loc='best');fig.suptitle(f'그림 7.5 · {prior} · 같은 대표 자리의 면과 단면 — {method_label}',fontsize=16);artifact(fig,f'그림7_5_{prior}',dict(title='대표 자리의 확대 메시와 단면',method=method,provisional=provisional,places=meta,views=frames,table='b173_table4',note='Values beneath images are the entire correct-cell region; blue overlays are uncovered GT. Sections are exact triangle-plane intersections.'))

def draw_remaining(prior,method):
 # Figures 7.4, 7.6, 7.7 share the completed score and early-figure caches.
 places=json.loads((C/'representatives_v1.json').read_text())['rows'];cache=O/'figure_cache'/prior/method
 fig,ax=plt.subplots(figsize=(10,7),layout='constrained');rows=[];labels=dict(prior='사전 정보',mvs='MVS',fusion='결합',baseline_30000='기준선',GeoGS_30000='GeoGS',**{'2DGS_30000':'2DGS'},CDGS_30000='CDGS',judgment_mesh='판단 조합',oracle='상한',method='본 방법 · r8 임시');markers=dict(baseline_30000='s',GeoGS_30000='^',**{'2DGS_30000':'v'},CDGS_30000='D',judgment_mesh='P',oracle='*')
 for family in ['prior','mvs','fusion','baseline_30000','GeoGS_30000','2DGS_30000','CDGS_30000','judgment_mesh','oracle','method']:
  v=value(prior,family,method);a=next(x for x in v['cells'] if x['cell']==1);b=next(x for x in v['cells'] if x['cell']==2);x,y=a['completeness']*100,b['completeness']*100;rows.append(dict(key=v['key'],cell1=x,cell2=y));c=COL.get(family,'#555555');ax.scatter(x,y,s=65,marker=markers.get(family,'o'),facecolors='none' if family in ['prior','mvs'] else c,edgecolors=c,label=labels[family])
 ax.legend(loc='upper left',bbox_to_anchor=(1.01,1),fontsize=9)
 ax.set(xlabel='보정이 맞는 곳의 완전성 (%)',ylabel='보존이 맞는 곳의 완전성 (%)',xlim=(0,103),ylim=(0,103),title=f'그림 7.4 · {prior} · 두 자료가 각각 틀린 곳');ax.grid(alpha=.2);artifact(fig,f'그림7_4_{prior}',dict(title='두 자료가 각각 틀린 곳의 완전성',method=method,rows=rows,provisional=True))
 row=next(r for r in places if r['id']=='B');ref=loadz(cache/'reference.npz');data={f:loadz(cache/(f+'.npz')) for f in ['prior','mvs','baseline_30000','method']};fig,axes=plt.subplots(2,2,figsize=(11,9),layout='constrained');meta=[]
 for j,family in enumerate(['baseline_30000','method']):
  axes[0,j].imshow(data[family]['B_image']);axes[0,j].axis('off');axes[0,j].set_title('기준선' if j==0 else '본 방법 · r8 임시');ax=axes[1,j];P=ref['B_gt'];ax.scatter(P[:,0],P[:,1],c='black',s=.3,rasterized=True)
  for f in ['prior','mvs',family]:ax.add_collection(LineCollection(data[f]['B_section'],colors=COL.get(f,'#555555'),linewidths=.7))
  ax.set(xlim=(0,10),ylim=(np.percentile(P[:,1],5)-1,np.percentile(P[:,1],99)+(6 if row['id']=='A' else 1.5)),xlabel='단면 거리 (m)',ylabel='지역 원점 기준 높이 (m)');m=next(x for x in value(prior,family,method)['cells'] if x['cell']==2);ax.set_title(f"보존이 맞는 영역 전체 완전성 {m['completeness']*100:.2f}%");meta.append(dict(family=family,cell2=m))
 artifact(fig,f'그림7_6_{prior}',dict(title='판단 빼기',method=method,place=row,rows=meta,provisional=True))
 ctx=context(SITE,prior);core=ctx['core'];old=loadz(TG/'r8/targets'/f'{SITE}_{prior}.npz',['sigma']);sigma=old['sigma'][core['source_index']];points=loadz(O/'scores'/method/'points.npz',['row_owner','row_distance_m']);own=points['row_owner'];dist=points['row_distance_m'];median=np.full(len(sigma),np.nan);valid=own>=0;order=np.argsort(own[valid]);o=own[valid][order];d=dist[valid][order];ids,begin=np.unique(o,return_index=True)
 for k,a,b in zip(ids,begin,np.r_[begin[1:],len(o)]):median[k]=np.median(d[a:b])
 limit=float(np.nanmax(np.r_[sigma,median]));fig,axes=plt.subplots(1,2,figsize=(13,6),layout='constrained')
 a,b,n=patch_basis(core);c=core['centre'];a=a*.125;b=b*.125;polygons=np.stack([c-a-b,c+a-b,c+a+b,c-a+b],axis=1)[:,:,:2]
 for ax,values,title in zip(axes,[sigma,median],['목표 σ','참값→결과 거리 중앙값']):
  ok=(core['kind']==1)&np.isfinite(values);im=PolyCollection(polygons[ok],array=values[ok],cmap='viridis',edgecolors='none',rasterized=True);im.set_clim(0,limit);ax.add_collection(im);ax.autoscale_view();ax.set_aspect('equal');ax.set(title=title,xlabel='동쪽 (m)',ylabel='북쪽 (m)')
 fig.colorbar(im,ax=axes,label='m');fig.suptitle(f'그림 7.7 · {prior} · 목표 정밀도와 결과 오차 · r8 임시');artifact(fig,f'그림7_7_{prior}',dict(title='정밀도 지도와 오차 지도',method=method,range_m=[0,limit],sigma_source=str(TG/'r8/targets'/f'{SITE}_{prior}.npz')+':sigma',distance_source=str(O/'scores'/method/'points.npz')+':row_distance_m',provisional=True))

def draw_diagnostic(scorekey):
 site,prior,_=scorekey.split('__');j=next(x for x in json.loads((O/'diagnostics'/f'{site}_jobs.json').read_text())['jobs'] if x['key']==scorekey);views=json.loads((O/'views'/f'{site}.json').read_text())['views'];train=[v for v in views if not v['virtual']];v=train[len(train)//2];gt=SiteGT(site);P=gt.Gb;E=np.array(v['W2C']);K=np.array(v['K']);q=P@E[:3,:3].T+E[:3,3];good=q[:,2]>0;u=np.rint(q[:,0]/np.maximum(q[:,2],1e-10)*K[0,0]+K[0,2]).astype(int);y=np.rint(q[:,1]/np.maximum(q[:,2],1e-10)*K[1,1]+K[1,2]).astype(int);W,H=v['width'],v['height'];good&=(u>=0)&(u<W)&(y>=0)&(y<H);depth=np.full(H*W,np.inf);np.minimum.at(depth,y[good]*W+u[good],q[good,2]);depth=depth.reshape(H,W);depth[~np.isfinite(depth)]=np.nan;source=O/'renders'/j['render_key']/f"{v['index']:04d}.npz";render=loadz(source,['depth'])['depth'].astype(float);render[render<=0]=np.nan;finite=np.r_[depth[np.isfinite(depth)],render[np.isfinite(render)]];lo,hi=float(finite.min()),float(finite.max());fig,axes=plt.subplots(1,2,figsize=(12,6),layout='constrained')
 for ax,values,label in zip(axes,[render,depth],['렌더 깊이','참값 점의 최근접 깊이']):im=ax.imshow(values,vmin=lo,vmax=hi,cmap='viridis');ax.set_title(label);ax.axis('off')
 fig.colorbar(im,ax=axes,label='카메라 깊이 (m)');fig.suptitle(f'{scorekey} · 대표 학습 시점 {v["name"]}');artifact(fig,'깊이점검_'+scorekey,dict(title='대표 시점의 렌더 깊이와 참값 깊이',key=scorekey,view=v,view_selection='middle camera in frozen ordered training list; independent of method result',reference='cleaned GT points projected with z-buffer; empty pixels remain empty; no interpolation',render_source=str(source),render_sha256=sha(source),depth_range_m=[lo,hi]))

def draw_inputs():
 rows=json.loads((C/'input_sections_v1.json').read_text())['rows'];fig,axes=plt.subplots(2,2,figsize=(13,8),layout='constrained');records=[]
 for ax,row in zip(axes.flat,rows):
  site,prior=row['site'],row['prior'];gt=SiteGT(site);P=section_points(gt.Gb,row);ax.scatter(P[:,0],P[:,1],s=1,c=COL['gt'],label='참값',rasterized=True);sources=[];limits=[P[:,1]]
  for family in ['prior','mvs']:
   v=json.loads((O/'scores'/f'{site}__{prior}__{family}/values.json').read_text());V,F=read_surface(v['mesh']);segments=section_segments(V,F,row);del V,F;gc.collect();sources.append(dict(family=family,surface=v['mesh'],surface_sha256=v['mesh_sha256']));limits.append(segments[:,:,1].ravel())
   if family=='prior':ax.add_collection(LineCollection(segments,colors=COL['prior'],linewidths=1,label='사전 정보'))
   else:points=segments.reshape(-1,2);ax.scatter(points[:,0],points[:,1],s=1,c=COL['mvs'],label='MVS',rasterized=True)
  z=np.concatenate([a[np.isfinite(a)] for a in limits]);ax.set(xlim=(0,np.linalg.norm(np.array(row['end'])-row['start'])),ylim=(z.min()-.3,z.max()+.3),xlabel='단면 거리 (m)',ylabel='지역 원점 기준 높이 (m)',title=row['title']);ax.grid(alpha=.2);records.append(dict(place=row,sources=sources,n_gt=len(P),height_origin='same local frame as frozen inputs; world Z origin 604 m'))
 axes[0,0].legend();fig.suptitle('그림 6.2 · 사전 정보와 현재 관측의 단면',fontsize=15);artifact(fig,'그림6_2',dict(title='사전 정보가 실제와 다른 모양',rows=records,learned_results_used=False,section_source=str(C/'input_sections_v1.json'),section_source_sha256=sha(C/'input_sections_v1.json')))

def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','early','remaining','diagnostic','inputs']);p.add_argument('--key');p.add_argument('--prior',choices=['ALS','LoD2']);p.add_argument('--method-als',default='B173nb_b10__ALS__r8_30000');p.add_argument('--method-lod2',default='B173nb_b10__LoD2__r8_7000');a=p.parse_args();cfg()
 if a.mode=='diagnostic':draw_diagnostic(a.key);return
 if a.mode=='inputs':draw_inputs();return
 for prior in ([a.prior] if a.prior else ['ALS','LoD2']):
  method=a.method_als if prior=='ALS' else a.method_lod2
  {'prepare':prepare,'early':draw_early,'remaining':draw_remaining}[a.mode](prior,method)
if __name__=='__main__':main()
