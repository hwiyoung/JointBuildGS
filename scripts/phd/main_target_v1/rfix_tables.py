"""Factual tables and fixed-view figures from completed renderer checks."""
import csv,math,gc,shutil
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from common import *
ROOT=OUT/'rfix';DEST=DOC/'rfix';TAB=DEST/'tables';FIG=DEST/'figures'
LABEL={'base_ALS_30000':'기준선 ALS 30,000','base_LoD2_30000':'기준선 LoD2 30,000','r8_ALS_30000':'r8 ALS 30,000','r7_LoD2_30000':'r7 LoD2 30,000','r8_LoD2_stop':'r8 LoD2 14,030','image_only_2DGS_30000':'2DGS 영상만 30,000','GeoGS_ALS_30000':'GeoGS ALS 30,000','GeoGS_LoD2_30000':'GeoGS LoD2 30,000'}
def table(name,rows):
 dump(TAB/(name+'.json'),dict(rows=rows,scientific_verdict=None))
 if not rows:return
 keys=list(rows[0]);fmt=lambda x:json.dumps(x,ensure_ascii=False) if isinstance(x,(dict,list)) else ('' if x is None else x)
 with (TAB/(name+'.csv')).open('w',newline='') as f:
  w=csv.DictWriter(f,keys);w.writeheader();w.writerows({k:fmt(r.get(k)) for k in keys} for r in rows)
 lines=['| '+' | '.join(keys)+' |','|'+'|'.join(['---']*len(keys))+'|']
 lines+=['| '+' | '.join(str(fmt(r.get(k))).replace('|','/').replace('\n',' ') for k in keys)+' |' for r in rows]
 (TAB/(name+'.md')).write_text('\n'.join(lines)+'\n')
def fig(name,f,data):
 f.savefig(FIG/(name+'.png'),dpi=150,bbox_inches='tight');f.savefig(FIG/(name+'.pdf'),bbox_inches='tight');plt.close(f);dump(FIG/(name+'.json'),dict(data=data,scientific_verdict=None))
def quant(a):
 a=np.asarray(a);f=a[np.isfinite(a)];return dict(n=len(a),nonfinite=int(len(a)-len(f)),q00_q25_q50_q75_q95_q100=np.quantile(f,[0,.25,.5,.75,.95,1]).tolist() if len(f) else None)
