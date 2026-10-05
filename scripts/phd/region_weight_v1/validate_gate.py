"""Match three regional preflights before any corresponding full continuation."""
import argparse
import json
from pathlib import Path
from run_phase import read,sha,validate_intervention


def validate(root):
    root=Path(root); cfg=read(root/'config.json'); schedules=[]; first=[]; rows=[]
    for alpha in cfg['alphas']:
        output=root/'preflight'/f'alpha_{alpha}'; model=output/'model'; receipt=read(output/'receipt.json')
        for key,value in dict(status='PASS',completed=True,final_iteration=cfg['preflight_stop'],region=cfg['region'],
            config_sha256=sha(root/'config.json'),mask_sha256=cfg['mask_sha256'],
            source_provenance_sha256=sha(root/'source/region_weight_source_provenance.json')).items():
            if receipt.get(key)!=value:raise ValueError('Preflight receipt mismatch: '+key)
        for item in receipt['verified_outputs']:
            if sha(output/item['path'])!=item['sha256']:raise ValueError('Checkpoint changed')
        validate_intervention(output,cfg,alpha)
        restore=read(model/'jbgs_restore.json')
        if restore['declared_dynamic_depth_weight_change']!=[True,False]:raise ValueError('Controller override missing')
        schedule=[json.loads(line) for line in (model/'region_weight_camera_trace.jsonl').read_text().splitlines()]
        if [r['iteration'] for r in schedule]!=list(range(8001,cfg['preflight_stop']+1)):raise ValueError('Incomplete schedule')
        schedules.append(schedule);first.append(read(model/'region_weight_first_step.json'))
        rows.append(dict(alpha=alpha,receipt_sha256=sha(output/'receipt.json'),cameras_exercised=receipt['cameras_exercised']))
    if any(s!=schedules[0] for s in schedules):raise ValueError('Camera schedules differ')
    if any(r!=first[0] for r in first):raise ValueError('Initial pre-update render differs')
    return dict(status='PASS',scientific_verdict=None,region=cfg['region'],config_sha256=sha(root/'config.json'),
        source_provenance_sha256=sha(root/'source/region_weight_source_provenance.json'),
        matched_camera_schedule=True,matched_first_render=True,preflights=rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args()
    try: result=validate(args.root)
    except Exception as error:
        (args.root/'gate_failure.json').write_text(json.dumps(dict(status='FAIL',error=repr(error),scientific_verdict=None),indent=2));raise
    with (args.root/'gate.json').open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(result))
