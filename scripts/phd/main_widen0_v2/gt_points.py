"""Inherited stage-1 v3 nadir point cleaning and frozen common height shift.

Uses no manual LiDAR. Whole-area values are never substituted by the old B0 mix.
"""
import json
from pathlib import Path
import numpy as np
from preflight import PH,dump,sha
from tile_points import DT

O=Path('/out')
S=PH/'main_design_realchange_survey_v1/PHD-MAIN-DESIGN-REALCHANGE-SURVEY-v1'
def main():
    G=np.load(S/'derived.npz');A=np.load(S/'s1/rasters_als_mvs_uls.npz')
    uls,mvs,als,veg=G['uls'],G['mvs'],G['als'],G['veg']
    n=A['als_n'];mult=A['als_n_multi']/np.maximum(n,1);c20=A['als_n_c20']/np.maximum(n,1)
    trans=(uls>np.fmax(mvs,als)+1.5)&np.isfinite(mvs)&np.isfinite(uls)
    trees=(veg>.3)|((c20>.5)&(mult>.5));excl=trees|trans
    top=np.fmax(mvs,als)-604.+.75
    shift_path=PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1/v3/align/common_shift.json'
    shift=json.loads(shift_path.read_text())['common_shift_m']
    ny,nx=excl.shape
    for tile in json.loads((O/'inputs/tiles.json').read_text()):
        tid=tile['id'];dst=O/'holdout/internal/points'/tid;dst.mkdir(parents=True,exist_ok=True)
        if (dst/'gt.json').exists():continue
        arr=np.memmap(O/'inputs/points'/tid/'uls.bin',mode='r',dtype=DT)
        X=np.column_stack([arr[k] for k in ['x','y','z']])
        ix=np.floor((X[:,0]+690953.-690700.)/.5).astype(np.int64)
        iy=np.floor((X[:,1]+5336071.-5335820.)/.5).astype(np.int64)
        ing=(ix>=0)&(ix<nx)&(iy>=0)&(iy<ny)
        keep=ing.copy();ids=np.flatnonzero(ing)
        # The uncertainty task excludes the complete tree/transient cells after stage-1 cleaning.
        keep[ids]&=~excl[iy[ids],ix[ids]]
        Y=X[keep];Y[:,2]+=shift
        np.save(dst/'gt_xyz.npy',Y)
        dump(dst/'gt.json',dict(tile=tid,raw_points=len(X),kept=len(Y),outside_existing_exclusion_grid=int((~ing).sum()),
            common_shift_m=shift,common_shift_sha256=sha(shift_path),manual_uls=False,
            source='stage-1 v3 common shift and main_uncert_v1 GT exclusion rule; original raw nadir points',
            scientific_verdict=None))
        print('nadir GT source prepared',tid,flush=True)

if __name__=='__main__':main()
