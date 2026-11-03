"""Final 3x5 judgment maps. One 5cm background per region, reused in all panels."""
from common import *
from inherit import functions
from cameras import Cameras,RAW
from photo_prepare import mesh_data
from judgments import NAMES
import zipfile,cv2,open3d as o3d,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
from matplotlib.collections import PolyCollection
FONT='/fonts/NotoSansCJK-Regular.ttc';font_manager.fontManager.addfont(FONT);plt.rcParams.update({'font.family':font_manager.FontProperties(fname=FONT).get_name(),'axes.unicode_minus':False,'font.size':9})
COLORS=['#a8adb2','#3ca76a','#ee9c3b','#3678c9','#a33d85','#ffffff','#d7d7d7']
LABELS=['두 자료 모두 맞음','영상을 따름·맞음','사전 정보를 따름·맞음','놓친 보정','잘못된 보정','맞는 자료 없음','확인 불가']
SITES_KO={'B0_b10':'B0','B173nb_b10':'B173 주변','R1rep_b10':'R1'}
ORDER=[2,3,5,4,6]
def scene_from_prior(g,prior):
    site=str(g['region_name'][0]);m=mesh_data(site,prior);keep=np.isin(m['tri_surface'],np.unique(g['surf']));f=m['F'][keep]
    scene=o3d.t.geometry.RaycastingScene(nthreads=2);scene.add_triangles(o3d.core.Tensor(m['V'].astype('f4')),o3d.core.Tensor(f.astype('u4')))
    return scene,[dict(site=site,prior=prior,surfaces=np.unique(g['surf']).tolist(),triangles=len(f))]
env=dict(np=np,o3d=o3d,cv2=cv2,zipfile=zipfile,RAW=RAW,scene_from_prior=scene_from_prior)
rgb,background=functions('figures_reply2.py',['rgb','background'],env)
def paint(d,j):
    c=d['cell'];r=d['region'][j];colour=np.full(len(c),5,np.int8);colour[c==0]=0
    if j==6:
        colour[c==1]=1;colour[np.isin(c,[2,4])]=2
    else:
        colour[(c==1)&(r==2)]=1;colour[(c==1)&np.isin(r,[0,1,4,3])]=3
        colour[(c==2)&np.isin(r,[1,4])]=2;colour[(c==2)&np.isin(r,[0,2,3])]=4
        colour[(c==4)&np.isin(r,[1,4])]=2;colour[(c==4)&np.isin(r,[2,3])]=4
        colour[np.isin(c,[1,2,4])&(r==9)]=6
    colour[c==9]=6;return colour
def visible_indices(d):
    site=str(d['region_name'][0]);prior=str(d['prior'][0]);m=mesh_data(site,prior)
    scene=o3d.t.geometry.RaycastingScene(nthreads=2);scene.add_triangles(o3d.core.Tensor(m['V'].astype('f4')),o3d.core.Tensor(m['F'].astype('u4')))
    c=d['centre'];top=float(m['V'][:,2].max()+50);rays=np.c_[c[:,:2],np.full(len(c),top),np.zeros((len(c),2)),-np.ones(len(c))].astype('f4')
    hit=scene.cast_rays(o3d.core.Tensor(rays),nthreads=2);primitive=hit['primitive_ids'].numpy();valid=primitive<len(m['F']);same=np.zeros(len(c),bool)
    same[valid]=m['tri_surface'][primitive[valid]]==d['surf'][valid];same&=d['normal'][:,2]>1e-8
    cells=np.floor(c[:,:2]/.25).astype(int);owners={}
    for i in np.argsort(-d['area'],kind='stable'):
        if same[i]:owners.setdefault(tuple(cells[i]),int(i))
    ix=np.array(list(owners.values()),int);return ix,cells[ix]