def main():
 TAB.mkdir(parents=True,exist_ok=True);FIG.mkdir(parents=True,exist_ok=True)
 fonts=list(Path('/fonts').glob('*Regular.ttc'))
 if fonts:plt.rcParams['font.family']=FontProperties(fname=str(fonts[0])).get_name()
 plt.rcParams['axes.unicode_minus']=False
 cfg=json.loads((CFG/'rfix.json').read_text());summaries=[];views=[];grads=[];group_rows=[];missing=[];top=[]
 for state in cfg['states']:
  key=state['key'];path=ROOT/'states'/key/'result.json';gp=ROOT/'gradients'/key/'result.json'
  if not path.exists() or not gp.exists():missing.append(key);continue
  data=json.loads(path.read_text());g=json.loads(gp.read_text());records=data['records'];b=np.array([r['performance'][1]['overlaps'] for r in records]);a=np.array([r['performance'][2]['overlaps'] for r in records]);bb=np.array([r['performance'][1]['binning_bytes'] for r in records]);ab=np.array([r['performance'][2]['binning_bytes'] for r in records]);bt=np.array([r['performance'][1]['seconds_including_accounting'] for r in records]);at=np.array([r['performance'][2]['seconds_including_accounting'] for r in records]);N=data['gaussians']
  deltas=[m['fixed_max_abs'] for r in g['rows'] for m in r['parameters'].values()];jitter=[m['jitter_max_abs'] for r in g['rows'] for m in r['parameters'].values()]
  summaries.append(dict(state=key,gaussians=N,render_views=len(records),render_pass=sum(r['pass_'] for r in records),max_render_abs=max(m['max_abs'] for r in records for m in r['comparison'].values()),radii_all_equal=all(r['comparison']['radii']['pass_'] for r in records),gradient_views=len(g['rows']),gradient_pass=sum(r['pass_'] for r in g['rows']),gradient_comparisons=len(deltas),gradient_comparisons_failed=sum(not m['pass_'] for r in g['rows'] for m in r['parameters'].values()),max_gradient_abs=max(deltas),max_original_gradient_repeat_abs=max(jitter),original_overlaps_sum=int(b.sum()),fixed_overlaps_sum=int(a.sum()),overlaps_ratio=float(a.sum()/b.sum()),original_overlap_median=float(np.median(b)),fixed_overlap_median=float(np.median(a)),original_overlap_max=int(b.max()),fixed_overlap_max=int(a.max()),original_buffer_max_bytes=int(bb.max()),fixed_buffer_max_bytes=int(ab.max()),original_peak_allocated_max=max(r['performance'][1]['peak_allocated_bytes'] for r in records),fixed_peak_allocated_max=max(r['performance'][2]['peak_allocated_bytes'] for r in records),original_render_median_s=float(np.median(bt)),fixed_render_median_s=float(np.median(at))))
  for vi,r in enumerate(records):
   views.append(dict(state=key,camera=r['camera'],width=r['width'],height=r['height'],burst_pairs=r['pairs'],burst_pair_fraction=r['pairs']/N,burst_overlaps=r['burst_overlaps'],burst_overlap_fraction=r['burst_overlaps']/int(b[vi]) if b[vi] else None,burst_color_contributors=r['burst_color_contributors'],burst_color_fraction=r['burst_color_contributors']/r['pairs'] if r['pairs'] else None,original_overlaps=int(b[vi]),fixed_overlaps=int(a[vi]),original_buffer_bytes=int(bb[vi]),fixed_buffer_bytes=int(ab[vi]),original_render_s=float(bt[vi]),fixed_render_s=float(at[vi]),outputs_pass=r['pass_']))
  for variant,col in [('original',b),('fixed',a)]:
   for rank,i in enumerate(sorted(range(len(col)),key=lambda i:(-col[i],records[i]['camera']))[:5],1):top.append(dict(state=key,variant=variant,rank=rank,camera=records[i]['camera'],overlaps=int(col[i]),buffer_bytes=int((bb if variant=='original' else ab)[i])))
  for r in g['rows']:
   for name,m in r['parameters'].items():grads.append(dict(state=key,camera=r['camera'],parameter=name,original_repeat_max_abs=m['jitter_max_abs'],fixed_max_abs=m['fixed_max_abs'],relative_l2=m['relative_l2'],different_rows=m['different_rows'],pass_=m['pass_'],worst_rows=m['worst_rows']))
  f,axes=plt.subplots(3,1,figsize=(12,9),sharex=True);x=np.arange(1,204)
  for ax,orig,fix,label in [(axes[0],b/1e6,a/1e6,'가우시안–타일 겹침 (백만 개)'),(axes[1],bb/2**30,ab/2**30,'정렬 버퍼 (GiB)'),(axes[2],bt*1000,at*1000,'렌더 시간 (ms)')]:ax.plot(x,orig,label='원본 두 번째 실행',lw=1);ax.plot(x,fix,label='타일 등록 고침',lw=1);ax.set_ylabel(label);ax.grid(alpha=.2);ax.legend()
  axes[0].set_title(LABEL[key]);axes[-1].set_xlabel('고정 학습 영상 순서 (이름순)');fig(key+'_load',f,dict(state=key,views=[r['camera'] for r in records],before_overlaps=b.tolist(),after_overlaps=a.tolist(),before_buffer=bb.tolist(),after_buffer=ab.tolist(),before_seconds=bt.tolist(),after_seconds=at.tolist()))
  params=list(g['rows'][0]['parameters']);ratio=np.array([[m['fixed_max_abs']/m['jitter_max_abs'] if m['jitter_max_abs']>0 else (0 if m['fixed_max_abs']==0 else np.inf) for m in r['parameters'].values()] for r in g['rows']]);shown=np.minimum(ratio,4);f,ax=plt.subplots(figsize=(9,10));im=ax.imshow(shown,vmin=0,vmax=4,cmap='coolwarm',aspect='auto');ax.set_xticks(range(len(params)),params,rotation=35,ha='right');ax.set_yticks(range(30),[r['camera'] for r in g['rows']],fontsize=6);ax.set_title(LABEL[key]+'\n기울기 최대 차 / 원본 두 번 실행 최대 차');f.colorbar(im,ax=ax,label='비율 (4 이상은 같은 색; 1 초과 기준 미달)');fig(key+'_gradient',f,dict(state=key,rows=g['rows'],ratio=[[None if not np.isfinite(v) else float(v) for v in r] for r in ratio],infinite_ratio_count=int(np.isinf(ratio).sum()),display_clip=4,acceptance_limit=1))
  for p in (ROOT/'states'/key/'fixed_views').glob('*.npz'):
   z=np.load(p);f,axes=plt.subplots(1,3,figsize=(14,4));ims=[z['gt'],z['before'],z['after']]
   for ax,v,title in zip(axes,ims,['학습 사진','원본','타일 등록 고침']):ax.imshow(np.clip(v.transpose(1,2,0),0,1));ax.set_title(title);ax.axis('off')
   f.suptitle(LABEL[key]+' · '+p.stem);fig(key+'_'+p.stem,f,dict(state=key,camera=p.stem,input=str(p),input_sha256=sha(p),maximum_rgb_difference=float(abs(z['before']-z['after']).max()),color_range=[0,1]))
  cols=['center_depth','outside_distance_px','disc_nearest_depth','disc_farthest_depth','aabb_d','sum_w','max_w','radius','camera_distance_m','tag','xy_bin','height_bin','within_camera30','center_inside','nearest_camera_distance_m'];parts={k:[] for k in cols}
  for p in sorted((ROOT/'states'/key/'bursts').glob('*.npz')):
   with np.load(p) as z:
    for k in cols:parts[k].append(z[k].reshape(-1))
  vals={k:np.concatenate(v) for k,v in parts.items()};del parts;code=vals['tag'].astype('i8')*32+vals['xy_bin']*8+vals['height_bin']*2+(vals['nearest_camera_distance_m']<=30).astype('i8')
  for value in np.unique(code):
   mask=code==value;i=np.flatnonzero(mask)[0];group_rows.append(dict(state=key,tag=int(vals['tag'][i]),xy_bin=int(vals['xy_bin'][i]),height_bin=int(vals['height_bin'][i]),within_camera30=bool(vals['nearest_camera_distance_m'][i]<=30),pairs=int(mask.sum()),center_inside=int(vals['center_inside'][mask].sum()),color_contributing=int((vals['sum_w'][mask]>0).sum()),statistics={k:quant(vals[k][mask]) for k in cols[:9]+['nearest_camera_distance_m']}))
  f,axes=plt.subplots(1,2,figsize=(11,4));positive=vals['max_w']>0;axes[0].hist(vals['center_depth'],bins=np.linspace(0,300,100),color='#366aa6');axes[0].set_xlabel('중심 카메라 깊이 (m; 0~300 표시)');axes[0].set_ylabel('터진 가우시안–영상 쌍');axes[1].hist(np.log10(vals['max_w'][positive]),bins=80,color='#ce7635');axes[1].set_xlabel('실제 최대 색 기여 log10(alpha×T)');axes[1].set_ylabel('쌍 수');axes[1].set_title(f'색 기여 0: {int((~positive).sum()):,}쌍');f.suptitle(LABEL[key]);fig(key+'_burst',f,dict(state=key,total_pairs=len(positive),positive_pairs=int(positive.sum()),zero_pairs=int((~positive).sum()),center_depth=quant(vals['center_depth']),disc_nearest=quant(vals['disc_nearest_depth']),disc_farthest=quant(vals['disc_farthest_depth']),aabb_d=quant(vals['aabb_d']),max_w=quant(vals['max_w']),raw_pairs=str(ROOT/'states'/key/'bursts')));del vals,code;gc.collect()
 table('state_summary',summaries);table('per_view',views);table('load_top5',top);table('gradient_comparisons',grads);table('burst_groups',group_rows)
 for label in ['target','imageonly','geogs']:
  p=ROOT/'units'/label/'result.json'
  if p.exists():table('unit_'+label,json.loads(p.read_text())['rows'])
 dump(DEST/'completion.json',dict(at=stamp(),states_completed=len(summaries),missing=missing,forward_pairs=sum(s['render_views'] for s in summaries),gradient_pairs=sum(s['gradient_views'] for s in summaries),formal_pass=not missing and all(s['render_pass']==203 and s['gradient_pass']==30 and s['radii_all_equal'] and s['overlaps_ratio']<1 for s in summaries),scientific_verdict=None));print('RFIX_TABLES',len(summaries),missing,flush=True)
if __name__=='__main__':main()
