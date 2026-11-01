"""Delivery audit distinguishes measurement validity, experiment gates and unavailable work."""
import ast,re
from common import *
def read(p):return json.loads(p.read_text())
def main():
 checks=0
 for name in ['fork_r20_base.json','target_v1.runtime.r6.lock.json','execution_r6.code.lock.json']:
  for path,digest in read(CFG/name)['files'].items():assert sha(REPO/path)==digest,path;checks+=1
 assert sha(CFG/'target_v1.r6.json')==read(CFG/'target_v1.r6.lock.json')['config_sha256']
 assert read(OUT/'r6/verification/unit.json')['status']=='PASS_R6_UNIT'
 assert read(OUT/'r6/verification/initial.json')['status']=='PASS_R6_INITIALIZATION'
 rows=[]
 for prior in ['ALS','LoD2']:
  run=OUT/'r6/runs'/f'tg_B173nb_b10_{prior}_s0_r6';score=read(run/'post7000/score.json');old=read(OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0/post7000/score.json');ref=read(OUT/'r6/reference'/prior/'score.json')
  assert old['rows']==ref['rows'] and old['mesh_sha256']==ref['mesh_sha256']
  assert read(run/'verification7000.json')['status']=='PASS_R6_SAVED_EVIDENCE_RECOUNT'
  assert read(run/'verification_post7000.json')['status']=='PASS_POST7000_RECOUNT_AND_RAYS'
  assert read(run/'verification_diagnostics.json')['status']=='PASS_R6_DIAGNOSTIC_RECOUNT'
  full=read(run/'verification_full_state.json');assert full['rows'][0]['status']=='PASS_COMPLETE_STATE'
  source=read(run/'launch.json');assert source['config_sha256']==sha(CFG/'target_v1.r6.json')
  assert score['status']==('PASS' if all(score['gates'].values()) else 'FAIL')
  assert sha(run/'post7000/score.json')==read(run/'verification_post7000.json')['score_sha256']
  assert sha(run/'model/check7000/coverage.json')==read(run/'verification7000.json')['coverage_sha256']
  rows.append(dict(prior=prior,gates=score['gates'],status=score['status'],saved_complete_states=[r['iteration'] for r in full['rows'] if r['status']=='PASS_COMPLETE_STATE']))
 pairs=[]
 for p in sorted((DOC/'figures').glob('r6_*.png')):
  assert p.with_suffix('.json').exists();read(p.with_suffix('.json'));pairs.append(dict(file=p.name,sha256=sha(p)))
 assert len(pairs)>=30
 visual=read(DOC/'tables/visual_review_r6.json')
 assert {r['file'] for r in visual['figures']}=={r['file'] for r in pairs}
 for row in visual['figures']:assert sha(DOC/'figures'/row['file'])==row['sha256']
 for name in ['영역별목표학습_보고_v1.md','단계1_7000회_점검_r6.md']:
  p=DOC/name;body=p.read_text()
  for target in re.findall(r'\]\(([^)]+)\)',body):
   if '://' not in target and not target.startswith('#'):assert (p.parent/target).exists(),(p,target)
 body=(DOC/'영역별목표학습_보고_v1.md').read_text();assert len(body)<20000 and len(re.findall(r'^## [1-8]\. ',body,re.M))==8
 for folder in [REPO/'scripts/phd/main_target_v1',REPO/'src/phd/forks/GeoGS-conf-guided-v1-r20']:
  for p in folder.rglob('*.py'):ast.parse(p.read_text())
 passed=all(r['status']=='PASS' for r in rows)
 result=dict(at=stamp(),status='PASS_R6_DELIVERY_AUDIT',experiment_status='PASS_7000_STOP_SCHEDULED_RESET' if passed else 'STOP_R6_7000_AND_SCHEDULED_RESET',rows=rows,
  locked_files_checked=checks,figure_pairs=len(pairs),report_characters=len(body),scientific_verdict=None)
 dump(DOC/'tables/final_audit_r6.json',result);dump(OUT/'r6/final_audit.json',result);print(json.dumps(result),flush=True)
if __name__=='__main__':main()
