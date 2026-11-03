"""Stage 0: exact saved-state inventory and source-index/target-scope audit."""
from common import *
def paths(site,prior,family):
 if family in ['r7','r8']:
  stem=f'tg_{site}_{prior}_s0_{family}'
  return [TG/family/'runs'/stem/'model',TG/'r7_continue'/('lod2_retry' if prior=='LoD2' else 'attempt2')/'runs'/stem/'model'] if family=='r7' else [TG/'r8/runs'/stem/'model',TG/'r8_recorded_continue/runs'/stem/'model']
 task,res={'baseline':('main_stage3_v1/PHD-MAIN-STAGE3-v1',f'nojudge_{prior}_s0'),
 '2DGS':('main_baselines_v1/PHD-MAIN-BASELINES-v1','imgonly_2dgs_s0'),
 'GeoGS':('main_fix_v1/PHD-MAIN-FIX-v1','trust_LoD2_fix1') if prior=='LoD2' else ('main_baselines_v1/PHD-MAIN-BASELINES-v1','geogs_ALS_fix1'),
 'CDGS':('main_fill_v1/PHD-MAIN-FILL-v1',f'cdgsnofit_{prior}_s0')}[family]
 ans=[PH/task/'runs'/site/res/'model']
 if family=='baseline' and site=='B173nb_b10':ans.append(TG/'r7/baselines'/f'base7k_{site}_{prior}_s0/model')
 return ans
