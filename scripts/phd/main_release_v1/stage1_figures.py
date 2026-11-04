"""Exactly two places: one section and one two-panel top map for each."""
from common import *
import sys,gc
sys.path.append('/repo/scripts/phd/main_rescore_v1')
import figures as f
import s2_fig61 as places
from scipy.spatial import cKDTree
from matplotlib.collections import LineCollection
from matplotlib.colors import ListedColormap,BoundaryNorm
def choose():
 c=places.f.sources('R1rep_b10','ALS');rows=[]
 source=R/'docs/experiments/phd/main_rescore_v1/addendum3_stage2/figures/fig6_1_실험지역.json';frozen=json.loads(source.read_text());label=next(r for r in frozen['labels'] if r['text']=='계단 가장자리 깊이 틀림')
 for cell in [2,4]:
  cc={**c,'cell_v2':np.where(c['cell_v2']==cell,2,-1)};cluster=places.clusters(cc)[0];ids=np.flatnonzero(cluster['mask']);p=c['centre'][ids,:2];centre=np.array(label['arrow_xyz'][:2]) if cell==2 else np.average(p,axis=0,weights=c['area'][ids]);cov=np.cov(p.T,aweights=c['area'][ids]);_,vec=np.linalg.eigh(cov);direction=vec[:,0]
  if cell==2:assert abs(cluster['area']-label['cluster_area_m2'])<1e-6
  rows.append(dict(cell=cell,name='계단 가장자리' if cell==2 else '칸 4 최대 모임',start=(centre-6*direction).tolist(),end=(centre+6*direction).tolist(),half_width=.25,roi_half_width=3.,cluster_area_m2=cluster['area'],cluster_patch_indices=ids.tolist(),selection='inherited 0.25 m raster, 4 dilations, 8-neighbour roof component; largest by area; section minor PCA axis, 12 m; cell2 uses exact fig6.1 arrow',source=str(source),source_sha256=sha(source)))
 dump(C/'stage1_places.json',dict(rows=rows,GT_used_for_figures_only=True,scientific_verdict=None));return rows
