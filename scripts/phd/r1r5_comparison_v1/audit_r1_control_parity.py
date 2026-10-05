"""Read-only comparison of executed R1 controls and pre-intervention log values."""
import argparse
import hashlib
import json
from pathlib import Path
import re

def read(path):return json.loads(Path(path).read_text())
def rows(path):return [json.loads(line) for line in Path(path).read_text().splitlines()]
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

ap=argparse.ArgumentParser();ap.add_argument('attempt',type=Path);ap.add_argument('output',type=Path)
a=ap.parse_args();root=a.attempt.resolve();cfg=read(root/'config.json');art=Path(cfg['artifact_root'])
old=art/cfg['r1_run_relative']/'refinement';new=root/'R1/local_prior0'
r0,r1=read(old/'receipt.json'),read(new/'receipt.json')
mask=read(root/'R1/masks/receipt.json');counts={v['name']:v['pixels'] for v in mask['masks']}
s0,s1=rows(old/'camera_sampling.jsonl'),rows(new/'camera_sampling.jsonl')
first=next(row for row in s1 if counts[row['camera']]>0)
actual=next(row for row in rows(new/'local_prior_trace.jsonl') if row['zero_weight_valid']>0)
assert first['iteration']==actual['iteration']==8015
assert all(counts[row['camera']]==0 for row in s1 if row['iteration']<8015)
logs=[]
for stage in [old,new]:
    line=next(line for line in (stage/'process.log').read_text().splitlines()
              if 'Training progress:' in line and 'lod=' in line)
    values={key:float(re.search(key+r'=([0-9.]+)',line).group(1)) for key in ['Loss','lod','da','normal']}
    logs.append(dict(stage=str(stage),iteration=8010,values=values,source_line=line,
                     meaning='Exponential moving averages printed every 10 iterations; not instantaneous loss'))
assert logs[0]['values']['lod']!=logs[1]['values']['lod']
weights=[sorted(set(row['mvs_weight'] for row in rows(stage/'model/mvs_pgsr_trace.jsonl'))) for stage in [old,new]]
run=art/cfg['r1_run_relative'];binding=read(run/'mesh_recovery.json')
meshes=[run/binding['relative']/'extract_final',root/'R1/extract_local_prior0'];mesh_values=[]
for folder in meshes:
    text=(folder/'process.log').read_text()
    mesh_values.append({key:float(re.search(re.escape(key)+r': ([0-9.]+)',text).group(1)) for key in ['voxel_size','sdf_trunc','depth_truc']})
result=dict(status='PASS_READ_ONLY_CONTROL_AUDIT',scientific_verdict=None,
    same_anchor=r0['anchor_sha256']==r1['anchor_sha256'],same_training_argv=r0['command']==r1['command'],
    same_docker_image=r0['runtime_image_id']==r1['runtime_image_id'],
    same_camera_sequence=len(s0)==len(s1) and all((x['iteration'],x['camera'])==(y['iteration'],y['camera']) for x,y in zip(s0,s1)),
    compared_iterations=len(s0),image_depth_weights=weights,tsdf_parameters=mesh_values,
    first_selected_mask_camera=first,first_recorded_active_mask=actual,pre_mask_progress=logs,
    runtime_differences=dict(control_gpu=1,local_prior0_gpu=0,control_allocator='backend:native,max_split_size_mb:128',
        local_prior0_allocator=read(new/'invocation.json')['effective_cuda_allocator'],
        control_driver_sha256=r0['driver_sha256'],local_prior0_driver_sha256=r1['driver_sha256']),
    input_evidence_sha256={str(p):digest(p) for p in [old/'command.sh',old/'process.log',new/'command.json',new/'process.log',new/'local_prior_trace.jsonl']},
    conclusion='Numerical divergence is recorded before the first nonzero mask. Its cause and its contribution to the final floater are not isolated.')
a.output.parent.mkdir(parents=True,exist_ok=True)
with a.output.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
print(json.dumps({k:result[k] for k in ['status','same_anchor','same_training_argv','same_camera_sequence','pre_mask_progress']},ensure_ascii=False))
