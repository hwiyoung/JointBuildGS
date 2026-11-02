"""Forward measurements and unchanged scoring into inspectable tables/figures."""
import sys,csv,itertools,gc
import numpy as np
from scipy.spatial import cKDTree
from plyfile import PlyData
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from common import *
from cause_r8_spatial import bins
ROOT=OUT/'screen_sim';DEST=DOC/'screen_sim';TAB=DEST/'tables';FIG=DEST/'figures'
def table(name,rows):
 TAB.mkdir(parents=True,exist_ok=True);dump(TAB/(name+'.json'),dict(rows=rows,scientific_verdict=None))
 if not rows:return
 fields=list(dict.fromkeys(k for r in rows for k in r));
 with (TAB/(name+'.csv')).open('w') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 def fmt(v):
  if v is None:return '없음'
  if isinstance(v,float):return f'{v:.8g}'
  return str(v).replace('|','/').replace('\n',' ')
 (TAB/(name+'.md')).write_text('| '+' | '.join(fields)+' |\n|'+'|'.join(['---']*len(fields))+'|\n'+'\n'.join('| '+' | '.join(fmt(r.get(k)) for k in fields)+' |' for r in rows)+'\n')
def figure(name,fig,meta):
 FIG.mkdir(parents=True,exist_ok=True);fig.savefig(FIG/(name+'.png'),dpi=160,bbox_inches='tight');fig.savefig(FIG/(name+'.pdf'),bbox_inches='tight');plt.close(fig);dump(FIG/(name+'.json'),dict(**meta,scientific_verdict=None))
def local(p):return Path(p.replace('/out/',str(OUT)+'/'))
def avg(rows,region,metric):
 v=[r['quality'][region][metric] for r in rows if r['quality'][region][metric] is not None];return float(np.mean(v)) if v else None
def quality_summary(rows,region):
 n=sum(r['quality'][region]['pixels'] for r in rows);s=sum(r['quality'][region]['pixels']*(r['quality'][region]['mse'] or 0) for r in rows);m=s/n if n else None
 return dict(views=sum(r['quality'][region]['pixels']>0 for r in rows),pixels=n,mean_psnr_db=avg(rows,region,'psnr'),mean_ssim=avg(rows,region,'ssim'),pooled_mse=m,pooled_psnr_db=-10*np.log10(m) if m is not None and m>0 else None)