def main(mode='prepare'):
 cfg();p=C/'stage1_places.json';rows=json.loads(p.read_text())['rows'] if p.exists() else choose();root=O/'stage1/R1rep_b10__ALS';cache=root/'sections';cache.mkdir(exist_ok=True)
 families=['prior','mvs','FINALTRAIN_30000','judgment_mesh'] if mode=='prepare' else ['sim_delete_released','sim_pull_released']
 for method in families:
  out=cache/(method+'.npz')
  if out.exists():continue
  path=O/'scores'/('R1rep_b10__ALS__'+method)/'values.json' if method.startswith('sim_') else score_dir('R1rep_b10','ALS',method)/'values.json';v=json.loads(path.read_text());V,F=f.read_surface(v['mesh']);savez(out,**{str(r['cell']):f.section_segments(V,F,r) for r in rows});dump(out.with_suffix('.json'),dict(mesh=v['mesh'],mesh_sha256=v['mesh_sha256'],places_sha256=sha(p),scientific_verdict=None));del V,F;gc.collect()
 if mode=='prepare':return
 data=loadz(root/'rows.npz');g=loadz(root/'gaussians.npz');attr=loadz(root/'attribution.npz');t=loadz(FT/'targets/R1rep_b10__ALS.npz');gt=data['xyz'];tree=cKDTree(gt);own=tree.query(g['xyz'],workers=2)[1];labels=np.full(len(g['xyz']),3,'i1');labels[g['tag']==2]=2;att=g['tag']==1;labels[att]=np.where(g['patch_ids'][g['target_index'][att]]==data['source_index'][own[att]],0,1)
 colors=['#1b9e77','#e6ab02','#d95f02','#7570b3','#999999'];names=['같은 패치','다른 패치','풀림','배경','확인 불가'];methods=['prior','mvs','FINALTRAIN_30000','judgment_mesh','sim_delete_released','sim_pull_released'];mnames=['사전 정보','MVS','V0','판단 조합','모의 가: 풀림 뺌','모의 나: 풀림 당김'];mc=['#a65628','#66a61e','#e41a1c','#377eb8','#984ea3','#000000']
 for row in rows:
  cell=row['cell'];fig,ax=f.plt.subplots(figsize=(14,7));P=f.section_points(gt,row);ax.scatter(P[:,0],P[:,1],c='#bbbbbb',s=4,label='참값',zorder=1);allz=[P[:,1]];sources=[]
  for method,label,col in zip(methods,mnames,mc):
   pp=cache/(method+'.npz');seg=loadz(pp,[str(cell)])[str(cell)];ax.add_collection(LineCollection(seg,colors=col,linewidths=1.2,label=label,zorder=3));allz.append(seg[:,:,1].ravel());sources.append(dict(path=str(pp),sha256=sha(pp)))
  for label,col,k in zip(names,colors,range(5)):
   Q=f.section_points(g['xyz'][labels==k],row);ax.scatter(Q[:,0],Q[:,1],s=7,alpha=.7,color=col,marker='x',label='중심: '+label,zorder=4)
  P=f.section_points(t['target'],row);ax.scatter(P[:,0],P[:,1],s=10,marker='s',facecolors='none',edgecolors='#00bfc4',label='목표',zorder=5)
  a,b=np.array(row['start']),np.array(row['end']);direction=(b-a)/np.linalg.norm(b-a);off=abs((t['target'][:,:2]-a)@np.array([-direction[1],direction[0]]));along=(t['target'][:,:2]-a)@direction;mask=(off<=.25)&(along>=0)&(along<=12)&np.isfinite(t['sigma']);p0=t['target'][mask]-1.96*t['sigma'][mask,None]*t['normal'][mask];p1=t['target'][mask]+1.96*t['sigma'][mask,None]*t['normal'][mask];bands=np.stack([np.c_[(p0[:,:2]-a)@direction,p0[:,2]],np.c_[(p1[:,:2]-a)@direction,p1[:,2]]],axis=1);ax.add_collection(LineCollection(bands,colors='#00bfc4',linewidths=1,alpha=.5,label='목표 ±1.96σ',zorder=2));allz.extend([p0[:,2],p1[:,2]])
  zs=np.concatenate(allz);zs=zs[np.isfinite(zs)];ax.set(xlim=(0,12),ylim=(float(zs.min())-.5,float(zs.max())+.5),xlabel='단면 거리 (m)',ylabel='local Z (m)',title='R1 항공 LiDAR · '+row['name']);ax.grid(alpha=.2);ax.legend(ncol=4,fontsize=9,loc='upper center',bbox_to_anchor=(.5,-.12));fig.tight_layout();save(fig,'cell'+str(cell)+'_section',dict(place=row,sources=sources,source_row_sha256=sha(root/'rows.npz'),y_range=list(ax.get_ylim()),interventions='simulation masks from tags and frozen targets only'))
  low=np.minimum(a,b)-3;high=np.maximum(a,b)+3;sel=((gt[:,:2]>=low)&(gt[:,:2]<=high)).all(1);fig,axs=f.plt.subplots(1,2,figsize=(13,6),sharex=True,sharey=True)
  for ax,codes,cs,ls,title in [(axs[0],data['result_type'],['#1b9e77','#d95f02','#7570b3','#222222'],['τ 안','τ 밖·앞/위','τ 밖·뒤/아래','면 없음'],'결과 종류'),(axs[1],attr['current_binding'],colors,names,'그리는 꼬리표')]:
   for k,(col,label) in enumerate(zip(cs,ls)):
    m=sel&(codes==k);ax.scatter(gt[m,0],gt[m,1],s=4,c=col,label=label)
   ax.plot([a[0],b[0]],[a[1],b[1]],'k--',lw=1);ax.set(xlim=(low[0],high[0]),ylim=(low[1],high[1]),xlabel='local X (m)',ylabel='local Y (m)',title=title);ax.set_aspect('equal');ax.legend(fontsize=8,loc='upper center',bbox_to_anchor=(.5,-.12),ncol=2)
  fig.suptitle('R1 항공 LiDAR · '+row['name']);fig.tight_layout();save(fig,'cell'+str(cell)+'_map',dict(place=row,row_sha256=sha(root/'rows.npz'),attribution_sha256=sha(root/'attribution.npz'),extent=[*low,*high],crs='EPSG:25832 inherited local shift'))
def save(fig,name,meta):
 p=D/'figures/stage1'/name;p.parent.mkdir(parents=True,exist_ok=True);fig.savefig(p.with_suffix('.png'),dpi=200,bbox_inches='tight');f.plt.close(fig);dump(p.with_suffix('.json'),dict(**meta,scientific_verdict=None))
if __name__=='__main__':main(*sys.argv[1:])
