"""CPU-only saved-state arrays and original baseline execution records."""
import gc
import numpy as np
import torch
from plyfile import PlyData
from scipy.special import expit
from common import *

ROOT=OUT/'r8_lod2_cause'
def main():
    lock=json.loads((CFG/'cause_r8_lod2.lock.r1.json').read_text())
    assert sha(CFG/'cause_r8_lod2.json')==lock['config_sha256']
    config=json.loads((CFG/'cause_r8_lod2.json').read_text()); result=[]
    for row in config['rows']:
        key=row['key']; dest=ROOT/'states'/key; dest.mkdir(parents=True,exist_ok=True)
        assert sha(row['ply'])==lock['files'][row['ply']]
        v=PlyData.read(row['ply'])['vertex'].data
        xyz=np.column_stack([v[k] for k in ['x','y','z']]); ids=v['init_id'].astype('i8')
        origin=v['origin'].astype('i1'); scale=np.exp(np.column_stack([v[k] for k in ['scale_0','scale_1']]))
        opacity=expit(v['opacity']); release=np.full(len(v),-1,'i4')
        if row['family']=='base':
            initial=np.load(S0/'fork_inputs/s61/B173nb_b10'/f'scene_{row["prior"]}/sparse/0/origin.npy')
            assert np.array_equal(origin,initial[ids]); tags=origin.copy()
        else:
            assert sha(row['snapshot'])==lock['files'][row['snapshot']]
            with np.load(row['snapshot']) as s:
                assert np.array_equal(ids,s['init_id']) and np.array_equal(xyz,s['xyz'])
                assert np.array_equal(origin,s['origin']);tags=s['target_tag'];release=s['target_released_at']
        a=dict(xyz=xyz,init_id=ids,origin=origin,tag=tags,released_at=release,longest_axis=scale.max(axis=1),opacity=opacity)
        grad=dict(status='NOT_REQUESTED')
        if row['gradient_requested']:
            grad=dict(status='없음',searched=str(Path(row['model'])/'jbgs_complete'),reason='No exact 7000 complete checkpoint; PLY has no accumulated position gradient')
            if row['checkpoint']:
                assert sha(row['checkpoint'])==lock['files'][row['checkpoint']]
                c=torch.load(row['checkpoint'],map_location='cpu');m=c['model']
                assert np.array_equal(xyz,m[1].detach().numpy()) and np.array_equal(ids,c['init_id'].detach().numpy())
                accum=m[8].detach().numpy().reshape(-1);denom=m[9].detach().numpy().reshape(-1)
                with np.errstate(invalid='ignore',divide='ignore'):g=accum/denom
                g[np.isnan(g)]=0;threshold=c['optimization']['densify_grad_threshold']
                a.update(gradient_accum=accum,gradient_denom=denom,gradient=g,gradient_above=g>=threshold)
                grad=dict(status='AVAILABLE',threshold=threshold,total_above=int((g>=threshold).sum()),denom_positive=int((denom>0).sum()),checkpoint=row['checkpoint'])
                del c,m;gc.collect()
        np.savez_compressed(dest/'arrays.npz',**a)
        summary=dict(key=key,gaussians=len(v),tags={str(t):int((tags==t).sum()) for t in np.unique(tags)},
            released_at100=int(((tags==2)&(release==100)).sum()) if row['family']!='base' else None,gradient=grad,
            arrays_sha256=sha(dest/'arrays.npz'),scientific_verdict=None)
        dump(dest/'inventory.json',summary);result.append(summary);print('INVENTORY',key,len(v),grad['status'],flush=True)
        del v,a,xyz,scale,opacity;gc.collect()
    baseline=[]
    for prior in ['ALS','LoD2']:
        base=PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs/B173nb_b10'/f'nojudge_{prior}_s0'
        rows=[json.loads(x) for x in (base/'model/jbgs_trace.jsonl').read_text().splitlines()]
        fields=['peak_cuda_allocated_bytes','peak_cuda_reserved_bytes']
        entry=dict(prior=prior,gaussians_30000=next(r['gaussians'] for r in result if r['key']==f'base_{prior}_30000'),
            memory={f:max((r[f] for r in rows if f in r),default=None) for f in fields},
            records_14000_15000=[{k:r[k] for k in ['iteration','gaussians']+fields if k in r} for r in rows if 14000<=r['iteration']<=15000],
            sources={str(base/'model/jbgs_trace.jsonl'):sha(base/'model/jbgs_trace.jsonl'),str(base/'receipt.json'):sha(base/'receipt.json')},
            note='Memory peaks cumulative from original process start; GPU model requires original environment record')
        baseline.append(entry)
    dump(ROOT/'inventory.json',dict(at=stamp(),states=result,baseline=baseline,training=False,scientific_verdict=None))

if __name__=='__main__':main()
