"""CPU classification of immutable events and checkpoint descendants."""
from common import *
from stage1_prepare import eval_mask,v0_model
import sys
sys.path.append('/repo/src/phd/forks/GeoGS-conf-guided-v1-r24')
from release_search import TangentTree
def main(site,prior,rule,stage):
 cfg();stage=int(stage);name=f'rlog_{prior}_s0' if stage==2 else f'rl_{rule}_{prior}_s0';key=f'{site}__{prior}__{name}';run=O/'runs'/site/name;rec=json.loads((run/'receipt.json').read_text());mon=Path(rec['attempts'][-1]['model'])/'target_monitor';end=15000 if stage==2 else 30000
 target=loadz(FT/'targets'/f'{site}__{prior}.npz');snap=loadz(mon/f'snapshot_{end}.npz');ids=snap['patch_ids'];norm=snap['patch_normal'].astype(float);anchor=snap['patch_anchor'].astype(float);width=(np.float32(1.96)*snap['patch_sigma']).astype(float)
 # Candidate geometry uses the original float64 target points, as r23 does.
 anchor=target['target'][ids].astype(float);norm/=np.linalg.norm(norm,axis=1)[:,None]
 tree=TangentTree(anchor,norm,width,ids);parts=[];metadata=[]
 for file in sorted((mon/'release_events').glob('*.npz')):
  a=loadz(file);meta=json.loads(file.with_suffix('.json').read_text());n=len(a['event_id']);d,e,j=tree.query(a['xyz']);old=a['previous_target_index'];valid=old>=0;nearest_region=target['judge_region'][ids[j]];prev_region=np.full(n,-1,'i1');prev_region[valid]=target['judge_region'][ids[old[valid]]]
  diff=np.full(n,np.nan);diff[valid]=((anchor[j[valid]]-anchor[old[valid]])*norm[old[valid]]).sum(1)
  delta=a['xyz'].astype(float)-a['previous_check_xyz'].astype(float);hn=np.full(n,np.nan);tn=hn.copy();hn[valid]=(delta[valid]*norm[old[valid]]).sum(1);tn[valid]=np.linalg.norm(delta[valid]-hn[valid,None]*norm[old[valid]],axis=1);a['movement_normal_m']=hn;a['movement_tangent_m']=tn
  angle=np.rad2deg(np.arccos(np.clip(abs((a['parent_disk_normal']*norm[j]).sum(1)),-1,1)));birth=np.where(a['birth_iteration']==0,0,np.where(a['birth_iteration']==meta['iteration'],a['birth_kind'],3))
  a.update(iteration=np.full(n,meta['iteration'],'i4'),action=np.full(n,{'release':0,'pull':1,'delete':2}[meta['action']],'i1'),cause=np.full(n,0 if meta['cause']=='density_control' else 1,'i1'),birth_category=birth,case=np.where(d<=.5,1,0).astype('i1'),nearest_target_index=j,nearest_tangent_m=d,nearest_normal_excess_m=e,previous_judgment=prev_region,nearest_judgment=nearest_region,target_normal_height_difference_m=diff,parent_normal_angle_degrees=angle,inside_eval=eval_mask(a['xyz'],site));parts.append(a);metadata.append(dict(path=str(file),sha256=sha(file),**meta))
 fields={k:np.concatenate([a[k] for a in parts]) for k in parts[0]} if parts else {};root=O/'events'/key;root.mkdir(parents=True,exist_ok=True)
 releases=[];desc=[];maxid=int(fields['event_id'].max())+1 if fields else 0
 for it in [7000,15000,30000]:
  file=mon/f'snapshot_{it}.npz'
  if not file.exists():continue
  z=loadz(file);r=loadz(mon/f'release_snapshot_{it}.npz');inside=eval_mask(z['xyz'],site);released=z['target_tag']==2;seedreg=z['region'][z['init_id']];vmon=v0_model(site,prior)/'target_monitor';old=json.loads((vmon/f'release_{it}.json').read_text())
  weights=np.bincount(r['rl_event'][r['rl_event']>=0],minlength=maxid);iw=np.bincount(r['rl_event'][(r['rl_event']>=0)&inside],minlength=maxid)
  if fields:fields[f'descendants_{it}']=weights[fields['event_id']];fields[f'inside_descendants_{it}']=iw[fields['event_id']]
  for region in [0,1,2,3]:
   m=(z['origin']==1)&(seedreg==region);previous=next(q for q in old['rows'] if q['region']==region)
   releases.append(dict(site=site,prior=prior,rule=rule,iteration=it,internal_seed_region=region,judgment_region={0:4,1:0,2:1,3:2}[region],prior_descendants=int(m.sum()),released=int((m&released).sum()),inside_released=int((m&released&inside).sum()),outside_released=int((m&released&~inside).sum()),V0_released=previous['released'],difference=int((m&released).sum())-previous['released']))
 if fields:
  savez(root/'events.npz',**fields)
  for action in [0,1,2]:
   for case in [0,1]:
    for birth in [0,1,2,3]:
     for cause in [0,1]:
      m=(fields['action']==action)&(fields['case']==case)&(fields['birth_category']==birth)&(fields['cause']==cause)
      desc.append(dict(site=site,prior=prior,rule=rule,action=action,case=case,birth=birth,cause=cause,events=int(m.sum()),descendants_15000=int(fields['descendants_15000'][m].sum()),inside_descendants_15000=int(fields['inside_descendants_15000'][m].sum())))
 table(('stage2/' if stage==2 else 'runs/'+key+'/')+key+'_events',desc);table(('stage2/' if stage==2 else 'runs/'+key+'/')+key+'_release',releases)
 curve=[json.loads(x) for x in (mon/'curve.jsonl').read_text().splitlines()];base=[json.loads(x) for x in (v0_model(site,prior)/'target_monitor/curve.jsonl').read_text().splitlines()]
 def times(rows):return {b['iteration']:(b['elapsed_seconds']-a['elapsed_seconds'])/(b['iteration']-a['iteration']) for a,b in zip(rows[:-1],rows[1:]) if b['iteration']<=end and a['iteration']>=100 and a['iteration'] not in [7000,15000]}
 x,y=times(curve),times(base);ratios=[x[k]/y[k] for k in x.keys()&y.keys() if y[k]>0]
 overhead=float(np.median(ratios)) if ratios else None
 dump(root/'receipt.json',dict(at=now(),source_model=str(mon.parent),stage=stage,site=site,prior=prior,rule=rule,events=sum(m['count'] for m in metadata),raw_batches=metadata,raw_event_directory=str(mon/'release_events'),median_iteration_ratio_vs_V0=overhead,ratio_confounded_by_concurrent_render_and_CPU=True,buffering='one compressed array per check batch, never one file per Gaussian',birth_codes={0:'initial seed',1:'current clone',2:'current split',3:'preexisting'},action_codes={0:'release',1:'pull',2:'delete'},case_codes={0:'no tangent target within 0.5 m',1:'tangent target within 0.5 m; all admissible targets exceed interval by 0.5 m'},scientific_verdict=None))
 print('EVENT_SUMMARY',key,sum(m['count'] for m in metadata),overhead,flush=True)
