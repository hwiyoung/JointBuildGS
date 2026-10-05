"""Tables A-D and four fixed-comparison figures from measured artifacts only."""
import csv,json,sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from PIL import Image
from scipy.spatial import cKDTree
from analyze import OriginalMesh,xyz_ply
T=Path('/task');names=['N','B+0.25','B+0.5','B+1.0','B-1.0'];deltas=[0,.25,.5,1,-1]
if (T/'conditions/N/finished.txt').exists() and not (T/'conditions/N/train_receipt.json').exists():
 import datetime
 nr=T/'conditions/N';start=datetime.datetime.fromisoformat((nr/'started.txt').read_text().strip());end=datetime.datetime.fromisoformat((nr/'finished.txt').read_text().strip());rc=int((nr/'train.exit').read_text())
 container=json.loads((T/'provenance/n_container_inspect.json').read_text())[0]
 (nr/'train_receipt.json').write_text(json.dumps({'condition':'N','phase':'train','command':container['Config']['Cmd'],'image_id':container['Image'],'started_at':start.isoformat(),'finished_at':end.isoformat(),'seconds':(end-start).total_seconds(),'exit_code':rc,'status':'PASS' if rc==0 else 'FAILED','scientific_verdict':None},indent=2))
for p in ['tables','figures']:(T/p).mkdir(exist_ok=True)
from matplotlib import font_manager
font_manager.fontManager.addfont(str(T/'assets/NotoSansCJK-Regular.ttc'))
ko_font=font_manager.FontProperties(fname=str(T/'assets/NotoSansCJK-Regular.ttc')).get_name()
plt.rcParams.update({'font.family':ko_font,'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'white'})
def read(p,default=None):return json.loads(p.read_text()) if p.exists() else ({} if default is None else default)
def table(name,rows):
 fields=list(dict.fromkeys(k for row in rows for k in row))
 with (T/'tables'/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
A=[];B=[];C=[];D=[];summaries={};mesh=OriginalMesh(T/'provenance/original_mesh.npz');execution=read(T/'status.json')
for name in names:
 root=T/'conditions'/name;s=read(root/'analysis/summary.json');summaries[name]=s
 a={'condition':name,'status':'PENDING','PSNR_dB':None,'SSIM':None,'LPIPS_native_vgg':None,'global_M3C2_mean_abs_m':None,'global_M3C2_signed_median_m':None,'global_M3C2_valid_n':None,'F1_at_0_2':None,'F1_at_0_5':None}
 m=read(root/'model/results.json').get('ours_30000',{})
 if m:a.update(status='PARTIAL',PSNR_dB=m.get('PSNR'),SSIM=m.get('SSIM'),LPIPS_native_vgg=m.get('LPIPS'))
 files=list((root/'evaluation/native_results').glob('*/m3c2_distances.npy')) if (root/'evaluation/native_results').exists() else []
 if files:
  e=np.load(files[0]);e=e[np.isfinite(e)];a.update(global_M3C2_mean_abs_m=float(np.mean(np.abs(e))) if len(e) else None,global_M3C2_signed_median_m=float(np.median(e)) if len(e) else None,global_M3C2_valid_n=len(e),global_M3C2_rmse_m=float(np.sqrt(np.mean(e*e))) if len(e) else None,global_M3C2_signed_mean_m=float(np.mean(e)) if len(e) else None)
 predfile=root/'evaluation/pred_points.ply';gtfile=root/'evaluation/gt_cropped.ply'
 if predfile.exists() and gtfile.exists():
  # Same native eval_f1 0.1m downsampling, < threshold and symmetric F1; retain full precision.
  def voxel(x):return x[np.unique(np.floor(x/.1).astype(np.int64),axis=0,return_index=True)[1]]
  p=voxel(xyz_ply(predfile));g=voxel(xyz_ply(gtfile));dp=cKDTree(g).query(p,workers=8)[0];dg=cKDTree(p).query(g,workers=8)[0]
  for thr,key in [(.2,'F1_at_0_2'),(.5,'F1_at_0_5')]:
   pr=float(np.mean(dp<thr));re=float(np.mean(dg<thr));a[key]=2*pr*re/(pr+re) if pr+re else 0.
 if all(a[k] is not None for k in ['PSNR_dB','SSIM','LPIPS_native_vgg','global_M3C2_mean_abs_m','F1_at_0_2','F1_at_0_5']):a['status']='MEASURED'
 if a['status']!='MEASURED' and 'FAILED' in execution.get('conditions',{}).get(name,{}).values():a['status']='FAILED_OR_PARTIAL'
 A.append(a)
 for label in ['roof','wall']:
  b={'condition':name,'surface':label,'n':None,'median_m':None,'nmad_m':None,'abs_gt_0_2_fraction':None,'gt_n':None,'prediction_n':None}
  b.update({k:v for k,v in s.get('surfaces',{}).get(label,{}).items() if k!='normal_component_stats'});B.append(b)
 p=s.get('protection',{});c={'condition':name,'protected_n_8000':p.get('n_8000'),'matched_n_30000':p.get('n'),'opacity_median':p.get('opacity_median'),'opacity_gt_0_5_fraction':p.get('opacity_gt_0_5_fraction'),'opacity_lt_0_01_fraction':p.get('opacity_lt_0_01_fraction'),'movement_median_m':p.get('movement_median_m'),'movement_p95_m':p.get('movement_p95_m'),'distance_failed':p.get('distance_failed'),'collision_failed':p.get('collision_failed'),'unmatched_total':p.get('unmatched_total'),'matched_native_protected_fraction':p.get('matched_native_protected_fraction'),'roof_unprotected_n':s.get('roof_unprotected',{}).get('n'),'roof_unprotected_opacity_median':s.get('roof_unprotected',{}).get('opacity_median'),'actual_protected_n':s.get('actual_protected',{}).get('n'),'actual_protected_opacity_median':s.get('actual_protected',{}).get('opacity_median')};C.append(c)
 event=s.get('densification',{});D.append(dict(condition=name,**{k:event.get(k) for k in ['event','added','removed','clone_added','split_added','split_parents_removed','culled']}))
for c in C:
 native=summaries[c['condition']].get('actual_protected',{})
 c['actual_opacity_gt_0_5_fraction']=native.get('opacity_gt_0_5_fraction')
 c['actual_opacity_lt_0_01_fraction']=native.get('opacity_lt_0_01_fraction')
 roof_native=summaries[c['condition']].get('roof_actual_protected',{})
 c['roof_actual_protected_n']=roof_native.get('n')
 c['roof_actual_protected_opacity_median']=roof_native.get('opacity_median')
 c['roof_actual_protected_opacity_gt_0_5_fraction']=roof_native.get('opacity_gt_0_5_fraction')
 c['roof_actual_protected_opacity_lt_0_01_fraction']=roof_native.get('opacity_lt_0_01_fraction')
for row in B:
 row['measurement_status']='MEASURED' if row.get('median_m') is not None else 'UNAVAILABLE'
finite_audit=read(T/'provenance/checkpoint_finite_audit.json')
for row in C:
 s=summaries[row['condition']];a=finite_audit.get(row['condition'],{}).get('30000',{})
 row['nonfinite_xyz_30000']=a.get('nonfinite_xyz')
 row['nonfinite_xyz_native_protected']=a.get('nonfinite_xyz_protected')
 row['nonfinite_xyz_native_unprotected']=a.get('nonfinite_xyz_unprotected')
 native=s.get('actual_protected',{})
 row['actual_opacity_nonfinite_n']=native.get('opacity_nonfinite_n',0 if native else None)
 row['actual_opacity_valid_n']=native.get('opacity_valid_n',native.get('n'))
 row['measurement_status']=('MEASURED_WITH_NONFINITE_EXCLUSIONS' if a.get('nonfinite_xyz',0) else 'MEASURED') if row.get('opacity_median') is not None else 'UNAVAILABLE'
for row in D:
 row['measurement_status']='COMPLETE_TRAINING' if row.get('event')=='completed' else 'PARTIAL_OR_UNAVAILABLE'
table('table_A.csv',A);table('table_B.csv',B);table('table_C.csv',C);table('table_D.csv',D)
# Figure 1: errors placed at their nearest GT coordinates, fixed colour scale.
fig,axes=plt.subplots(1,5,figsize=(20,6),layout='constrained');norm=Normalize(-1.5,1.5)
for ax,name in zip(axes,names):
 p=T/'conditions'/name/'analysis/roof_errors.npz'
 if p.exists():
  z=np.load(p);xy=z['gt_nearest'][:,:2];e=z['signed_error'];cell=np.floor(xy/.2).astype(np.int64);_,idx=np.unique(cell,axis=0,return_index=True)
  # Deterministic first measured point in each cell; no surface interpolation.
  ax.scatter(xy[idx,0],xy[idx,1],c=e[idx],s=3,cmap='coolwarm',norm=norm,rasterized=True)
 else:ax.text(.5,.5,'자료 없음',ha='center',transform=ax.transAxes)
 ax.set(title=name,xlabel='국소 X (m)',xlim=(mesh.lo[0],mesh.hi[0]),ylim=(mesh.lo[1],mesh.hi[1]));ax.set_aspect('equal')
axes[0].set_ylabel('국소 Y (m)');fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap='coolwarm'),ax=list(axes),label='지붕 부호 오차 (m)',shrink=.8,extend='both');fig.suptitle('그림 1 | GT 위에 투영한 지붕 부호 오차');fig.savefig(T/'figures/figure_1_roof_error.png',dpi=180);plt.close(fig)
# Figure 2: probabilities, same bins. Additional log panel resolves near-zero opacity.
fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained');histrows=[]
for name,color,style in [('N','#2166ac','-'),('B+1.0','#b35806','--')]:
 p=T/'conditions'/name/'analysis/protected_statistics.npz'
 if not p.exists():continue
 x=np.load(p)['tracked_opacity']
 if not len(x):continue
 weights=np.ones(len(x))/len(x)
 axes[0].hist(x,bins=np.linspace(0,1,51),weights=weights,histtype='step',color=color,linestyle=style,label=f'{name}, n={len(x):,}',lw=2)
 axes[1].hist(np.log10(np.maximum(x,1e-8)),bins=np.linspace(-8,0,81),weights=weights,histtype='step',color=color,linestyle=style,label=name,lw=2)
 h,b=np.histogram(x,bins=np.linspace(0,1,51))
 histrows.extend({'condition':name,'bin_left':b[i],'bin_right':b[i+1],'count':int(n),'fraction':float(n/len(x))} for i,n in enumerate(h))
for ax in axes:ax.set_ylabel('구간별 비율');ax.grid(axis='y',alpha=.2)
axes[0].set(xlabel='불투명도',xlim=(0,1));axes[1].set(xlabel='불투명도의 log10 (하한 1e-8)',xlim=(-8,0))
for value in [.01,.5]:axes[0].axvline(value,c='#666666',lw=.8,ls=':');axes[1].axvline(np.log10(value),c='#666666',lw=.8,ls=':')
if not histrows:
 for ax in axes:ax.text(.5,.5,'추적 불투명도 자료 없음',ha='center',transform=ax.transAxes)
if axes[0].get_legend_handles_labels()[0]:axes[0].legend()
fig.suptitle('그림 2 | 30,000회 보호 원반 불투명도 (5 cm 추적 성공 집합)');fig.savefig(T/'figures/figure_2_opacity.png',dpi=180);plt.close(fig)
if histrows:table('opacity_histogram_bins.csv',histrows)
# Figure 3: one frozen ridge-crossing plane, derived only from the unbiased prior.
tri=mesh.v[mesh.f[mesh.target&(mesh.kind==1)]];edges=[]
for t in tri:
 for i,j in [(0,1),(1,2),(2,0)]:
  a,b=t[i],t[j];length=np.linalg.norm((b-a)[:2])
  if abs(a[2]-b[2])<.2 and length>1:edges.append((float((a[2]+b[2])/2),float(length),a,b))
assert edges
_,_,a,b=max(edges,key=lambda q:(q[0],q[1]));center=(a+b)/2;along=(b-a)[:2];along/=np.linalg.norm(along);across=np.array([-along[1],along[0]])
section={'center':center.tolist(),'ridge_direction_xy':along.tolist(),'section_direction_xy':across.tolist(),'slab_width_m':.5,'selection':'highest near-horizontal original roof edge, then longest; frozen before results'}
(T/'provenance/section_contract.json').write_text(json.dumps(section,indent=2))
def section_points(x):
 uv=x[:,:2]-center[:2];keep=np.abs(uv@along)<=.25;return uv[keep]@across,x[keep,2],keep
# Plot exact intersections of source triangles with section plane.
def prior_segments(dz):
 seg=[]
 for t in tri:
  d=(t[:,:2]-center[:2])@along;pts=[]
  for i,j in [(0,1),(1,2),(2,0)]:
   if d[i]*d[j]<0:pts.append(t[i]+(t[j]-t[i])*d[i]/(d[i]-d[j]))
   elif abs(d[i])<1e-8:pts.append(t[i])
  if len(pts)>=2:
   p=np.array(pts[:2]);seg.append(np.column_stack(((p[:,:2]-center[:2])@across,p[:,2]+dz)))
 return seg
band=np.concatenate(prior_segments(0),axis=0)
section['plot_xlim_m']=[float(band[:,0].min()-1),float(band[:,0].max()+1)]
section['plot_ylim_m']=[float(band[:,1].min()+min(deltas)-.5),float(band[:,1].max()+max(deltas)+.5)]
(T/'provenance/section_contract.json').write_text(json.dumps(section,indent=2))
fig,axes=plt.subplots(1,5,figsize=(22,5),layout='constrained',sharex=True,sharey=True)
for ax,name,dz in zip(axes,names,deltas):
 root=T/'conditions'/name;gtfile=root/'evaluation/gt_cropped.ply';predfile=root/'evaluation/pred_points.ply'
 if gtfile.exists():
  x,y,_=section_points(xyz_ply(gtfile));ax.scatter(x,y,s=1,c='#555555',label='GT',alpha=.4,rasterized=True)
 if predfile.exists():
  x,y,_=section_points(xyz_ply(predfile));ax.scatter(x,y,s=1,c='#2166ac',label='최종 메시 표본',alpha=.4,rasterized=True)
 else:ax.text(.5,.05,'최종 메시 자료 없음',ha='center',transform=ax.transAxes,fontsize=9)
 for j,seg in enumerate(prior_segments(dz)):ax.plot(seg[:,0],seg[:,1],c='#b35806',ls='--',lw=1.5,label='편향 prior' if j==0 else None)
 p=root/'analysis/protected_statistics.npz'
 if p.exists():
  z=np.load(p);m=z['local_actual_protected'];x,y,k=section_points(z['local_xyz'][m]);op=z['local_opacity'][m][k];ax.scatter(x,y,c=op,s=8,cmap='viridis',vmin=0,vmax=1,label='실제 보호 원반',rasterized=True)
 ax.set(title=name,xlabel='마루 횡단 거리 (m)',xlim=section['plot_xlim_m'],ylim=section['plot_ylim_m']);ax.grid(alpha=.15)
axes[0].set_ylabel('국소 높이 Z (m)');handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=4);fig.colorbar(plt.cm.ScalarMappable(norm=Normalize(0,1),cmap='viridis'),ax=list(axes),label='보호 원반 불투명도',shrink=.8);fig.suptitle('그림 3 | 동일 지붕 마루 횡단면 (폭 0.5 m)');fig.savefig(T/'figures/figure_3_section.png',dpi=180);plt.close(fig)
# Figure 4: same first native test camera in each condition.
fig,axes=plt.subplots(1,5,figsize=(20,5),layout='constrained')
for ax,name,a in zip(axes,names,A):
 files=sorted((T/'conditions'/name/'model/test/ours_30000/renders').glob('*.png'))
 if files:ax.imshow(Image.open(files[0]))
 else:ax.text(.5,.5,'자료 없음',ha='center',transform=ax.transAxes)
 ax.axis('off');lp=a['LPIPS_native_vgg'];ax.set_title(name+(f'\n평균 LPIPS {lp:.4f}' if lp is not None else ''))
fig.suptitle('그림 4 | 동일 시험 시점 렌더 (공식 metrics.py 평가)');fig.savefig(T/'figures/figure_4_test_render.png',dpi=180);plt.close(fig)
from write_korean import write_korean
write_korean(T)
print('한국어 표 A-D, 그림 1-4, 결과 보고서 생성 완료')
state=read(T/'status.json')
if state.get('status') in ('COMPLETE','PARTIAL'):
 import subprocess
 subprocess.run([sys.executable,'/audit/seal_delivery.py'],check=True)
