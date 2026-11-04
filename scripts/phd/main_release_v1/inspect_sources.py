from common import *
import sys
sys.path.append('/repo/scripts/phd/main_rescore_v1')
def main():
    c=cfg(); rows=[]
    for site in SITES:
        for prior in ['ALS','LoD2']:
            for method in c['stage0']['methods']:
                root=score_dir(site,prior,method); p=root/'values.json'; v=json.loads(p.read_text())
                z=np.load(root/'points.npz'); rows.append(dict(site=site,prior=prior,method=method,score=str(p),score_sha256=sha(p),points=str(root/'points.npz'),points_sha256=sha(root/'points.npz'),mesh=v['mesh'],mesh_sha256=v['mesh_sha256'],n_gt=v['scene']['n_gt'],row_shape=z['row_distance_m'].shape[0],sample_shape=z['sample_owner'].shape[0]))
            if site=='R1rep_b10':
                rec=json.loads((FT/'runs'/site/f'ft_{prior}_s0/receipt.json').read_text())
                model=FT/Path(rec['attempts'][-1]['model']).relative_to('/out')
                s=np.load(model/'target_monitor/snapshot_30000.npz')
                print('SNAPSHOT',prior,{k:list(s[k].shape) for k in s.files},flush=True)
            t=np.load(FT/'targets'/f'{site}__{prior}.npz');print('TARGET',site,prior,{k:list(t[k].shape) for k in t.files},flush=True)
    dump(C/'score_inputs.lock.json',dict(at=now(),rows=rows,scientific_verdict=None));print('SOURCE_LOCK',len(rows),flush=True)
if __name__=='__main__':main()
