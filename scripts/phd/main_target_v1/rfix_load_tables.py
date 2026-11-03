"""Expose every recorded per-view allocation alongside overlaps, bytes and time."""
from rfix_tables import *
from matplotlib import font_manager
def main():
 for p in Path('/fonts').glob('*Regular.ttc'):
  font_manager.fontManager.addfont(str(p));plt.rcParams['font.family']=FontProperties(fname=str(p)).get_name();break
 plt.rcParams['axes.unicode_minus']=False
 cfg=json.loads((CFG/'rfix.json').read_text());rows=[];datasets={}
 for s in cfg['states']:
  d=json.loads((ROOT/'states'/s['key']/'result.json').read_text());datasets[s['key']]=d
  for r in d['records']:
   a,b=r['performance'][1:];rows.append(dict(state=s['key'],camera=r['camera'],width=r['width'],height=r['height'],original_overlaps=a['overlaps'],fixed_overlaps=b['overlaps'],original_buffer_bytes=a['binning_bytes'],fixed_buffer_bytes=b['binning_bytes'],original_peak_allocated_bytes=a['peak_allocated_bytes'],fixed_peak_allocated_bytes=b['peak_allocated_bytes'],original_peak_reserved_bytes=a['peak_reserved_bytes'],fixed_peak_reserved_bytes=b['peak_reserved_bytes'],original_seconds=a['seconds_including_accounting'],fixed_seconds=b['seconds_including_accounting']))
 table('per_view_full_load',rows)
 ymax=max(max(r['original_peak_allocated_bytes'],r['fixed_peak_allocated_bytes']) for r in rows)/2**30*1.05
 for key,d in datasets.items():
  ours=[r for r in rows if r['state']==key];f,ax=plt.subplots(figsize=(11,4));x=np.arange(1,204);ax.plot(x,[r['original_peak_allocated_bytes']/2**30 for r in ours],label='원본 두 번째 실행');ax.plot(x,[r['fixed_peak_allocated_bytes']/2**30 for r in ours],label='타일 등록 고침');ax.set_ylim(0,ymax);ax.set_xlabel('고정 학습 영상 순서 (이름순)');ax.set_ylabel('최대 GPU 할당 (GiB)');ax.set_title(LABEL[key]);ax.legend();ax.grid(alpha=.2);fig(key+'_gpu_memory',f,dict(rows=ours,shared_ymax_GiB=ymax))
 print('RFIX_FULL_LOAD_TABLES',len(rows),flush=True)
if __name__=='__main__':main()
