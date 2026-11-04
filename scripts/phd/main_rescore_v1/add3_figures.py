"""Reuse frozen B173 camera/places/colors with primary meshes and FINALTRAIN sigma."""
from common import *
import types,sys,gc,shutil
FT=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1';BASE=Path('/out');SITE='B173nb_b10'
def module():
 source=Path(__file__).with_name('figures.py');text=source.read_text()
 text=text.replace("TG/'r8/targets'/f'{SITE}_{prior}.npz'","FT/'targets'/f'{SITE}__{prior}.npz'")
 text=text.replace("'본 방법 · '+method", "'본 방법 · FINALTRAIN 30,000회'")
 text=text.replace('r8 임시','FINALTRAIN 30,000회').replace('provisional=True','provisional=False')
 text=text.replace("x['cell']==2);ax.set_title(f\"보존이 맞는 영역 전체 완전성", "x['cell']==row['labels_by_prior'][prior]['cell']);ax.set_title(f\"{CELL[row['labels_by_prior'][prior]['cell']]} 영역 전체 완전성")
 text=text.replace('dict(family=family,cell2=m)','dict(family=family,cell=m)')
 m=types.ModuleType('rescore_addendum3_figures');m.__file__=str(source);m.FT=FT;exec(compile(text,str(source),'exec'),m.__dict__)
 original=m.artifact
 def artifact(fig,name,meta):
  rule='original input surfaces; no TSDF' if name=='그림6_2' else '203 training views, TSDF .05/.25 m, top50 and evaluation crop'
  meta.update(mesh_rule=rule,provisional=False,adapter_sha256=sha(__file__),source_sha256=sha(source))
  original(fig,name,meta)
 m.artifact=artifact;return m

def prepare(m,prior,method):
 from geometry import context,MeshScene
 cache=O/'figure_cache'/prior/method;cache.mkdir(parents=True,exist_ok=True);oldkey=f'{SITE}__{prior}__'+('r8_30000' if prior=='ALS' else 'r8_7000');old=BASE/'figure_cache'/prior/oldkey
 frames=json.loads((old/'frames.json').read_text());places=json.loads((C/'representatives_v1.json').read_text())['rows']
 for name in ['prior.npz','mvs.npz','reference.npz','frames.json']:
  dest=cache/name
  if not dest.exists():dest.symlink_to(old/name)
 ctx=context(SITE,prior);gt=ctx['gt'].Gb
 for family in ['fusion','method','baseline_30000']:
  if (cache/(family+'.npz')).exists():continue
  v=m.value(prior,family,method);points=loadz(O/'scores'/v['key']/'points.npz',['scene_distance_m','scene_tau_m']);V,F=m.read_surface(v['mesh']);scene=MeshScene(V,F);f={k:np.asarray(x) if isinstance(x,list) else x for k,x in frames['all'].items()};data=dict(all_gt=m.gt_image(gt,points['scene_distance_m'],points['scene_tau_m'],f),all_result=m.render_mesh(scene,ctx,f,cache/(family+'_all_columns')))
  for row in places:
   f={k:np.asarray(x) if isinstance(x,list) else x for k,x in frames[row['id']].items()};im=m.render_mesh(scene,ctx,f,cache/(family+'_'+row['id']+'_columns'));data[row['id']+'_image']=m.gt_image(gt,points['scene_distance_m'],points['scene_tau_m'],f,im,True);data[row['id']+'_section']=m.section_segments(V,F,row)
  savez(cache/(family+'.npz'),**data);del V,F,scene;gc.collect();print('FIGURE_CACHE',prior,family,flush=True)
 dump(cache/'receipt.json',dict(status='PASS',method=method,prior=prior,unchanged_camera_source=str(old/'frames.json'),frames_sha256=sha(old/'frames.json'),input_cache_reused=True,places_sha256=sha(C/'representatives_v1.json'),scientific_verdict=None))

def inputs(m):
 # Read only existing source surfaces at the four unchanged chapter-6 cuts.
 rows=json.loads((C/'input_sections_v1.json').read_text())['rows'];fig,axes=m.plt.subplots(2,2,figsize=(13,8),layout='constrained');records=[]
 titles=['(가) B173 날개, LoD2','(나) B173 날개, 항공 LiDAR','(다) B0 모임지붕 끝, LoD2','(라) R1 지붕, LoD2']
 for ax,row,title in zip(axes.flat,rows,titles):
  gt=m.SiteGT(row['site']);P=m.section_points(gt.Gb,row);ax.scatter(P[:,0],P[:,1],s=1,c=m.COL['gt'],label='참값',rasterized=True);sources=[];limits=[P[:,1]]
  for family in ['prior','mvs']:
   v=json.loads((BASE/'scores'/f"{row['site']}__{row['prior']}__{family}/values.json").read_text());V,F=m.read_surface(v['mesh']);segments=m.section_segments(V,F,row);del V,F;gc.collect();sources.append(dict(family=family,surface=v['mesh'],surface_sha256=v['mesh_sha256']));limits.append(segments[:,:,1].ravel())
   if family=='prior':ax.add_collection(m.LineCollection(segments,colors=m.COL['prior'],linewidths=1,label='사전 정보'))
   else:points=segments.reshape(-1,2);ax.scatter(points[:,0],points[:,1],s=1,c=m.COL['mvs'],label='영상 깊이',rasterized=True)
  z=np.concatenate([a[np.isfinite(a)] for a in limits]);ax.set(xlim=(0,np.linalg.norm(np.array(row['end'])-row['start'])),ylim=(z.min()-.3,z.max()+.3),xlabel='단면을 따른 거리 (m)',ylabel='높이 (m)',title=title);ax.grid(alpha=.2);records.append(dict(place=row,sources=sources,n_gt=len(P),title=title,height_origin='same local frame; world Z origin 604 m'))
 axes[0,0].legend();m.artifact(fig,'그림6_2',dict(rows=records,legend=['참값','사전 정보','영상 깊이'],xlabel='단면을 따른 거리 (m)',ylabel='높이 (m)',large_title=False,unchanged_geometry=True))

def main(mode,prior='ALS'):
 m=module();method=f'{SITE}__{prior}__FINALTRAIN_30000'
 if mode=='prepare':prepare(m,prior,method)
 elif mode=='draw':m.draw_early(prior,method);m.draw_remaining(prior,method)
 elif mode=='inputs':inputs(m)
 else:raise ValueError(mode)
if __name__=='__main__':main(*sys.argv[1:])