def fmt(v):return '확인 불가' if v is None else f'{v:.2f} %'
def main():
    start=time.monotonic();folder=D/'figures';folder.mkdir(exist_ok=True);rates=json.loads((D/'tables/table7_1.json').read_text())['rows'];bgs={};metadata=[]
    for site in cfg()['sites']:
        d=loadz(O/'core_points'/f'{site}__LoD2.npz');cam=Cameras(site);bg,extent,j,meta=background(d,cam,'LoD2');meta['surface']='registered regional LoD2 prior, surfaces referenced by evaluation cores; common background for both priors';bgs[site]=(bg,extent,j,cam.names[j] if j is not None else None,meta)
        np.save(O/f'background_{site}.npy',bg);print('BACKGROUND_COMPLETE',site,flush=True)
    handles=[Patch(facecolor=c,label=l) for c,l in zip(COLORS,LABELS)]
    for prior,stem in [('LoD2','fig7_1_LoD2'),('ALS','fig7_2_ALS')]:
      fig,axes=plt.subplots(3,5,figsize=(18,11.4));allmeta=[]
      for row,site in enumerate(cfg()['sites']):
        d=loadz(O/'core_points'/f'{site}__{prior}.npz');bg,extent,j,image_name,meta=bgs[site];ix,cells=visible_indices(d);xy=cells*.25;polys=np.stack([xy,xy+[.25,0],xy+[.25,.25],xy+[0,.25]],1)
        rowfig,rowaxes=plt.subplots(1,5,figsize=(18,4.1));colours=[]
        for col,method in enumerate(ORDER):
          code=paint(d,method)[ix];colours.append(code.tolist());rgba=np.array([matplotlib.colors.to_rgba(COLORS[int(k)],.55) for k in code])
          rr=next((r for r in rates if r['site']==site and r['prior']==prior and r['kind']=='all' and r['method']==['prior_only','image_only','geometry_only','photo_only','fusion','method','oracle'][method]),None)
          caption='놓친 보정 0.00 % · 잘못된 보정 0.00 %' if method==6 else f'놓친 보정 {fmt(rr["missed_pct"])} · 잘못된 보정 {fmt(rr["false_pct"])}'
          for ax in [axes[row,col],rowaxes[col]]:
            ax.imshow(bg,origin='lower',extent=extent);ax.add_collection(PolyCollection(polys,facecolors=rgba,edgecolors='none'))
            if (code==6).any():ax.add_collection(PolyCollection(polys[code==6],facecolors='none',edgecolors='#666666',linewidths=0,hatch='////'))
            ax.set_xlim(extent[:2]);ax.set_ylim(extent[2:]);ax.set_aspect('equal');ax.set_xticks([]);ax.set_yticks([]);ax.set_title(NAMES[method],fontsize=10)
            ax.set_xlabel(caption,fontsize=7)
          if col==0:
            axes[row,col].set_ylabel(SITES_KO[site],fontsize=12);rowaxes[col].set_ylabel(SITES_KO[site],fontsize=12)
        record=dict(site=site,prior=prior,core_file=f'core_points/{site}__{prior}.npz',source_sha256=sha(O/'core_points'/f'{site}__{prior}.npz'),core_indices=ix.tolist(),patch_id=d['patch_id'][ix].tolist(),methods=[NAMES[i] for i in ORDER],colour_numbers=colours,colours=COLORS,colour_labels=LABELS,camera_index=j,image_name=image_name,background=meta,wall_included_in_numbers=True,scientific_verdict=None)
        rowfig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.03),ncol=7,frameon=False,fontsize=8);rowfig.text(.5,.015,'자주색 중 칸 4의 빈 공간 보정은 분모 밖 · 숫자는 LoD2 벽 포함 · 빗금은 확인 불가',ha='center',fontsize=8);rowfig.subplots_adjust(left=.045,right=.995,top=.89,bottom=.21,wspace=.04)
        out=folder/f'{stem}_{site}.png';rowfig.savefig(out,dpi=300);plt.close(rowfig);dump(out.with_suffix('.json'),record);allmeta.append(record)
      fig.legend(handles=handles,loc='lower center',ncol=7,frameon=False,fontsize=10)
      fig.text(.5,.047,'자주색 중 칸 4의 빈 공간 보정은 틀린 비율 분모 밖 · 숫자는 LoD2 벽 포함 · 빗금은 판단 확인 불가',ha='center',fontsize=9)
      fig.subplots_adjust(left=.045,right=.995,top=.97,bottom=.08,wspace=.04,hspace=.24)
      p=folder/f'{stem}.png';fig.savefig(p,dpi=300);plt.close(fig);dump(p.with_suffix('.json'),dict(rows=allmeta,scientific_verdict=None))
      metadata.append(str(p));print('FIGURE_COMPLETE',prior,flush=True)
    dump(O/'timing/figures.json',dict(at=now(),seconds=time.monotonic()-start,outputs=metadata,backgrounds=3,scientific_verdict=None))
if __name__=='__main__':main()
