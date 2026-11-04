"""Complete lineage quantities, saved-distance simulation comparisons, report."""
from common import *
from stage1_prepare import v0_model
from scipy.spatial import cKDTree
import sys
def main():
 cfg();release=[];details=[];simulation=[];scope_comparison=[]
 for prior in ['ALS','LoD2']:
  stem='R1rep_b10__'+prior;root=O/'stage1'/stem;g=loadz(root/'gaussians.npz');row=loadz(root/'rows.npz');a=loadz(root/'attribution.npz');eligible=loadz(root/'released_currently_eligible.npz')['eligible'];case=g['case'].copy();case[eligible]=2
  raw=json.loads((root/'lineage/receipt.json').read_text());ret=json.loads((root/'lineage_returned/receipt.json').read_text());weights={tuple(k):v for k,v in zip(raw['groups'],raw['alpha_T_sums'])};returned={k[0]:v for k,v in zip(ret['groups'],ret['alpha_T_sums'])}
  original=json.loads((v0_model('R1rep_b10',prior)/'target_monitor/release_30000.json').read_text())['rows']
  seedregions=loadz(v0_model('R1rep_b10',prior)/'target_monitor/snapshot_30000.npz',['region'])['region'][g['init_id']]
  for old in original:
   m=(g['origin']==1)&(seedregions==old['region']);rel=m&(g['tag']==2);assert int(rel.sum())==old['released'] and int(m.sum())==old['prior_descendants']
   scope_comparison.append(dict(prior=prior,internal_seed_region=old['region'],FINALTRAIN_prior_descendants=old['prior_descendants'],FINALTRAIN_released=old['released'],inside_prior=int((m&g['inside_eval']).sum()),outside_prior=int((m&~g['inside_eval']).sum()),inside_released=int((rel&g['inside_eval']).sum()),outside_released=int((rel&~g['inside_eval']).sum()),same_group_and_count=True))
  for r in [0,1,2,4,9]:
   allm=(g['origin']==1)&(g['initial_judgment_region']==r);old=next((v for v in original if v['region']=={0:1,1:2,2:3,4:0}.get(r,-99)),None)
   for place,inside in [('inside',g['inside_eval']),('outside',~g['inside_eval'])]:
    m=allm&inside;rr=m&(g['tag']==2)
    for k in [0,1,2] if place=='inside' else [-1]:
     alpha=None if place=='outside' else returned.get(r,0) if k==2 else weights.get((r,k),0)-(returned.get(r,0) if k==1 else 0)
     if alpha is not None:assert alpha>=-1e-4
     release.append(dict(prior=prior,judgment_region=r,evaluation_scope=place,release_case=k,prior_descendants=int(m.sum()),released_descendants=int(rr.sum()),case_descendants=int((rr&(case==k)).sum()),alpha_T_sum=max(alpha,0) if alpha is not None else None))
  missing=np.flatnonzero(row['result_type']==3);tree=cKDTree(g['xyz']);labels=np.full(len(g['xyz']),3,'i1');labels[g['tag']==2]=2
  for i,near in zip(missing,tree.query_ball_point(row['xyz'][missing],.25,workers=2)):
   near=np.asarray(near,'i8');lab=labels[near].copy();att=g['tag'][near]==1;lab[att]=np.where(g['patch_ids'][g['target_index'][near[att]]]==row['source_index'][i],0,1)
   counts=np.bincount(lab,minlength=5);details.append(dict(prior=prior,row_index=int(i),original_cell=int(row['old_cell'][i]),judgment_region=int(row['judge_region'][i]),near_025m_count=len(near),same_patch=int(counts[0]),other_patch=int(counts[1]),released=int(counts[2]),background=int(counts[3]),opacity_median=float(np.median(g['opacity'][near])) if len(near) else None,clear_train_views=int(a['unoccluded_positive_depth_views'][i]),zero_depth_unknown_views=int(a['unknown_zero_depth_views'][i])))
  for family in ['FINALTRAIN_30000','judgment_mesh',*['sim_'+s for s in cfg()['stage1']['simulations']]]:
   path=O/'scores'/f'{stem}__{family}'/'values.json' if family.startswith('sim_') else score_dir('R1rep_b10',prior,family)/'values.json'
   if not path.exists():continue
   z=json.loads(path.read_text());change=json.loads((O/'simulations'/f'{stem}__{family}'/'point_cloud.json').read_text()) if family.startswith('sim_') else {}
   for cell in [-1,0,1,2,4]:
    v=z['scene'] if cell==-1 else next(r for r in z['cells'] if r['cell']==cell)
    simulation.append({**v,'site':'R1rep_b10','prior':prior,'method':family,'cell_basis':'scene' if cell==-1 else 'original','cell':cell,'small':'적음' if v['n_gt']<1000 else '', 'removed':change.get('removed',0),'moved':change.get('moved',0)})
 table('stage1/release_scope_and_contribution',release);table('stage1/finaltrain_scope_comparison',scope_comparison);table('stage1/missing_point_neighborhoods',details);table('stage1/simulation_table',simulation)
 lines=['# 단계 1: R1 결과 면의 계보와 모의','', 'scientific_verdict: null. 모의는 저장된 모델에 한 번 적용한 위쪽 짐작이며 학습 성능이 아니다.','', '| 항공 LiDAR 기존 칸 실패 점 | 같은 패치 | 다른 패치 | 풀림 | 배경 | 확인 불가 |','|---|---:|---:|---:|---:|---:|']
 data=json.loads((D/'tables/stage1/R1rep_b10__ALS_attribution.json').read_text())['rows']
 for cell in [2,4]:
  counts=[sum(r['n_gt'] for r in data if r['cell_basis']=='original' and r['cell']==cell and r['judgment_region']==-1 and r['result_type'] in [1,2,3,4] and r['binding']==label) for label in range(5)];lines.append('| '+str(cell)+' | '+' | '.join(map(str,counts))+' |')
 lines+=['','| 사전 정보 | 평가 안 풀림 | 현재 후보 있음 | 계보 연결 / 참값 행 |','|---|---:|---:|---:|']
 for prior in ['ALS','LoD2']:
  p=O/'stage1'/('R1rep_b10__'+prior);q=json.loads((p/'qualification.json').read_text());j=json.loads((p/'join.json').read_text());lines.append(f"| {prior} | {q['released_in_eval']} | {q['released_now_with_valid_candidate']} | {j['attributed']} / {j['rows']} |")
 lines+=['','가: 면을 따라 0.5 m 안 목표 없음. 나: 후보는 있으나 모두 구간에서 0.5 m 초과. 현재 유효 후보가 생긴 풀림은 별도 셋째 항목이며 나에서 뺐다. alpha×T는 원 학습 시점의 모든 화소 합으로, 여러 시점의 중복 가시성을 유지한다. 범위 밖 기여는 요구 대상이 아니므로 계산하지 않았다.','', '| 사전 정보 | 방법 | 칸 2 완전성 % | 칸 4 완전성 % | 장면 정확성 % |','|---|---|---:|---:|---:|']
 for prior in ['ALS','LoD2']:
  for method in ['FINALTRAIN_30000','judgment_mesh',*['sim_'+s for s in cfg()['stage1']['simulations']]]:
   rr=[r for r in simulation if r['prior']==prior and r['method']==method]
   def number(cell,metric):
    r=next((r for r in rr if r['cell']==cell),None);return '확인 불가' if r is None or r[metric] is None else f"{r[metric]*100:.3f}"
   lines.append(f"| {prior} | {method} | {number(2,'completeness')} | {number(4,'completeness')} | {number(-1,'accuracy')} |")
 lines+=['','GT는 셈·그림에만 사용했다. 제거·이동은 초기 출신, 현재 꼬리표, PREP 평가 사각형, 잠근 목표만으로 선택했다.','면 있는 점의 계보는 원 렌더러의 최대 alpha×T와 깊이 0.25 m 대응 시점의 최빈 번호다. 면 없음 점은 참값 투영 화소의 실제 기여자를 전경 가림까지 포함해 세며, 가림 없이 보는 시점 수와 분리했다. TSDF 꼭짓점의 유일한 부모라는 뜻은 아니다. V0의 최초 풀림 상태는 같은 init_id 계보가 처음 풀림으로 보이는 7,000·15,000·30,000회이며 고유 부모의 사건 시각은 확인 불가다.','면 없음: 자기 기둥에 면이 없고 원 채점 거리도 τ 밖인 점. τ 안 비율은 원 표 4와 0.1 %p 이내로 확인했다. 벽 앞·뒤는 최빈 가우시안을 지지한 첫 학습 시점의 카메라 깊이 차, 지붕은 높이 방향이다. 벽 시점 대응이 없으면 결과 종류 4(앞·뒤 확인 불가)로 별도 보존했다.','저장 깊이 0인 시점은 가림 없이 보인다고 추정하지 않고 확인 불가로 셌다. 유효 깊이가 참값 투영 깊이보다 0.25 m 이상 앞서지 않은 시점만 clear에 포함했다.','원본 참값 행마다 꼬리표·거리·가우시안 번호·다른 목표 높이 차·최초 저장 상태는 stage1/*/attribution.npz; 기둥·결과 종류는 rows.npz; 모의의 선택 수와 해시는 simulations/*/point_cloud.json.']
 (D/'단계1_보고.md').write_text('\n'.join(lines)+'\n')
if __name__=='__main__':main()
