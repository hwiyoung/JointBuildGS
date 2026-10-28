"""Host standard library: derive the two conditional 7000-step r17 commands."""
import hashlib
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

repo=Path(__file__).resolve().parents[3]
ph=repo.parent/'JointBuildGS-artifacts/phase-payloads/phd'
lt=ph/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1'
out=ph/'main_floatdiag_v1/PHD-MAIN-FLOATDIAG-v1'
cfg=repo/'configs/phd/main_floatdiag_v1'
inventory=json.loads((repo/'docs/experiments/phd/main_floatdiag_v1/provenance/input_inventory_ALS.json').read_text())
unit=lt/'runs/R1rep_b10/lt_dynnow_ALS_s0';passed=json.loads((unit/'PASS.json').read_text())
original=unit/f"attempt_{passed['attempt']}/command.json"
command=json.loads(original.read_text());args=command[command.index('train.py')+1:]
def options(seq):
    result=[]
    for item in seq:
        if item.startswith('-'):result.append([item,[]])
        else:result[-1][1].append(item)
    return result
original_options=options(args)
runs=[]
for mode,name in [('dynamic','fd_dynnow_ALS_s0'),('current','fd_current_ALS_s0')]:
    # No existing models may be rewritten. Commands are prepared before launch.
    dest=out/'runs/R1rep_b10'/name
    assert not dest.exists(),dest
    changes={'-m':[f'/o/runs/R1rep_b10/{name}/model'],'--iterations':['7000'],
        '--test_iterations':['7000'],'--save_iterations':[str(i) for i in range(500,7001,500)],
        '--jbgs_snapshot_iterations':[str(i) for i in range(500,7001,500)],
        '--jbgs_readout_interval':['7000'],'--jbgs_dump_iterations':['7000'],
        '--jbgs_memlog_to':['7000'],'--jbgs_sw_depth_loss':[mode]}
    rewritten=[];diff=[]
    for key,value in original_options:
        new=changes.get(key,value)
        new=[x.replace('/o/direct_stage1_v2/','/ph/main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2/').replace('/o/checks/','/ph/main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/') for x in new]
        if new!=value:diff.append(dict(option=key,before=value,after=new))
        rewritten += [key,*new]
    runs.append(dict(site='R1rep_b10',name=name,mode=mode,arguments=rewritten,changes=diff,source_revision='r17',
        model_destination=str(dest/'model'),optimizer_steps_requested=7000,seed=0,
        depth_lambda=.0025 if mode=='dynamic' else .05,health='unchanged r17 monitor_v2',
        purpose='time-of-formation only; not used to score the 30000-step result',scientific_verdict=None))
# Existing snapshot inventory independently binds the condition; explicitly
# inspect both original dynamic models rather than inferring from one list.
condition=[]
for result in ['lt_dyngt_ALS_s0','lt_dynnow_ALS_s0']:
    root=lt/'runs/R1rep_b10'/result;r=json.loads((root/'PASS.json').read_text())
    model=root/f"attempt_{r['attempt']}"/'model'
    iterations=sorted(int(p.name.split('_')[-1]) for p in (model/'point_cloud').glob('iteration_*'))
    assert not any(1000<=i<=7000 for i in iterations)
    condition.append(dict(result=result,saved_iterations=iterations))
data=dict(at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),authorization='user-selected work order 4.7',
    condition=condition,original_command=str(original),original_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
    runs=runs,scientific_verdict=None)
p=cfg/'conditional_replays.json';assert not p.exists();p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
print('Prepared, not launched: two conditional 7000-step r17 runs')
