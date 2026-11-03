"""Host stdlib locks and history-preserving user acceptance amendment."""
import datetime,shutil
from r8_screen_prepare import *
def main():
 root=O/'rfix_continue';root.mkdir(exist_ok=False);(root/'runtime').mkdir()
 at=datetime.datetime.now().astimezone().isoformat();cfg=j(C/'r8_record_continue.json');stop=j(O/'r8_recorded_continue/STOP_LoD2.json')
 cfg.update(at=at,authority='2026-11-03 user stage3 PASS; relative L2 <=1e-4 plus exact pixel addends; immediate stage4',label='r8_LoD2_rfix',checkpoint=stop['stop_dir']+'/checkpoint.pth',checkpoint_sha256=stop['checkpoint_sha256'],model='/out/rfix_continue/runs/r8_LoD2_rfix/model',save_iterations=list(range(15000,30001,1000)),capture_iterations=list(range(15000,30001,1000)),additional_readout_suppressed=list(range(16000,30000,1000)),extension='/out/rfix/builds/target/extension/jbgs_rfix_target.so',extension_sha256='ae90687632d79f2a7278319f1d38604339ba5ee9e67103945a9758ec9459a602',near_cameras=['DJI_20241217102533_0019_D','DJI_20241217102535_0020_D','DJI_20241217102537_0021_D'],time_record='every100 wall clock block mean and sampled iteration; includes recording/checkpoint work',stop_request='/out/rfix_continue/STOP_REQUEST.json',speedup_build_used=False)
 assert sha(local(cfg['extension']))==cfg['extension_sha256'];assert sha(local(cfg['checkpoint']))==cfg['checkpoint_sha256']
 shutil.copyfile(O/'r8_recorded_continue/runtime/train_recorded.py',root/'runtime/train_recorded.py')
 dump(C/'rfix_continue.json',cfg)
 old=j(C/'target_v1.runtime.r8.lock.json');files={str('/repo/'+p):h for p,h in old['files'].items()}
 paths=[C/'rfix_continue.json',local(cfg['checkpoint']),local(cfg['extension']),local(cfg['boundaries']),root/'runtime/train_recorded.py']
 paths+=list((R/'scripts/phd/main_target_v1').glob('rfix_continue*.py'))
 paths+=[R/'scripts/phd/main_target_v1'/n for n in ['r8_record_hooks.py','r8_record_proxy.py']]
 for p in paths:files[docker(p)]=sha(p)
 for p,h in files.items():assert sha(local(p))==h,p
 dump(C/'rfix_continue.lock.json',dict(at=at,files=files,scientific_verdict=None))
 amended=[]
 for row in j(C/'rfix.json')['states']:
  raw=j(O/'rfix/gradients'/row['key']/'result.json');values=[p['relative_l2'] for v in raw['rows'] for p in v['parameters'].values()]
  amended.append(dict(state=row['key'],comparisons=len(values),max_relative_l2=max(values),pass_relative_l2=all(v<=1e-4 for v in values)))
 assert all(x['pass_relative_l2'] for x in amended)
 dump(root/'acceptance_amendment.json',dict(at=at,authority='2026-11-03 direct user decision',historical_result='STOP_GRADIENT_PARITY preserved in rfix',new_stage3_acceptance='PASS_BY_USER_DECISION',criterion=dict(relative_l2_max=1e-4,pixel_addends='exact equality; expand20 rows per8 states concurrently',on_difference='save and stop training'),reassessment=amended,scientific_verdict=None))
 print('RFIX_CONTINUE_LOCKED',at,sha(C/'rfix_continue.json'))
if __name__=='__main__':main()
