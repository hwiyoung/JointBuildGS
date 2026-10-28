"""Inspect exact raw-geometry joins without generating visibility or region labels."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from patch_units import locked,dump
PH=Path('/ph');W=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2/patch_values';S=PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1/regions_v3'
def main():
    locked();rows=[]
    for prior in ['ALS','LoD2']:
        refs=[]
        for site in ['B0_b10','B173nb_b10','B173_b0','R1rep_b10']:
            r=dict(np.load(S/f'regions_ext_v3_{site}_{prior}.npz'));q=r['centre']-r['frame_shift']
            refs.append((site,r,cKDTree(q),q))
        accum={site:dict(exact=0,raw_lt005=0,raw_lt025=0,registered_lt005=0,area_exact=0.,within_reference_bbox=0,ref_area=float(r['area'][r['in_eval']].sum()),frame_shift=r['frame_shift'].tolist()) for site,r,_,_ in refs}
        for f in sorted(W.glob(f'*__{prior}__R1.5.npz')):
            with np.load(f) as z:
                c=z['raw_centre'];reg=z['centre'];a=z['area'];kind=z['kind']
            if not len(c):continue
            for site,r,tr,q in refs:
                ids=np.flatnonzero(((c>=q.min(0)-.5)&(c<=q.max(0)+.5)).all(1))
                if not len(ids):continue
                dist,j=tr.query(c[ids]);inev=r['in_eval'][j]
                exact=(dist<1e-6)&(kind[ids]==r['kind'][j])&np.isclose(a[ids],r['area'][j],rtol=1e-8,atol=1e-9)&inev
                ac=accum[site];ac['exact']+=int(exact.sum());ac['area_exact']+=float(a[ids][exact].sum())
                ac['raw_lt005']+=int(((dist<.05)&inev).sum());ac['raw_lt025']+=int(((dist<.25)&inev).sum());ac['within_reference_bbox']+=len(ids)
                dr,jr=cKDTree(r['centre']).query(reg[ids]);ac['registered_lt005']+=int(((dr<.05)&r['in_eval'][jr]).sum())
        for site,ac in accum.items():rows.append(dict(prior=prior,site=site,**ac));print(prior,site,ac,flush=True)
    dump('/docs/tables/region_identity_probe.json',dict(rows=rows,scientific_verdict=None,labels_transferred=False,provenance='[이 발주에서 냄]'))
if __name__=='__main__':main()
