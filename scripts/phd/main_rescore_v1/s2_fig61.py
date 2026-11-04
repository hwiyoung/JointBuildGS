"""User's four figure-6.1 changes; inherited 0.25m/1m/8-neighbour clustering."""
from common import *
import add3_fig61 as f
import scipy.ndimage as ndi
import types,sys
OLD=Path('/docs/addendum3_stage1/figures/fig6_1_실험지역.json')
CLUSTER_SOURCE=R/'scripts/phd/main_fill_v1/fig61/fig61_notes.py'
def clusters(c):
 ids=np.flatnonzero((c['cell_v2']==2)&(c['kind']==1))
 if not len(ids):return []
 uv=f.xy_to_uv(c['centre'][ids]);lo=uv.min(0);ij=np.floor((uv-lo)/.25).astype(int);img=np.zeros((ij[:,1].max()+1,ij[:,0].max()+1),bool);img[ij[:,1],ij[:,0]]=True
 lab,n=ndi.label(ndi.binary_dilation(img,iterations=4),structure=np.ones((3,3)));groups=lab[ij[:,1],ij[:,0]];rows=[]
 for k in np.unique(groups):
  take=ids[groups==k];m=np.zeros(len(c['area']),bool);m[take]=True;rows.append(dict(mask=m,area=float(c['area'][take].sum()),centre=np.average(c['centre'][take],axis=0,weights=c['area'][take]).tolist(),uv_min=f.xy_to_uv(c['centre'][take]).min(0).tolist(),uv_max=f.xy_to_uv(c['centre'][take]).max(0).tolist()))
 return sorted(rows,key=lambda x:-x['area'])
def inspect():
 und=json.loads((PH/'main_fill_v1/PHD-MAIN-FILL-v1/prep/undecidable/definitions.json').read_text())['cases']['skylight']
 print('SKYLIGHT_DEFINITION',{k:v for k,v in und.items() if k!='units'},flush=True)
 for site,prior in [('B173nb_b10','ALS'),('B173nb_b10','LoD2'),('R1rep_b10','ALS')]:
  c=f.sources(site,prior);rr=clusters(c);print(site,prior,[{k:v for k,v in r.items() if k!='mask'} for r in rr[:8]],flush=True)
def labels():
 rows=json.loads(OLD.read_text())['labels']
 for r in rows:
  if r['text']=='LoD2 정면 20 cm 밖':r['text']='LoD2 정면 바깥';r['revision']='text only; original arrow preserved'
  if r['text']=='날개 3.5~5 m 위':r['text']='날개 3.5~6 m 위';r['revision']='text only; original arrow preserved'
 c=f.sources('B173nb_b10','ALS');cc=clusters(c);chosen=cc[0];prior='ALS';fallback=False
 glass=loadz(PH/'main_uncert_v1/PHD-MAIN-UNCERT-v1/work/places.npz',['glass_strip__ALS'])['glass_strip__ALS'];overlap=chosen['mask']&np.isin(c['source_index'],glass);assert overlap.any(),'Largest ALS cell2 cluster must intersect inherited skylight place'
 if chosen['area']<10:
  prior='LoD2';fallback=True;c=f.sources('B173nb_b10',prior);cc=clusters(c);chosen=cc[0]
 r=f.choose(c,'B173nb_b10',prior,'채광창 깊이 틀림',f.GREEN,2,chosen['mask'],'largest cell2 roof component under inherited figure61 clustering; ALS component intersects inherited skylight strip')
 r.update(fallback_to_LoD2=fallback,cluster_rank=1,cluster_area_m2=chosen['area'],cluster_uv_min=chosen['uv_min'],cluster_uv_max=chosen['uv_max'],clustering=dict(grid_m=.25,dilation_iterations=4,eight_neighbour_components=True,source=str(CLUSTER_SOURCE),source_sha256=sha(CLUSTER_SOURCE)))
 rows=[r if x['text']=='채광창 깊이 틀림' else x for x in rows]
 c=f.sources('R1rep_b10','ALS');chosen=clusters(c)[0];r=f.choose(c,'R1rep_b10','ALS','계단 가장자리 깊이 틀림',f.GREEN,2,chosen['mask'],'largest R1 ALS cell2 roof component under inherited figure61 clustering');r.update(cluster_rank=1,cluster_area_m2=chosen['area'],cluster_uv_min=chosen['uv_min'],cluster_uv_max=chosen['uv_max'],clustering=dict(grid_m=.25,dilation_iterations=4,eight_neighbour_components=True,source=str(CLUSTER_SOURCE),source_sha256=sha(CLUSTER_SOURCE)));rows.append(r)
 return rows
def draw():
 source=Path(f.__file__);text=source.read_text();old="'R1rep_b10':[(.08,.12),(.55,.9)]";assert old in text;text=text.replace(old,"'R1rep_b10':[(.08,.12),(.55,.9),(.95,.40)]")
 m=types.ModuleType('stage2_figure61');m.__file__=__file__;exec(compile(text,str(source),'exec'),m.__dict__);m.labels=labels;m.main()
 p=D/'figures/fig6_1_실험지역.json';v=json.loads(p.read_text());v.update(previous_figure=str(OLD),previous_figure_sha256=sha(OLD),draw_adapter_source=str(source),draw_adapter_source_sha256=sha(source),user_changes=4,gpu_used=False);dump(p,v)
 progress('그림 6.1 이름표 수정: B0 정면·B173 날개 문구만 교체(화살표 유지), B173 ALS 최대 칸2 모임 재선택, R1 ALS 최대 칸2 모임에 계단 가장자리 이름표 추가. 칠하기·빗금·B173만 없음. GPU 없음.')
if __name__=='__main__':draw() if len(sys.argv)>1 and sys.argv[1]=='draw' else inspect()
