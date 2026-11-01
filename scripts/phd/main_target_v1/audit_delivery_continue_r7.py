"""Final delivery completeness, source integrity, saved training state and declared unavailable rows."""
from common import *

def read(p):return json.loads(p.read_text())
def main():
 root=OUT/'r7_continue';cfg=read(CFG/'scoring_continue_r7.r1.json');checks={};sources={}
 for name in ['scoring_continue_r7','scoring_continue_r7.r1','continue_r7.lod2_r2']:
  p=CFG/(name+'.json');assert sha(p)==read(CFG/(name+'.lock.json'))['config_sha256'];sources[str(p)]=sha(p)
 lock=read(CFG/'target_v1.runtime.r7.lock.json');assert sha(CFG/'target_v1.r7.json')==lock['config_sha256']
 for p,h in lock['files'].items():assert sha(REPO/p)==h,p
 for p,h in read(CFG/'fork_r21_base.json')['files'].items():assert sha(REPO/p)==h,p
 for p,h in cfg['source_files'].items():assert sha(p)==h,p
 for p,h in read(CFG/'scoring_continue_r7.inputs.lock.json')['files'].items():assert sha(p)==h,p
 for p,h in read(CFG/'continue_r7.lod2_r2.lock.json')['files'].items():assert sha(REPO/p)==h,p
 checks['frozen_r21_training_and_inherited_scoring_sources']='PASS';checks['input_locks']='PASS'
 assert read(root/'scoring/parity.json')['status']=='PASS'
 assert read(root/'diagnostics/ALS/verification.r1.json')['status']=='PASS'
 checks['inherited_arithmetic_parity_and_ALS_independent_diagnostic']='PASS'
 summary=read(root/'summary.json');states=summary['states'];done=[];unavailable=[]
 for r in cfg['rows']:
  for kind in ['current','final']:
   q=root/'scoring'/r['key']/kind/'values.json';s=next(x for x in states if x['key']==r['key'] and x['kind']==kind)
   if q.exists():
    a=read(q);v=read(q.parent/'verification.json');assert a['status']=='PASS' and v['status']=='PASS_INDEPENDENT_SAVED_ARITHMETIC' and v['mesh_sha256']==a['mesh_sha256'];assert s['status']=='PASS'
    for typ in ['cells','axes','clumps']:
     p=DOC/'figures'/f"continue_r7_{r['key']}_{kind}_{typ}.json";assert p.exists() and p.with_suffix('.png').exists()
    if kind=='final':
     receipt=read(root/'meshes'/r['key']/'receipt.json');assert receipt['status']=='PASS' and receipt['mesh_sha256']==a['mesh_sha256'];assert receipt['final_triangles']>0
    done.append(dict(key=r['key'],kind=kind,mesh_sha256=a['mesh_sha256'],verification_sha256=sha(q.parent/'verification.json')))
   else:
    assert r['family']=='r7' and r['iteration']>7000 and s['status']=='NOT_REACHED_TRAINING_STOPPED',(r['key'],kind,s)
    checkpoint=Path(r['model'])/'jbgs_complete'/f"iteration_{r['iteration']}/checkpoint.pth";assert not checkpoint.exists();unavailable.append(dict(key=r['key'],kind=kind,status=s['status']))
 # At minimum the sixteen expressly requested pre-existing meshes must be complete.
 assert len(done)>=16 and len(done)+len(unavailable)==24
 checks['available_meshes_and_missing_rows']='PASS'
 run=root/'lod2_retry/runs/tg_B173nb_b10_LoD2_s0_r7';receipt=read(run/'receipt.json');rest=read(run/'model/jbgs_restore.json');assert rest['iteration']==7000 and all(rest[k] for k in ['target_state','optimizer_state','rng_and_camera_state'])
 curve=[json.loads(x) for x in (run/'model/target_monitor/curve.jsonl').read_text().splitlines()];memory=[json.loads(x) for x in (run/'model/target_monitor/memory_1000.jsonl').read_text().splitlines()];expected=[x for x in curve if x['iteration']%1000==0];assert [r['iteration'] for r in memory]==[r['iteration'] for r in expected]
 for r,c in zip(memory,expected):assert r['gaussians']==c['gaussians'] and r['tags']==c['tags'] and r['cuda_allocated_bytes']<=r['peak_cuda_allocated_bytes'] and r['cuda_reserved_bytes']<=r['peak_cuda_reserved_bytes']
 if receipt['exit_code']==0:
  assert curve[-1]['iteration']==30000 and receipt['status']=='TRAINING_COMPLETE_30000'
  fs=read(run/'verification_full_state.json');assert all(x['status']=='PASS_COMPLETE_STATE' for x in fs['rows']) and {x['iteration'] for x in fs['rows']}=={15000,30000};training='LoD2 30000 complete; ALS not resumed by r8 decision'
  for it in [15000,30000]:
   v=read(run/f'verification_post{it}.json');assert v['status']=='PASS_POST_RECOUNT_AND_RAYS'
   assert v['score_sha256']==sha(run/f'post{it}/score.json') and v['mesh_sha256']==sha(run/f'post{it}/merged.ply')
  checks['LoD2_independent_first_hit_rays_and_area_recount']='PASS'
 else:assert (root/'lod2_retry/STOP_LoD2.json').exists();training='LoD2 health/execution stop; ALS not resumed by r8 decision'
 checks['LoD2_independent_resume_and_1000_step_memory_records']='PASS';assert not (root/'als_retry').exists(),'review any new ALS authorization before delivery'
 for prior in ['ALS','LoD2']:
  c=read(root/'post'/f'base_{prior}_30000/coverage.json');assert c['iteration']==30000 and len(c['views'])==203;assert c['strata']['all']['target_pixels']==c['strata']['prior']['target_pixels']+c['strata']['background']['target_pixels']
  for kind in ['current','final']:
   for f in ['R_tau','P_tau','gt_mean','res_mean','floating','missing','ge_2.5','ge_10']:
    p=DOC/'figures'/f'continue_r7_compare_{prior}_{kind}_{f}.json';assert p.exists() and p.with_suffix('.png').exists()
 assert read(root/'post/baseline_coverage_verification.json')['status']=='PASS_BASELINE_CAMERA_LINEAGE_AND_PARTITIONS'
 checks['baseline30000_same_r7_pixel_targets_and_comparison_figures']='PASS'
 for name in ['이어학습과채점_r7.md','항공LiDAR_r7_원인점검.md','이어학습_r7_중단기록.md']:assert (DOC/name).exists()
 result=dict(at=stamp(),status='PASS_CONTINUATION_DELIVERY_AUDIT',checks=checks,training_status=training,mesh_scores_complete=len(done),mesh_scores_unavailable=len(unavailable),complete=done,unavailable=unavailable,other_six='NOT_STARTED',sources=sources,scoring_complete_for_available_models=True,scientific_verdict=None)
 dump(root/'final_audit.json',result);dump(DOC/'tables/final_audit_continue_r7.json',result);print('FINAL_CONTINUATION_AUDIT_PASS',len(done),len(unavailable),training,flush=True)
if __name__=='__main__':main()
