"""Host stdlib recovery orchestrator; scientific processing stays in Docker."""
import datetime,json,subprocess,time
from pathlib import Path
T=Path(__file__).resolve().parents[1]
root=T/'conditions/B-1.0'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save_state(state):
 state['updated_at']=now();p=T/'status.recovery.tmp';p.write_text(json.dumps(state,indent=2));p.replace(T/'status.json')
state=json.loads((T/'status.json').read_text());state['phase']='POSTPROCESS_RECOVERY';save_state(state)
for phase in ['analyze','export']:
 path=root/(phase+'_receipt.json');original=json.loads(path.read_text())
 archived=root/(phase+'_before_nonfinite_recovery_receipt.json')
 if not archived.exists():archived.write_text(json.dumps(original,indent=2))
 cmd=list(original['command']);cmd[cmd.index('--name')+1]='roof-Bm1-recovery-'+phase
 start=now();clock=time.monotonic()
 with (root/(phase+'_nonfinite_recovery.log')).open('w') as f:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
 receipt=dict(original,command=cmd,started_at=start,finished_at=now(),seconds=time.monotonic()-clock,exit_code=rc,status='PASS' if rc==0 else 'FAILED',recovery='Postprocessing handles nonfinite coordinates/opacity with explicit counts; source PLY unchanged')
 path.write_text(json.dumps(receipt,indent=2))
 state['conditions']['B-1.0'][phase]=receipt['status']
 if phase=='analyze':
  state['phase']='FINISHED'
  state['postprocessing_recovered']=rc==0
  state['data_quality_exceptions']=[{'condition':'B-1.0','nonfinite_final_gaussians':73,'native_protected':3,'native_unprotected':70,'checkpoint_unchanged':True,'training_cause':'UNDETERMINED'}]
  # Retain PARTIAL for the trained-state exception even if artifact recovery succeeds.
  state['status']='PARTIAL';save_state(state)
 if rc:break
state['phase']='FINISHED';state['postprocessing_recovery_finished_at']=now();save_state(state)
runtime=json.loads((T/'runtime_status.json').read_text());runtime.update(at=now(),phase='FINISHED',supervisor_alive=False,postprocessing_recovered=state.get('postprocessing_recovered',False));(T/'runtime_status.json').write_text(json.dumps(runtime,indent=2))
