"""Summarize immutable matched R1 outputs in the previously fixed floater box."""
import json
from pathlib import Path
import numpy as np


def vertices(path):
    types={'float':'<f4','double':'<f8','uchar':'u1','int':'<i4','uint':'<u4'}
    with path.open('rb') as f:
        fields=[];active=False;count=None
        while True:
            line=f.readline().decode('ascii').strip();w=line.split()
            if line=='end_header':break
            if w[:1]==['format']:assert w[1]=='binary_little_endian'
            if w[:1]==['element']:
                active=w[1]=='vertex'
                if active:count=int(w[2])
            if active and w[:1]==['property']:fields.append((w[2],types[w[1]]))
        offset=f.tell()
    return np.memmap(path,mode='r',dtype=np.dtype(fields),offset=offset,shape=(count,))


root=Path('/run');out=Path('/output');plan=json.loads(Path('/driver/causal_plan.json').read_text())
theta=np.deg2rad(70);basis=np.array([[np.cos(theta),np.sin(theta)],[np.sin(theta),-np.cos(theta)]])
rows=[]
for condition in plan['workers']['0']:
    if condition['region']!='R1':continue
    tag=condition['tag'];folder=root/'R1'/('local_prior0_'+tag);extract=root/'R1'/('extract_local_prior0_'+tag)
    receipt=json.loads((extract/'receipt.json').read_text());assert receipt['status']=='PASS'
    mesh=vertices(extract/receipt['surfaces']['fuse.ply']['path']);count=0;selected=[]
    for start in range(0,len(mesh),300000):
        v=mesh[start:start+300000];xyz=np.column_stack([v[k] for k in 'xyz']);xyz[:,:2]=xyz[:,:2]@basis.T;xyz[:,1]*=-1
        keep=((xyz>=np.array([-40,24,-18]))&(xyz<=np.array([-10,42,-12]))).all(1)
        count+=int(keep.sum());selected.append(xyz[keep])
    np.save(out/(tag+'_floater_vertices.npy'),np.concatenate(selected))
    g=vertices(folder/'model/jbgs_complete/iteration_30000/point_cloud.ply')
    scale=np.maximum(np.exp(g['scale_0']),np.exp(g['scale_1']));ids=np.argsort(scale)[-20:][::-1]
    probes=[json.loads(line) for line in (folder/'probe_depth_trace.jsonl').read_text().splitlines()]
    final_probes={x['camera']:x for x in probes}
    rows.append(dict(condition=condition,floater_box_raw_vertices=count,gaussians=len(g),
                     scale_gt_50m=int((scale>50).sum()),maximum_scale_m=float(scale.max()),
                     largest_gaussians=[dict(id=int(i),scale_m=float(scale[i]),xyz=[float(g[k][i]) for k in 'xyz']) for i in ids],
                     final_observed_probe_depths=final_probes,mesh_sha256=receipt['surfaces']['fuse.ply']['sha256']))
assert len(rows)==2
result=dict(status='PASS_MATCHED_PAIR_SUMMARY',scientific_verdict=None,rows=rows,
            limitation='One matched keep/release pair and fixed-box diagnostic, not population evidence or repeated-run variance estimate.')
(out/'receipt.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
