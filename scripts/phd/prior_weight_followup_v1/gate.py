"""Validate the actual preflight and parity with the prior .005 baseline."""
import json
from pathlib import Path
import sys
sys.path.insert(0,'/experiment/scripts')
from validate_gate import validate,sha,read

root=Path('/experiment');cfg=read(root/'config.json')
gate=validate(root)
prefix='p1_weight' if cfg['region']=='P1' else 'region_weight'
model=root/'preflight/alpha_4/model'
old=read(root/'baseline_first_step.json');new=read(model/(prefix+'_first_step.json'))
for key in ['camera','pred_depth_sha256','native_mvs_loss']:assert old[key]==new[key],key
old=[json.loads(x) for x in (root/'baseline_camera_trace.jsonl').read_text().splitlines()]
new=[json.loads(x) for x in (model/(prefix+'_camera_trace.jsonl')).read_text().splitlines()]
assert old[:len(new)]==new
gate.update(baseline_prior=.005,new_prior=.0005,r1_weight=4,baseline_first_render_exact=True,
            baseline_camera_schedule_exact=True,baseline_trace_sha256=sha(root/'baseline_camera_trace.jsonl'))
with (root/'gate.json').open('x') as f:json.dump(gate,f,indent=2)
print(json.dumps(gate))