def summary():
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib import font_manager
 for f in Path('/fonts').glob('*.ttc'):font_manager.fontManager.addfont(str(f))
 plt.rcParams['font.family']='Noto Sans CJK JP';fig1,ax1=plt.subplots(2,1,figsize=(12,7));fig2,ax2=plt.subplots(1,2,figsize=(13,6));meta=[];lines=['# 단계 2: 풀림 사건 기록','', 'scientific_verdict: null. 원본은 payload의 receipt.json에 경로와 각 SHA256을 기록했다.','', '| 사전 정보 | 사건 수 | 반복 시간 비율 중앙값 |','|---|---:|---:|']
 for j,prior in enumerate(['ALS','LoD2']):
  root=O/'events'/f'R1rep_b10__{prior}__rlog_{prior}_s0'
  if not (root/'receipt.json').exists():lines.append(f'| {prior} | 결과 없음 | 확인 불가 |');continue
  rec=json.loads((root/'receipt.json').read_text());z=loadz(root/'events.npz');it=z['iteration'];u,n=np.unique(it,return_counts=True);ax1[j].bar(u,n,width=70);density=np.unique(it[z['cause']==0]);ax1[j].vlines(density,0,max(n)*.06,color='red',linewidth=.5);ax1[j].set(title=prior,xlabel='반복 (빨간 표식: 밀도 제어 사건)',ylabel='풀림 사건 수')
  for k,col in [(0,'#d95f02'),(1,'#1b9e77')]:
   take=z['case']==k;ax2[j].scatter(z['xyz'][take,0],z['xyz'][take,1],c=col,s=1,label='가' if k==0 else '나')
  ax2[j].set(title=prior,xlabel='local X (m)',ylabel='local Y (m)');ax2[j].set_aspect('equal');ax2[j].legend();meta.append(dict(path=str(root/'events.npz'),sha256=sha(root/'events.npz')));lines.append(f"| {prior} | {rec['events']} | {rec['median_iteration_ratio_vs_V0']:.3f} |")
 for fig,name in [(fig1,'event_iterations'),(fig2,'event_locations')]:
  p=D/'figures/stage2'/name;p.parent.mkdir(parents=True,exist_ok=True);fig.tight_layout();fig.savefig(p.with_suffix('.png'),dpi=180);plt.close(fig);dump(p.with_suffix('.json'),dict(sources=meta,crs='EPSG:25832 inherited local shift',scientific_verdict=None))
 lines+=['','시간 비교에는 동시에 실행한 계보 렌더·CPU 작업의 영향이 섞여 있다. 사건은 점마다 쓰지 않고 점검마다 배열로 모아 저장했다. 7,000·15,000회 사건 계보 자손 수는 평가 범위 안·밖을 나눴다.','기본값·기록 on/off의 100회 Adam/복제/분할/정리 상태 동등성과 당김·지움·섞음 단위 점검은 verification에 있다.']
 (D/'단계2_보고.md').write_text('\n'.join(lines)+'\n')
if __name__=='__main__':summary() if sys.argv[1]=='summary' else main(*sys.argv[1:])
