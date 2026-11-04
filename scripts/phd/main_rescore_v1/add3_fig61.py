"""Chapter 6.1: three regions, boundaries and name arrows only; frozen cells_v2.
Drawing primitives adapted from main_fill_v1/fig61/fig61_draw.py; no painted classes.
"""
from common import *
import ast,sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager,patheffects as pe
from matplotlib.lines import Line2D
font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc');plt.rcParams.update({'font.family':'Noto Sans CJK JP','axes.unicode_minus':False})
SOURCE=R/'scripts/phd/main_fill_v1/fig61/fig61_draw.py';A_DEG=json.loads((R/'configs/phd/main_prep_measure_v1/prep_v5.json').read_text())['frame']['u_axis_angle_degrees_ccw_from_easting']
tree=ast.parse(SOURCE.read_text());nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['basis','xy_to_uv','north','scalebar','rect_uv']];exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),'exec'),globals())
PREP=PH/'main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1';DR=PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1';CH6=PH/'ch6_support_v1/PHD-CH6-SUPPORT-v1';BOX=json.loads((PREP/'step06/boxes_v1.json').read_text())['boxes'];RANGES=json.loads((PREP/'step01/ranges.json').read_text());NAMES={'B0_b10':'B0','B173nb_b10':'B173 주변','R1rep_b10':'R1'};BID={'B0_b10':'B0','B173nb_b10':'B173nb','R1rep_b10':'R1rep'};ORANGE='#D85A30';GREEN='#1D9E75';HALO=[pe.withStroke(linewidth=3,foreground='white')]

def sources(site,prior='LoD2'):
 c=loadz(JA/'core_points'/f'{site}__{prior}.npz',['patch_id','source_index','centre','area','kind','prior_height_m','gt_p']);v=loadz(CELLS/f'{site}__{prior}.npz',['patch_id','cell_v2']);assert np.array_equal(c['patch_id'],v['patch_id']);c.update(v)
 if prior=='LoD2':
  u=loadz(S0/'s61/box'/site/'LoD2/units.npz',['loc_surface','surf_ext']);c['ext']=u['surf_ext'][u['loc_surface'][c['source_index']]];tab=json.loads((DR/'s02_box'/site/'lod2_surfaces.json').read_text())['surfaces'];c['faces']={int(x['ext']):x for x in tab}
 return c

def face_mask(c,ids):return np.isin(c['ext'],[e for e,r in c['faces'].items() if r['gml'] in ids])
def largest_face(c,m):
 if not m.any():return m
 ex=np.unique(c['ext'][m]);areas=np.array([c['area'][m&(c['ext']==x)].sum() for x in ex]);return m&(c['ext']==ex[np.argmax(areas)])
def choose(c,site,prior,text,color,cell,place,place_source,anchor=None):
 m=place&(c['cell_v2']==cell);area=float(c['area'][m].sum());r=dict(site=site,prior=prior,text=text,color=color,cell=cell,patches=int(m.sum()),selected_cell_area_m2=area,whole_region_cell_area_m2=float(c['area'][c['cell_v2']==cell].sum()),selection_source=place_source,cells_sha256=sha(CELLS/f'{site}__{prior}.npz'),visible=area>=10.,reason=None)
 if area<10.:r['reason']='해당 자리의 새 칸 없음' if not m.any() else '해당 자리의 새 칸 넓이 10 m² 미만';return r
 ids=np.flatnonzero(m);p=c['centre'][ids];centre=np.average(p,axis=0,weights=c['area'][ids]) if anchor is None else np.asarray(anchor);pick=ids[np.argmin(np.linalg.norm(p-centre,axis=1))];r.update(arrow_xyz=c['centre'][pick].tolist(),arrow_uv=xy_to_uv(c['centre'][[pick]])[0].tolist(),arrow_patch_id=str(c['patch_id'][pick]),arrow_source_index=int(c['source_index'][pick]));return r

