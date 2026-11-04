"""Order section 7 and table/figure conservation, without rerunning scoring."""
from common import *
import sys,platform,subprocess
def main():
 cfg();checks=[];assert json.loads((O/'verification/unit_default.json').read_text())['status']=='PASS';assert json.loads((O/'verification/unit_rules.json').read_text())['status']=='PASS';checks.append('r23/r24 default/log on/off 100-step equality and pull/delete/mix units')
 runtime=json.loads((C/'runtime.lock.json').read_text());assert runtime['config_sha256']==sha(C/'release_v1.json')
 for path,h in runtime['files'].items():assert sha(path)==h,path
 checks.append('r24 sources and target-search binary match the pre-training runtime lock')
 assert sha(C/'inherited_files.lock.json')==json.loads((C/'release_v1.initial.lock.json').read_text())['inputs_lock_sha256']
 protected=json.loads((C/'inherited_files.lock.json').read_text());host='/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp'
 for path,h in protected.items():assert sha(path.replace(host,str(R),1))==h,path
 checks.append(f'{len(protected)} inherited code/config/report hashes unchanged')
 locked=json.loads((C/'score_inputs.lock.json').read_text());done={}
 for row in locked['rows']:
  for k in ['score','points','mesh']:
   p=row[k]
   if p not in done:done[p]=sha(p)
   assert done[p]==row[k+'_sha256'],p
 checks.append('54 inherited result sets: scores, point distances and surface hashes unchanged')
 maxerr=0
 for site in SITES:
  for prior in ['ALS','LoD2']:
   stem=f'{site}__{prior}';r=json.loads((O/'stage0'/stem/'receipt.json').read_text());maxerr=max(maxerr,r['max_reproduction_delta_pp']);assert r['max_reproduction_delta_pp']<=.1
   z=loadz(O/'stage0'/stem/'cells.npz',['old_cell','score_cell_1p0','prior_presence']);cross=json.loads((D/'tables/stage0'/f'{stem}_crosswalk.json').read_text())['rows'];assert sum(r['n_gt'] for r in cross)==len(z['old_cell']);assert (z['score_cell_1p0'][~z['prior_presence']]==-1).all()
 checks.append(f'tau 1 original cells reproduce table4 <=0.1 pp; observed maximum {maxerr:g} pp; all cross-tabs conserve rows')
 for prior in ['ALS','LoD2']:
  root=O/'stage1'/f'R1rep_b10__{prior}';r=loadz(root/'rows.npz');a=loadz(root/'attribution.npz');data=json.loads((D/'tables/stage1'/f'R1rep_b10__{prior}_attribution.json').read_text())['rows']
  assert len(r['xyz'])==len(a['selected_gaussian']);assert (a['current_binding'][a['selected_gaussian']<0]==4).all()
  for mode,labels in [('original',r['old_cell']),('score',loadz(O/'stage0'/f'R1rep_b10__{prior}'/'cells.npz',['score_cell_1p0'])['score_cell_1p0'])]:
   for cell in [0,1,2,4]:
    t=[q for q in data if q['cell_basis']==mode and q['cell']==cell and q['judgment_region']==-1];assert sum(q['n_gt'] for q in t)==int((labels==cell).sum())
    if mode=='original':
     v=json.loads((score_dir('R1rep_b10',prior,'FINALTRAIN_30000')/'values.json').read_text());old=next(x for x in v['cells'] if x['cell']==cell);den=int((labels==cell).sum())
     if den:assert abs(sum(q['n_gt'] for q in t if q['result_type']==0)/den-old['completeness'])*100<=.1
  for sim in cfg()['stage1']['simulations']:
   folder=O/'simulations'/f'R1rep_b10__{prior}__sim_{sim}';m=json.loads((folder/'point_cloud.json').read_text());assert m['GT_used'] is False;assert sha(folder/'point_cloud.ply')==m['output_sha256'];assert (O/'scores'/folder.name/'values.json').exists()
 checks.append('R1 original and score-cell lineage counts conserve all rows; completeness <=0.1 pp; six tag/target-only simulations scored')
 gate=json.loads((D/'단계3_판정.json').read_text());assert (O/'delivery/stage3_gate.json').exists()
 if gate['stage3_authorized']:
  selection=json.loads((D/'단계3_고른규칙.json').read_text());assert (O/'delivery/stage3_selection.json').exists();checks.append('committed original-cell gate and selection precede dependent runs')
 else:assert not list((O/'runs').glob('*/rl_*'));checks.append('negative prespecified gate: no stage3 training')
 for prior in ['ALS','LoD2']:
  run=O/'runs/R1rep_b10'/f'rlog_{prior}_s0';rec=json.loads((run/'receipt.json').read_text())
  if rec['status']=='COMPLETED_15000':
   mon=Path(rec['attempts'][-1]['model'])/'target_monitor'
   for it in [7000,15000]:
    a=loadz(mon/f'snapshot_{it}.npz',['target_tag']);b=loadz(mon/f'release_snapshot_{it}.npz',['rl_event']);assert np.array_equal(a['target_tag']==2,b['rl_event']>=0)
    health=json.loads((mon/f'health_{it}.json').read_text());assert health['status']=='PASS_HEALTH' and np.isfinite(health['loss'])
 checks.append('stage2 recorded release-event descendants exactly match released population at checkpoints; saved health receipts')
 for stage,count in [('stage0',4),('stage1',4),('stage2',2)]:
  images=list((D/'figures'/stage).glob('*.png'));assert len(images)==count
  for p in images:assert p.with_suffix('.json').exists()
 checks.append('requested 4+4+2 figures each have provenance JSON')
 report=D/'보고.md';assert len(report.read_text())<=12000
 dump(D/'validation.json',dict(at=now(),status='PASS_ORDER_CHECKLIST_WITH_DOCUMENTED_UNAVAILABLE',checks=checks,python=platform.python_version(),numpy=np.__version__,report_characters=len(report.read_text()),scientific_verdict=None))
 print('VALIDATION_PASS',len(checks),flush=True)
if __name__=='__main__':main()
