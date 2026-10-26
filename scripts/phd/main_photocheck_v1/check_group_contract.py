"""Independently verify ALS common surface origin and 0.5m cell ownership."""
from common import *
def main():
    records=[]
    for sealed in [False,True]:
      base=paths(sealed)
      for f in (base/'geometry').glob('*__ALS.npz'):
        tile=f.stem.split('__')[0];g=npz(f);mp=npz(f.with_name(f.stem+'__mapping.npz'))
        source=W/('holdout/patch_values' if sealed else 'patch_values')/f'{tile}__ALS__R1.5.npz'
        with np.load(source) as z:d={k:z[k][mp['source_index']] for k in ['centre','surf','kind','source_extra','area','building']}
        with np.load(W/'holdout/internal/patch_geometry'/f'{tile}_ALS.npz') as z:globald={k:z[k] for k in ['centre','surf','kind','source_extra']}
        checked=0;multi=0
        for face in np.unique(d['surf']):
          for kind in np.unique(d['kind'][d['surf']==face]):
            ids=np.flatnonzero((d['surf']==face)&(d['kind']==kind)&~d['source_extra'])
            if not len(ids):continue
            gm=(globald['surf']==face)&(globald['kind']==kind)&~globald['source_extra'];origin=globald['centre'][gm,:2].min(0)
            uv=np.floor((d['centre'][ids,:2]-origin)/.5+1e-7).astype(np.int64)
            # Independent dictionary: exactly one output point per inherited surface cell.
            cell_points={};point_cells={}
            for j,cell in zip(ids,map(tuple,uv)):
                p=int(mp['point_index'][j]);cell_points.setdefault(cell,set()).add(p);point_cells.setdefault(p,set()).add(cell)
            assert all(len(v)==1 for v in cell_points.values()),(tile,face,'cell split')
            assert all(len(v)==1 for v in point_cells.values()),(tile,face,'cells merged')
            checked+=len(ids)
        if len(g['point_id']):multi=sum(';' in x for x in g['building_ids'])
        records.append(dict(tile=tile,holdout=sealed,regular_patches_checked=checked,multi_building_points=multi))
    # Sealed details remain in holdout; public receipt gives only completion status.
    dump(O/'holdout/group_contract_details.json',dict(rows=records,scientific_verdict=None))
    dump(O/'gates/group_contract.json',dict(status='PASS',development_rows=[r for r in records if not r['holdout']],holdout_verification_sha256=sha(O/'holdout/group_contract_details.json'),environment=env()))
    print('surface grid contract PASS',sum(r['regular_patches_checked'] for r in records),'regular patches')
if __name__=='__main__':main()