def labels():
 rows=[];sites=json.loads((R/'configs/phd/main_prep_discard_rule_v1/sites_v1.json').read_text())['sites'];named={r['id']:r for r in sites};site='B0_b10';c=sources(site);front=face_mask(c,named['B0_facade']['faces_gml']);rows.append(choose(c,site,'LoD2','LoD2 정면 20 cm 밖',ORANGE,1,front,'sites_v1 B0_facade exact GML'))
 old=json.loads((PH/'main_fill_v1/PHD-MAIN-FILL-v1/work/fig61/notes.json').read_text());cl=max(old['B0_wrong']['clusters'],key=lambda r:r['area_m2']);uv=xy_to_uv(c['centre']);roof=(c['kind']==1)&(uv[:,0]>=cl['u_range'][0])&(uv[:,0]<=cl['u_range'][1])&(uv[:,1]>=cl['v_range'][0])&(uv[:,1]<=cl['v_range'][1]);rows.append(choose(c,site,'LoD2','LoD2 지붕 끝 높음',ORANGE,1,roof,'existing B0_wrong largest cluster rectangle, unchanged'));rows.append(choose(c,site,'LoD2','창 깊이 없음',GREEN,4,front,'sites_v1 B0_facade exact GML'))
 site='B173nb_b10';c=sources(site);wing=face_mask(c,named['B173_wings']['faces_gml']);rows.append(choose(c,site,'LoD2','날개 3.5~5 m 위',ORANGE,1,wing,'sites_v1 B173_wings exact GML',anchor=[141.655,97.83,-26.4]))
 ca=sources(site,'ALS');places=loadz(PH/'main_uncert_v1/PHD-MAIN-UNCERT-v1/work/places.npz',['glass_strip__ALS']);glass=np.isin(ca['source_index'],places['glass_strip__ALS']);rows.append(choose(ca,site,'ALS','채광창 깊이 틀림',GREEN,2,glass,'UNCERT glass_strip__ALS unchanged'))
 unseen=json.loads((S1/'defs/fig_views_v1.json').read_text())['sites'][site]['unseen_face']['surf_ext'];rows.append(choose(c,site,'LoD2','긴 벽 깊이 없음',GREEN,4,c['ext']==unseen,'frozen unseen wall surf_ext='+str(unseen)))
 neighbor=np.isin(c['ext'],[e for e,r in c['faces'].items() if r.get('building')!='DEBY_LOD2_4959326'])&(c['kind']==2);neighbor=largest_face(c,neighbor&(c['cell_v2']==4));rows.append(choose(c,site,'LoD2','이웃 벽 깊이 없음',GREEN,4,neighbor,'largest cell4 neighboring wall face, excluding B173 building'))
 site='R1rep_b10';c=sources(site);low=(c['kind']==1)&(c['prior_height_m']<c['gt_p']);low=largest_face(c,low&(c['cell_v2']==1));rows.append(choose(c,site,'LoD2','LoD2 지붕 낮음',ORANGE,1,low,'largest new cell1 low-prior roof face in inherited R1 region'));missing=largest_face(c,(c['kind']==1)&(c['cell_v2']==4));rows.append(choose(c,site,'LoD2','지붕 일부 깊이 없음',GREEN,4,missing,'largest new cell4 roof face in inherited R1 region'))
 return rows

def raster(ax,name):
 p=CH6/'t3'/f'ortho_{name}.npz';z=loadz(p);rgb=z['rgb'];u0,v0,res=map(float,[z['u0'],z['v0'],z['res']]);H,W=rgb.shape[:2];extent=[u0,u0+W*res,v0,v0+H*res];ax.imshow(rgb,origin='lower',extent=extent,interpolation='bilinear');return extent,dict(source=str(p),sha256=sha(p),extent_uv=extent)
