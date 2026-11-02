"""Fixed saved-state scientific figures; every figure has companion JSON."""
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager,patches
from common import *
ROOT=OUT/'r8_recorded_continue';H=ROOT/'heavy';T=H/'tables';F=H/'figures'
NAMES=['배경','패치','풀림: 100회 자손','풀림: 그 밖'];COLORS=['#317fa0','#d29123','#9c438a','#d4a7bf']
for p in Path('/fonts').glob('*CJK*Regular.ttc'):
 font_manager.fontManager.addfont(str(p));plt.rcParams['font.family']=font_manager.FontProperties(fname=str(p)).get_name();break
plt.rcParams['axes.unicode_minus']=False
def read(p):return json.loads(Path(p).read_text())
def save(fig,name,data):
 fig.savefig(F/(name+'.png'),dpi=180,bbox_inches='tight');fig.savefig(F/(name+'.pdf'),bbox_inches='tight');plt.close(fig);dump(F/(name+'.json'),dict(data=data,scientific_verdict=None))
def main():
 lock=read(CFG/'r8_heavy_figures.lock.json')
 for p,h in lock['files'].items():assert sha(p)==h,p
 F.mkdir(exist_ok=False);c=read(CFG/'r8_heavy.json');b=read(c['boundaries']);rows=read(T/'top_summary.json')['rows'];cam=c['heavy_camera'];s=[r for r in rows if r['camera']==cam];fig,ax=plt.subplots(2,1,figsize=(12,8),sharex=True)
 for stage,label,color in [('pre','밀도 제어 직전','#317fa0'),('post','밀도 제어 직후','#d29123')]:
  rr=[r for r in s if r['stage']==stage and r['top_fraction']==.01];ax[0].plot([r['iteration'] for r in rr],[r['total_overlap'] for r in rr],'o-',label=label,color=color)
  for q,ls in [(.01,'--'),(.1,'-')]:
   qq=[r for r in s if r['stage']==stage and r['top_fraction']==q];ax[1].plot([r['iteration'] for r in qq],[r['overlap_share']*100 for r in qq],marker='o',ls=ls,color=color,label=f'{label} · 상위 {int(q*100)}%')
 base=next(r for r in s if r['state']=='base_LoD2_30000' and r['top_fraction']==.01);st=next(r for r in s if r['state']=='r8_14031_stop' and r['top_fraction']==.01)
 ax[0].axhline(base['total_overlap'],ls=':',color='#555',label='기준선 30,000회');ax[0].scatter([14031],[st['total_overlap']],marker='x',s=65,color='#b62e3e',label='14,031회 시도 직전');ax[0].set_ylabel('가우시안–타일 겹침');ax[0].legend(fontsize=9)
 for q in [.01,.1]:
  rr=next(r for r in s if r['state']=='r8_14031_stop' and r['top_fraction']==q);ax[1].scatter([14031],[rr['overlap_share']*100],marker='x',s=65,color='#b62e3e')
 ax[1].set(xlabel='반복',ylabel='상위 무리의 전체 겹침 몫 (%)',ylim=(0,102));ax[1].legend(fontsize=8,ncol=2);[a.grid(alpha=.2) for a in ax];fig.suptitle(cam+' · 같은 영상, 저장 상태별');fig.tight_layout();save(fig,'heavy_iteration_curve',s)
 # Full stopped-state spatial/camera projection. Centers shown; rectangle outlines for100 heaviest.
 d=H/'states/r8_14031_stop';a=dict(np.load(d/'arrays.npz'));v=dict(np.load(d/(cam+'.npz')));tiles=v['tiles'].astype('i8');order=np.lexsort((np.arange(len(tiles)),-tiles));meta=read(OUT/'r7/stage1/B173nb_b10_LoD2/maps/index.json')['views'][cam];W=np.array(meta['W2C']);K=np.array(meta['K']);xyz=a['xyz'].astype(float);camera_xyz=xyz@W[:3,:3].T+W[:3,3];proj=camera_xyz@K.T
 with np.errstate(divide='ignore',invalid='ignore'):uv=proj[:,:2]/proj[:,2,None]
 rgb=np.clip(v['rgb'].transpose(1,2,0),0,1);height,width=rgb.shape[:2];corn=np.array([[b['lo'][0],b['lo'][1]],[b['hi'][0],b['lo'][1]],[b['hi'][0],b['hi'][1]],[b['lo'][0],b['hi'][1]],[b['lo'][0],b['lo'][1]]])@np.array(b['basis']);data=[]
 for q in c['top_fractions']:
  ix=order[:math.ceil(q*len(order))];inside=(camera_xyz[ix,2]>.2)&(uv[ix,0]>=0)&(uv[ix,0]<width)&(uv[ix,1]>=0)&(uv[ix,1]<height);fig,axs=plt.subplots(1,3,figsize=(18,5.8));axs[0].imshow(rgb);visible=ix[inside]
  for tag,name in enumerate(NAMES):
   jj=visible[a['group'][visible]//16==tag];axs[0].scatter(uv[jj,0],uv[jj,1],s=1,alpha=.35,c=COLORS[tag],rasterized=True)
   jj=ix[a['group'][ix]//16==tag]
   for aa in axs[1:]:aa.scatter(xyz[jj,0],xyz[jj,1],s=1,alpha=.3,c=COLORS[tag],label=name,rasterized=True)
  for j in ix[:100]:
   if camera_xyz[j,2]>.2:
    r=float(v['radius'][j]);axs[0].add_patch(patches.Rectangle((uv[j,0]-r,uv[j,1]-r),2*r,2*r,fill=False,color=COLORS[a['group'][j]//16],lw=.3,alpha=.3))
  axs[0].set(xlim=(0,width),ylim=(height,0),title='카메라 시점 · 중심 + 상위 100개 반지름 상자',xlabel='pixel x',ylabel='pixel y')
  for aa in axs[1:]:aa.plot(corn[:,0],corn[:,1],color='black',lw=1.2,label='평가 상자');aa.scatter(*v['camera_center'][:2],marker='*',s=90,c='red',label='카메라');aa.set(xlabel='지역 X (m)',ylabel='지역 Y (m)',aspect='equal');aa.grid(alpha=.2)
  axs[1].set_title('위에서 본 중심 · 전체 범위');axs[2].set(title='위에서 본 중심 · 평가 상자 주변',xlim=(corn[:,0].min()-50,corn[:,0].max()+50),ylim=(corn[:,1].min()-50,corn[:,1].max()+50));axs[2].legend(fontsize=8,markerscale=4)
  fig.suptitle(f'중단 상태 · 겹침 상위 {int(q*100)}% ({len(ix):,}개) · 색은 출신');fig.tight_layout();save(fig,f'top{int(q*100)}_camera_overhead',dict(camera=cam,top_fraction=q,selected=len(ix),center_inside_image=int(inside.sum()),center_outside_image_or_behind=len(ix)-int(inside.sum()),camera_center=v['camera_center'].tolist(),K=K.tolist(),W2C=W.tolist(),rows_file=f'r8_14031_stop__{cam}__top10.csv.gz',plot_note='All selected centers, no downsampling. Image shows original full RGB and selected center overlay. Largest100 radius square outlines are screen bounds, not exact ellipse silhouettes.',row_indices=ix.tolist()))
 del a,v,xyz,uv,camera_xyz,tiles,order
 # Metric quantile curves: direct empirical percentiles, stopped vs baseline.
 dd=read(T/'distributions.json')['rows'];metrics=['camera_distance_m','longest_axis_m','opacity','radius_pixels'];labels=['카메라 거리 (m)','긴 축 (m)','불투명도','화면 반지름 (pixel)'];fig,axs=plt.subplots(2,4,figsize=(17,8));chosen=[]
 for qi,q in enumerate(c['top_fractions']):
  for j,(metric,label) in enumerate(zip(metrics,labels)):
   for key,lab,color in [('r8_14031_stop','중단 상태','#9c438a'),('base_LoD2_30000','기준선 30,000회','#317fa0')]:
    r=next(r for r in dd if r['state']==key and r['camera']==cam and r['top_fraction']==q and r['metric']==metric);chosen.append(r);axs[qi,j].plot([float(x) for x in r['quantiles']],[x for x in r['quantiles'].values()],'o-',label=lab,color=color)
   axs[qi,j].set(title=f'상위 {int(q*100)}% · {label}',xlabel='백분위',ylabel=label);axs[qi,j].grid(alpha=.2)
   if metric!='opacity':axs[qi,j].set_yscale('symlog',linthresh=.01 if metric=='longest_axis_m' else 1)
 axs[0,0].legend(fontsize=8);fig.tight_layout();save(fig,'top_distributions',chosen)
 # Top groups at five cameras: provenance x location heatmaps, same overlap-fraction scale.
 cells=read(T/'top_cells.json')['rows'];top5=read(ROOT/'stop_diagnostic/renders/summary.json')['top5']
 for q in c['top_fractions']:
  fig,axs=plt.subplots(5,1,figsize=(15,13),sharex=True);rr=[]
  for aa,view in zip(axs,top5):
   cc=[r for r in cells if r['state']=='r8_14031_stop' and r['camera']==view['camera'] and r['top_fraction']==q];rr+=cc;mat=np.array([r['overlap_fraction_of_all']*100 for r in cc]).reshape(4,16);im=aa.imshow(mat,vmin=0,vmax=100,aspect='auto',cmap='magma');aa.set(yticks=range(4),yticklabels=NAMES,title=view['camera']);
  axs[-1].set(xticks=range(16),xticklabels=[f'가로{x+1}\n높이{z+1}' for x in range(4) for z in range(4)]);fig.colorbar(im,ax=axs,location='right',label='해당 영상 전체 겹침의 %',fraction=.02);fig.suptitle(f'상위 5개 영상 · 상위 {int(q*100)}% 출신 × 자리');save(fig,f'top{int(q*100)}_five_view_cells',rr)
 gr=read(T/'pre_density_gradients.json')['rows'];growth=read(T/'growth_1000.json')['rows']
 for name,rr,value,title in [('pre_density_by_cell',gr,'fraction','밀도 제어 직전 문턱 이상 비율'),('growth_by_cell',growth,'net_change','1,000회 구간의 수 순변화')]:
  fig,axs=plt.subplots(4,1,figsize=(15,12),sharex=True);vmax=max(abs(r[value]) for r in rr if r[value] is not None);vmin=-vmax if name.startswith('growth') else 0
  for tag,aa in enumerate(axs):
   tt=[r for r in rr if r['tag']==tag];mat=np.array([r[value] if r[value] is not None else np.nan for r in tt]).reshape(7,16);im=aa.imshow(mat,vmin=vmin,vmax=vmax,aspect='auto',cmap='coolwarm' if vmin<0 else 'viridis');aa.set(yticks=range(7),yticklabels=range(8000,14001,1000),title=NAMES[tag],ylabel='구간 끝 / 반복')
  axs[-1].set(xticks=range(16),xticklabels=[f'가로{x+1}\n높이{z+1}' for x in range(4) for z in range(4)]);fig.colorbar(im,ax=axs,location='right',fraction=.02,label=title);fig.suptitle(title);save(fig,name,rr)
 print('HEAVY_FIGURES_COMPLETE',flush=True)
if __name__=='__main__':main()
