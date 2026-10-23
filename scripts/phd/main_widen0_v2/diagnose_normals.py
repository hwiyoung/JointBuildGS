"""Inspect inherited source normal lengths without reading GT patch outcomes."""
import json
from pathlib import Path
import numpy as np
from preflight import dump
O=Path('/out');R=O/'holdout/internal'
def main():
    cover=np.load(O/'inputs/coverage.npz');mask=cover['common'];ny,nx=mask.shape
    e0,n0,res=float(cover['e0']),float(cover['n0']),float(cover['res'])
    rows=[]
    for tile in json.loads((O/'inputs/tiles.json').read_text()):
        for prior in ['lod2','als']:
            with np.load(R/'prior_tiles'/tile['id']/f'{prior}_store.npz') as st:
                c=st['loc_center'];cross=np.cross(st['loc_t1'],st['loc_t2']);raw=np.linalg.norm(cross,axis=1)
                normal=cross/np.maximum(raw[:,None],1e-12);norm=np.linalg.norm(normal,axis=1)
                x0,y0,x1,y1=tile['core_global'];core=(c[:,0]+690953>=x0)&(c[:,0]+690953<x1)&(c[:,1]+5336071>=y0)&(c[:,1]+5336071<y1)
                ix=np.floor((c[:,0]+690953-e0)/res).astype(int);iy=np.floor((c[:,1]+5336071-n0)/res).astype(int)
                inside=(ix>=0)&(ix<nx)&(iy>=0)&(iy<ny);ii=np.flatnonzero(inside)
                common=np.zeros(len(c),bool);common[ii]=mask[iy[ii],ix[ii]]
                candidate=core&common;bad=candidate&~np.isclose(norm,1.,atol=1e-6)
                assert np.all(st['loc_extra'][bad]) and np.all(raw[bad]==0.)
                if not bad.any():continue
                area=st['loc_area'][bad]
                rows.append(dict(tile=tile['id'],prior=prior,source_candidates=int(candidate.sum()),
                    nonunit_count=int(bad.sum()),nonunit_area_m2=float(area.sum()),zero_area_count=int((area==0).sum()),
                    raw_cross_norm_min=float(raw[bad].min()),raw_cross_norm_max=float(raw[bad].max()),
                    normal_length_min=float(norm[bad].min()),normal_length_max=float(norm[bad].max()),
                    patch_area_min=float(area.min()),patch_area_max=float(area.max())))
    dump(R/'diagnostics/source_normals.json',dict(rows=rows,scientific_verdict=None))
    for prior in ['lod2','als']:
        rr=[r for r in rows if r['prior']==prior]
        print(prior,'affected tiles',len(rr),'nonunit source candidates',sum(r['nonunit_count'] for r in rr),'area m2',sum(r['nonunit_area_m2'] for r in rr),flush=True)
    print('source normal audit complete')
if __name__=='__main__':main()