def main():
 start=time.monotonic();cfg();rows=[];models=[];scopes=[];fusion=[]
 for site in SITES:
  for prior in ['LoD2','ALS']:
   for family in ['r7','r8','baseline','GeoGS','2DGS','CDGS']:
    records=[]
    for model in paths(site,prior,family):
     if not model.exists():continue
     receipt=model.parent/'receipt.json';meta=json.loads(receipt.read_text()) if receipt.exists() else {}
     source=meta.get('source');image=meta.get('image');seed=meta.get('seed')
     if family in ['r7','r8']:
      source=f'/repo/src/phd/forks/GeoGS-conf-guided-v1-r{21 if family=="r7" else 22}';image='jointbuildgs:geogs-conf-guided-v1';seed=0
     elif family=='baseline' and not source:
      source='/repo/src/phd/forks/GeoGS-conf-guided-v1-r21';image='jointbuildgs:geogs-conf-guided-v1';seed=0
     for it in [7000,15000,30000]:
      ply=model/f'point_cloud/iteration_{it}/point_cloud.ply'
      if not ply.is_file():continue
      rec=dict(site=site,prior=prior,family=family,iteration=it,model=str(model),ply=str(ply),saved_bytes=ply.stat().st_size,
       rerender_state_present=True,renderer=source or '확인 불가',image=image,seed=seed,
       renderer_status='r21/r22: 고친 뒤' if family in ['r7','r8'] else '별도 구현; TARGET 수정 전후 비교에 해당 없음',
       judgment='TARGET r7 고정 판단; JUDGEAPPLY 이전' if family in ['r7','r8'] else '판단 사용 안 함',
       provenance=str(receipt) if receipt.exists() else '학습 실행 스크립트',provisional=family=='r8')
      records.append(rec);models.append(rec)
    rows.append(dict(site=site,prior=prior,family=family,iterations=sorted(set(x['iteration'] for x in records)),status='있음' if records else '없음',records=records))
   p=TG/'stage0_r1/inputs'/f'{site}_{prior}.npz';cp=JA/'core_points'/f'{site}__{prior}.npz';tp=TG/'r8/targets'/f'{site}_{prior}.npz'
   row=dict(site=site,prior=prior,stage0_path=str(p),r8_target_path=str(tp),r8_target_present=tp.exists())
   if p.exists():
    z=loadz(p,['centre','normal','area','in_eval','kind']);ev=z['in_eval'];row.update(stage0_patches=len(ev),outside_patches=int((~ev).sum()),outside_area_m2=float(z['area'][~ev].sum()))
    if cp.exists():
     j=loadz(cp,['source_index','centre','area','patch_id','region','normal']);ix=j['source_index']
     ok=np.array_equal(z['centre'][ix],j['centre']) and np.array_equal(z['area'][ix],j['area']) and ev[ix].all()
     row.update(join_count=len(ix),join_source_max=int(ix.max()),source_index_correct=bool(ok),unique_patch_id=len(np.unique(j['patch_id']))==len(ix),core_sha256=sha(cp))
     assert ok and row['unique_patch_id']
     fusion.append(dict(site=site,prior=prior,status='있음',n=len(ix),source=str(cp),field='region[4]',region_codes=np.unique(j['region'][4]).tolist()))
    else:fusion.append(dict(site=site,prior=prior,status='없음',n=0,source=str(cp),field='region[4]'))
    if tp.exists():
     t=loadz(tp);assert np.array_equal(t['centre'],z['centre'])
     valid=(t['region']>=0)&(t['region']!=5)&np.isfinite(t['h'])&np.isfinite(t['sigma'])&(t['sigma']>0)
     seeds=loadz(TG/'r8/stage1'/f'{site}_{prior}/seeds.npz',['patch']);pid=np.unique(seeds['patch'][seeds['patch']>=0]);outside_ids=pid[~ev[pid]]
     row.update(outside_valid_target_patches=int((valid&~ev).sum()),outside_valid_target_area_m2=float(t['area'][valid&~ev].sum()),outside_seeded_patches=len(outside_ids),outside_seeded_area_m2=float(t['area'][outside_ids].sum()),target_sha256=sha(tp),training_uses_outside=bool(len(outside_ids)))
   else:row['status']='없음'
   scopes.append(row)
 table('stage0_inventory',rows);table('stage0_patch_scope',scopes);table('stage0_fusion',fusion);dump(O/'inventory.json',dict(rows=models,scientific_verdict=None))
 lines=['# 단계 0 목록','', '[이 발주에서 냄] · 학습 없음 · scientific_verdict: null','', 'PH = 외부 `JointBuildGS-artifacts/phase-payloads/phd`. 정확한 경로·렌더러·씨앗·상태는 `tables/stage0_inventory.json`(48줄)에 기록했다. 숫자는 실제 PLY가 있는 반복 횟수다.','', '| 지역·사전 정보 | r7 | r8 | 기준선 | GeoGS | 2DGS | CDGS |','|---|---|---|---|---|---|---|']
 for site in SITES:
  for prior in ['LoD2','ALS']:
   rr=[x for x in rows if x['site']==site and x['prior']==prior];lines.append('| '+LABELS[site]+' '+prior+' | '+' | '.join(','.join(str(i) for i in x['iterations']) or '없음' for x in rr)+' |')
 lines+=['','2DGS는 사전 정보 없는 동일 저장 결과를 두 사전 정보의 평가에 연결한다. GeoGS는 고친 공식 구현, CDGS는 7장 숫자 작업의 크기 맞추기 생략 판이다. r7/r8 씨앗은 0. 나머지는 각 receipt의 seed를 기록했다. CDGS 학습 씨앗은 공식 코드에서 고정되지 않았음(분할만 42).','', 'r8 LoD2 30,000회는 없다. 기록 연장은 14,031 상태에서 멈췄으며 본 발주는 요청한 7,000회로 센다. 4.9의 LoD2 r8 30,000회 점검은 확인 불가. r7 결과를 r8로 대체하지 않는다.','', '| 지역·사전 정보 | 평가 밖 전체 패치/넓이 m² | r8 유효 목표 패치/넓이 m² | JUDGEAPPLY 연결 |','|---|---|---|---|']
 for x in scopes:
  def fmt(n,a):return f'{x[n]:,} / {x[a]:.3f}' if n in x else '없음'
  lines.append('| '+LABELS[x['site']]+' '+x['prior']+' | '+fmt('outside_patches','outside_area_m2')+' | '+fmt('outside_valid_target_patches','outside_valid_target_area_m2')+' | '+(f'{x["join_count"]:,}개, 정확 일치' if 'join_count' in x else '없음')+' |')
 lines+=['','r8은 평가 밖 패치도 사용한다. 실제 초기 가우시안이 연결된 평가 밖 패치 수/넓이도 `stage0_patch_scope`에 별도 기록했다. TARGET `prepare_inputs_r8.py:21–46`은 단계 0 전체 배열을 읽고 r7 목표·패치 초기값을 그대로 복사한다. `jbgs_target_r7.py`의 후보 검색도 평가 마스크로 제한하지 않는다.','', 'JUDGEAPPLY의 `source_index`는 단계 0 배열 번호다. 중심·넓이·평가 마스크와 고유 patch_id를 6개 파일 전체에서 확인했다. ALS 법선은 JUDGEAPPLY에서 재추정했으므로 동일 법선으로 가정하지 않는다. 결합 영역 `region[4]`는 세 지역×두 사전 정보 모두 있다. B173만의 JUDGEAPPLY 핵심점 파일은 없다.','', '상세 출처: `tables/stage0_inventory.{json,csv,md}`, `stage0_patch_scope`, `stage0_fusion`. 모든 원본 읽기 전용.']
 text='\n'.join(lines)+'\n';assert len(text)<=3000,len(text);(D/'단계0_목록.md').write_text(text)
 timing('stage0',start);print('STAGE0_COMPLETE',len(models),'saved states',len(text),'report characters')
if __name__=='__main__':main()
