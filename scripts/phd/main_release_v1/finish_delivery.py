"""Wait for completed numerical jobs, then deliver stage1 and final bundles."""
import json,subprocess
from gpu_job import R,O,C,D,dump,now
from post_run import await_file,cpu
from publish import lock,commit,bundle,sha
S=R/'scripts/phd/main_release_v1'
def main():
 for prior in ['ALS','LoD2']:
  for sim in ['delete_released','pull_released','delete_background']:await_file(O/'scores'/f'R1rep_b10__{prior}__sim_{sim}'/'values.json')
 cpu('stage1-final-summary','stage1_summary.py')
 assert json.loads((O/'verification/visual_stage1.json').read_text())['status']=='PASS'
 paths=[C,S,D/'tables/stage1',D/'figures/stage1',D/'단계1_보고.md',D/'단계3_판정.json',D/'table_codes.json',D/'재실행_경로.md',D/'issues.md']
 evidence=[]
 for root in (O/'stage1').glob('R1rep_b10__*'):
  evidence.extend(root.glob('*.json'));evidence.extend(root/p for p in ['rows.npz','attribution.npz','simulation_masks.npz','outside_attributed_targets.npz']);evidence.extend([root/'lineage/receipt.json',root/'lineage_returned/receipt.json'])
 evidence.extend((O/'simulations').glob('*/point_cloud.json'));evidence.extend((O/'scores').glob('*/values.json'))
 with lock():
  rec=bundle('PHD-MAIN-RELEASE-v1_단계1.zip',[*paths,*evidence,O/'delivery/stage3_gate.json']);head=commit('stage 1 R1 lineage and six simulations',paths);dump(O/'delivery/stage1.json',dict(at=now(),commit=head,bundle=rec,scientific_verdict=None))
 print('STAGE1_DELIVERED',head,rec['path'],flush=True)
 await_file(O/'delivery/stage2.json');await_file(O/'verification/visual_stage2.json')
 assert json.loads((O/'verification/visual_stage2.json').read_text())['status']=='PASS'
 cpu('final-report','final_report.py');cpu('final-validation','validate_outputs.py')
 gate=json.loads((O/'delivery/stage3_gate.json').read_text());assert sha(D/'단계3_판정.json')==gate['gate_sha256']
 manifest=dict(at=now(),config_sha256=sha(C/'release_v1.json'),payload_root=str(O),stage0=str(O/'stage0'),stage1=str(O/'stage1'),event_records=[str(p) for p in sorted((O/'events').glob('*/receipt.json'))],run_receipts=[str(p) for p in sorted((O/'runs').glob('*/*/receipt.json'))],simulation_models=[str(p) for p in sorted((O/'simulations').glob('*/point_cloud.json'))],scores=[dict(path=str(p),sha256=sha(p)) for p in sorted((O/'scores').glob('*/values.json'))],gate=gate,stage3='NOT_RUN_PRESPECIFIED_GATE_FALSE',scientific_verdict=None)
 dump(D/'payload_manifest.json',manifest)
 with lock():
  extras=[*list((O/'verification').glob('*.json')),*list((O/'events').glob('*/receipt.json')),*list((O/'delivery').glob('stage*.json'))]
  rec=bundle('PHD-MAIN-RELEASE-v1.zip',[C,S,D,*extras]);head=commit('final no-stage3 delivery',[C,S,D,R/'src/phd/forks/GeoGS-conf-guided-v1-r24']);dump(O/'delivery/final.json',dict(at=now(),commit=head,bundle=rec,status='COMPLETE_STAGES_0_1_2_STAGE3_NOT_OPENED',scientific_verdict=None))
 print('FINAL_DELIVERED',head,rec['path'],rec['sha256'],flush=True)
if __name__=='__main__':main()