def process(row,cfg,inp,b):
 key=row['key'];root=ROOT/'states'/key;a=dict(np.load(root/'gaussians.npz'));xyz=a['xyz'];N=len(xyz);x,h=bins(xyz,b);cams=np.array([np.linalg.inv(v['W2C'])[:3,3] for v in inp['views']]);distance=cKDTree(cams).query(xyz,workers=4)[0];near=distance<=30;v=PlyData.read(str(local(row['ply'])))['vertex'].data
 assert np.array_equal(np.c_[v['x'],v['y'],v['z']],xyz)
 if row['family']=='base':
  initial=np.load(S0/'fork_inputs/s61/B173nb_b10'/f'scene_{row["prior"]}/sparse/0/origin.npy');tag=initial[v['init_id'].astype('i8')];assert np.array_equal(tag,v['origin']);names=['SfM','사전 정보']
 elif row['family'] in ['r7','r8']:
  s=np.load(local(row['snapshot']));assert np.array_equal(xyz,s['xyz']) and np.array_equal(v['init_id'],s['init_id']);tag=s['target_tag'];names=['배경','패치','풀림']
 elif row['family']=='image_only':tag=np.zeros(N,'i1');names=['SfM / 영상만']
 else:tag=np.zeros(N,'i1');names=['출신 확인 불가']
 np.savez_compressed(root/'groups.npz',xy=x,height=h,tag=tag,nearest_camera_distance_m=distance,near30=near,provenance_names=names)
 sums=a['total_contribution'];rsums=a['roi_contribution'];before=json.loads((root/'before/summary.json').read_text());groups=[];summary=[];views=[];tops=[];qualities=[];arrays=[]
 for variant in ['before']+[r['key'] for r in cfg['candidates']]:
  data=json.loads((root/variant/'summary.json').read_text());rr=data['views'];quality={reg:quality_summary(rr,reg) for reg in ['all','roi']};baseq={reg:quality_summary(before['views'],reg) for reg in ['all','roi']};over=np.array([r['overlaps'] for r in rr]);removed=np.zeros(N,bool) if variant=='before' else np.load(root/(variant+'_remove.npy'));nd=int(removed.sum());assert nd==data['selected']
  s=dict(state=key,variant=variant,iteration=row['iteration'],gaussians=N,removed=nd,removed_fraction=nd/N,removed_contribution_fraction=float(sums[removed].sum()/sums.sum()),removed_roi_contribution_fraction=float(rsums[removed].sum()/rsums.sum()) if rsums.sum()>0 else None,mean_psnr_db=quality['all']['mean_psnr_db'],psnr_change_db=quality['all']['mean_psnr_db']-baseq['all']['mean_psnr_db'],roi_mean_psnr_db=quality['roi']['mean_psnr_db'],roi_psnr_change_db=quality['roi']['mean_psnr_db']-baseq['roi']['mean_psnr_db'],mean_ssim=quality['all']['mean_ssim'],roi_mean_ssim=quality['roi']['mean_ssim'],overlap_median=float(np.median(over)),overlap_max=int(over.max()));summary.append(s)
  for reg,q in quality.items():qualities.append(dict(state=key,variant=variant,region=reg,**q))
  for r in rr:
   z=dict(state=key,variant=variant,camera=r['camera'],width=r['width'],height=r['height'],overlaps=r['overlaps'],binning_bytes=r['binning_bytes'])
   for reg in ['all','roi']:
    z.update({reg+'_'+k:v for k,v in r['quality'][reg].items()})
   views.append(z)
  for rank,r in enumerate(sorted(rr,key=lambda r:(-r['overlaps'],r['camera']))[:5],1):tops.append(dict(state=key,variant=variant,rank=rank,camera=r['camera'],overlaps=r['overlaps'],binning_bytes=r['binning_bytes']))
  for t,name in enumerate(names):
   for xi,hi,ni in itertools.product(range(4),range(4),range(2)):
    m=(tag==t)&(x==xi)&(h==hi)&(near==bool(ni));sel=m&removed;n=int(m.sum());nsel=int(sel.sum());groups.append(dict(state=key,variant=variant,provenance=name,xy_bin=xi,height_bin=hi,camera_within30m=bool(ni),all_count=n,removed=nsel,removed_fraction_of_group=nsel/n if n else None,removed_fraction_of_state=nsel/N,contribution_sum=float(sums[sel].sum()),roi_contribution_sum=float(rsums[sel].sum())))
  if variant!='before':arrays.append((variant,removed))
 # Radius/total contribution: logarithmic bins of all saved rows, near camera in orange.
 fig,axes=plt.subplots(1,2,figsize=(13,5),sharex=True,sharey=True);histmeta=[];positive=(a['max_radius']>0)&(sums>0);rx=np.log10(np.maximum(a['max_radius'],1));cy=np.log10(np.maximum(sums,1e-12));xe=np.linspace(0,max(float(rx.max()),3),121);ye=np.linspace(min(float(cy[positive].min()) if positive.any() else -8,-8),max(float(cy.max()),1),121)
 for ax,nn,title,cmap in zip(axes,[False,True],['가장 가까운 카메라 > 30 m','가장 가까운 카메라 ≤ 30 m'],['Blues','Oranges']):
  m=positive&(near==nn);hist,_,_=np.histogram2d(rx[m],cy[m],bins=[xe,ye]);ax.pcolormesh(xe,ye,np.log10(1+hist.T),cmap=cmap,shading='auto');histmeta.append(dict(near30=nn,hist=hist.astype(int).tolist()));ax.set_title(title);ax.set_xlabel('log10(203장 최대 화면 반지름 / px)');ax.set_ylabel('log10(203장 총 색 기여)')
  for threshold in [20,102.4,256,512]:ax.axvline(np.log10(threshold),color='black',ls='--',lw=.7);ax.text(np.log10(threshold),ye[-1],f'{threshold:g}',rotation=90,va='top',fontsize=7)
 fig.suptitle(key);figure(key+'_radius_contribution',fig,dict(state=key,x_log10_edges=xe.tolist(),y_log10_edges=ye.tolist(),panels=histmeta,zero_radius=int((a['max_radius']==0).sum()),zero_total_contribution=int((sums==0).sum()),zero_contribution_removed={v:int((mask&(sums==0)).sum()) for v,mask in arrays},rule='all positive rows histogram; zeros counted separately'))
 # Fixed input-only context +/- 200 m around evaluation rectangle, plus full extent.
 poly=np.array(list(itertools.product(*zip(b['lo'],b['hi']))))@np.array(b['basis']);poly=poly[[0,1,3,2,0]];lo=poly.min(0)-200;hi=poly.max(0)+200
 fig,axs=plt.subplots(2,2,figsize=(12,10),sharex=True,sharey=True);overhead=[]
 for ax,(variant,mask) in zip(axs.ravel(),arrays):
  hist,xe2,ye2=np.histogram2d(xyz[mask,0],xyz[mask,1],bins=240,range=[[lo[0],hi[0]],[lo[1],hi[1]]]);ax.pcolormesh(xe2,ye2,np.log10(1+hist.T),cmap='magma',shading='auto');ax.plot(poly[:,0],poly[:,1],color='cyan');ax.scatter(cams[:,0],cams[:,1],s=4,c='lime',marker='^');ax.set_xlim(lo[0],hi[0]);ax.set_ylim(lo[1],hi[1]);ax.set_aspect('equal');ax.set_title(f'{variant}: {int(mask.sum()):,}개');ax.set_xlabel('지역 X / m');ax.set_ylabel('지역 Y / m');overhead.append(dict(variant=variant,hist=hist.astype(int).tolist(),outside_context=int(mask.sum()-hist.sum())))
 figure(key+'_removed_overhead',fig,dict(state=key,extent=[lo.tolist(),hi.tolist()],xy_frame='EPSG:25832 minus inherited world shift',panels=overhead,cameras=cams.tolist(),evaluation_polygon=poly.tolist(),rule='input-only eval rectangle +/-200m, same all states; out-of-frame counts retained'))
 for cam in inp['fixed_views']:
  fig,axs=plt.subplots(2,3,figsize=(15,7.5));base=np.load(root/'before'/(cam+'_float.npz'));axs[0,0].imshow(base['gt'].transpose(1,2,0));axs[0,0].set_title('학습 영상')
  for ax,variant in zip(axs.ravel()[1:],['before']+[r['key'] for r in cfg['candidates']]):
   z=np.load(root/variant/(cam+'_float.npz'));ax.imshow(z['rgb'].transpose(1,2,0));ax.set_title(variant)
  for ax in axs.ravel():ax.axis('off')
  fig.suptitle(key+' / '+cam);figure(key+'_'+cam+'_renders',fig,dict(state=key,camera=cam,variants=['training RGB','before']+[r['key'] for r in cfg['candidates']],rgb_range=[0,1],input_roi=cam+'.npz'))
 for name,rows in [('summary',summary),('groups',groups),('views',views),('top5',tops),('quality',qualities)]:dump(root/(name+'_table.json'),dict(rows=rows,scientific_verdict=None))
 dump(root/'table_receipt.json',dict(status='PASS',gaussians=N,at=stamp(),source_sha256=sha(__file__),scientific_verdict=None));print('SIM_TABLE',key,flush=True)