def axes_style(ax,extent):ax.set_xlim(extent[:2]);ax.set_ylim(extent[2:]);ax.invert_yaxis();ax.set_aspect('equal');ax.set_xticks([]);ax.set_yticks([])
def main():
 rows=labels();fig=plt.figure(figsize=(17,13));gs=fig.add_gridspec(3,3,height_ratios=[1.55,1.,.16],left=.025,right=.985,top=.97,bottom=.025,wspace=.08,hspace=.09);ax=fig.add_subplot(gs[0,:]);ex,meta=raster(ax,'overview');boundaries={};exploration={}
 for name in ['SW','R1','R2','R3E','R4','R5','B0']:
  p=xy_to_uv(np.array(RANGES[name]['polygon_local']));p=np.vstack([p,p[:1]]);ax.plot(*p.T,c='black',lw=.7);a=p[:-1].mean(0);ax.text(*a,name,color='black',ha='center',fontsize=9,path_effects=HALO);exploration[name]=p.tolist()
 offsets={'B0_b10':(-5,-8),'B173nb_b10':(0,-8),'R1rep_b10':(-3,7)}
 for site,name in NAMES.items():
  p=rect_uv(BOX[BID[site]]);boundaries[site]=p.tolist();ax.plot(*p.T,c='white',lw=4.8);ax.plot(*p.T,c='black',lw=2.0);a=p[0]+offsets[site];ax.text(*a,name,color='black',fontsize=11,fontweight='bold',path_effects=HALO)
 axes_style(ax,ex);north(ax,ex[1]-30,ex[3]-30,22);scalebar(ax,ex[0]+15,ex[3]-18,50,'50 m');ax.set_title('(가) 캠퍼스와 실험 지역',loc='left',fontsize=13)
 rasters={'overview':meta};positions={'B0_b10':[(.06,.16),(.60,.20),(.35,.90)],'B173nb_b10':[(.05,.16),(.48,.91),(.46,.08),(.95,.28)],'R1rep_b10':[(.08,.12),(.55,.9)]}
 for i,(site,name) in enumerate(NAMES.items()):
  ax=fig.add_subplot(gs[1,i]);ex,meta=raster(ax,site);rasters[site]=meta;p=rect_uv(BOX[BID[site]]);bounds=[max(ex[0],p[:,0].min()-5),min(ex[1],p[:,0].max()+5),max(ex[2],p[:,1].min()-5),min(ex[3],p[:,1].max()+5)];ax.plot(*p.T,c='white',lw=2);axes_style(ax,bounds);ax.set_title(['(나) B0','(다) B173 주변','(라) R1'][i],loc='left',fontsize=13)
  local=[r for r in rows if r['site']==site]
  for r,position in zip(local,positions[site]):
   if not r['visible']:continue
   ax.annotate(r['text'],xy=r['arrow_uv'],xytext=position,textcoords='axes fraction',fontsize=10.5,fontweight='bold',color=r['color'],ha='left' if position[0]<.4 else 'right' if position[0]>.8 else 'center',va='center',path_effects=HALO,arrowprops=dict(arrowstyle='->',color=r['color'],lw=1.3));r['label_axes_fraction']=list(position)
  north(ax,bounds[1]-7,bounds[3]-2,3.5);scalebar(ax,bounds[0]+1.5,bounds[3]-2,10,'10 m')
 legend=fig.add_subplot(gs[2,:]);legend.axis('off');handles=[Line2D([0],[0],color='black',lw=.7,label='가는 선 = 탐색 지역'),Line2D([0],[0],color='black',lw=2.,label='굵은 선 = 실험 지역'),Line2D([],[],color=ORANGE,marker='$A$',linestyle='none',label='주황 글자 = 사전 정보가 틀린 곳'),Line2D([],[],color=GREEN,marker='$A$',linestyle='none',label='초록 글자 = 영상 깊이가 틀리거나 없는 곳')];legend.legend(handles=handles,loc='center',ncol=2,fontsize=12,frameon=False)
 out=D/'figures/fig6_1_실험지역';out.parent.mkdir(exist_ok=True);fig.savefig(out.with_suffix('.png'),dpi=300,facecolor='white');plt.close(fig);dump(out.with_suffix('.json'),dict(dpi=300,source_script=str(SOURCE),source_sha256=sha(SOURCE),adapter_sha256=sha(__file__),ortho_sources=rasters,exploration_boundaries_uv=exploration,evaluation_boundaries_uv=boundaries,labels=rows,crs='EPSG:25832',local_world_shift=[690953.,5336071.,604.],uv_angle_degrees=A_DEG,painted_cells=False,hatching=False,B173_only=False,annotation_colors=[ORANGE,GREEN],scientific_verdict=None));table('figure6_1_labels',rows);print('FIG61',sum(r['visible'] for r in rows),'shown',len(rows)-sum(r['visible'] for r in rows),'omitted',flush=True)
if __name__=='__main__':main()