def aggregate(cfg,inp):
 for name in ['summary','groups','views','top5','quality']:
  rows=[]
  for r in cfg['states']:
   p=ROOT/'states'/r['key']/(name+'_table.json')
   if p.exists():rows+=json.loads(p.read_text())['rows']
  table(name,rows)
 table('common_roi',[{k:v for k,v in r.items() if k not in ['K','W2C']} for r in inp['views']]);score=[]
 for p in sorted((ROOT/'scores').glob('*/*/*/values.json')):
  z=json.loads(p.read_text())
  for cell,m in z['metrics'].items():
   g=m['gt'];r=m['res']['E'];s=z['surface'][cell];score.append(dict(state=z['state'],variant=z['variant'],prior=z['prior'],cell=cell,n_gt=g['n_gt'],n_result_E=r['n'],n_result_all=m['res']['n_res_all'],excluded_result_E=r['excluded'],R_tau=g.get('R_tau'),P_tau_E=r.get('P_tau'),GT_mean_distance_m=g['mean']/100 if 'mean' in g else None,result_E_mean_distance_m=r['mean']/100 if 'mean' in r else None,**s))
 table('axes71',score)
def main():
 for font in Path('/fonts').glob('NotoSansCJK-Regular.ttc'):font_manager.fontManager.addfont(str(font));plt.rcParams['font.family']='Noto Sans CJK JP'
 plt.rcParams['axes.unicode_minus']=False;cfg=json.loads((CFG/'screen_sim.json').read_text());inp=json.loads((ROOT/'inputs/index.json').read_text());b=json.loads(Path(cfg['boundaries']).read_text())
 for r in cfg['states']:
  root=ROOT/'states'/r['key']
  if (root/'receipt.json').exists() and not (root/'table_receipt.json').exists():process(r,cfg,inp,b);gc.collect()
 aggregate(cfg,inp)
if __name__=='__main__':main()
