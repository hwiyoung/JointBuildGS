"""Stage 2 preparation (host python, json only; run once 2026-11-19 02:10): TRAINLOG config configs/.../trainlog_gtt.json from the TRAINERR
trainlog_te.json (save iterations and scene dumps replaced by gttarget_v1.json 'training'), and whole-box record ranges /gt/region/<stem>.json
(GTJUDGE views/<site>.json box padded 1 m, 1 m voxels, one box: every Gaussian in the scene box is recorded)."""
import json, math, os
from pathlib import Path
R = Path(__file__).resolve().parents[3]; PH = R.parent/'JointBuildGS-artifacts/phase-payloads/phd'; O = PH/'main_gttarget_v1/PHD-MAIN-GTTARGET-v1'
src = json.load(open(R/'configs/phd/main_trainerr_v1/trainlog_te.json')); c = json.load(open(R/'configs/phd/main_gttarget_v1/gttarget_v1.json'))['training']
tl = dict(src['training_log']); tl['save_iterations'] = c['save_iterations']; tl['scene_dump'] = c['scene_dump']
tl['save_rule'] = {'listed': 'order 6.1 scene saves; every actual opacity reset also saves <it>_pre_reset (states) and the listed ones also the whole scene'}
json.dump(dict(training_log=tl, coordinates=src['coordinates'], note='PHD-MAIN-GTTARGET-v1: TRAINLOG read-only record; range = whole scene box (region/<stem>.json, 1 m voxels); gradients off',
               scientific_verdict=None), open(R/'configs/phd/main_gttarget_v1/trainlog_gtt.json', 'w'), ensure_ascii=False, indent=1)
for site in ['B0_b10', 'B173nb_b10', 'R1rep_b10']:
    b = json.load(open(PH/f'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1/views/{site}.json'))['box']
    lo = [math.floor(x)-1 for x in b[0]]; hi = [math.ceil(x)+1 for x in b[1]]; shape = [h-l for l, h in zip(lo, hi)]
    reg = dict(site=site, boxes=[[lo[0], hi[0], lo[1], hi[1], lo[2], hi[2], 0]], box_columns=['xmin', 'xmax', 'ymin', 'ymax', 'zmin', 'zmax', 'n'], voxel_m=1.0, grid_origin=lo,
               grid_shape=shape, occupied_voxels=shape[0]*shape[1]*shape[2], rule='whole scene view box (GTJUDGE views/<site>.json) padded 1 m, 1 m voxels: every Gaussian in the box is recorded',
               scientific_verdict=None)
    for prior in ['ALS', 'LoD2']:
        p = O/'region'/f'{site}__{prior}.json'; os.makedirs(p.parent, exist_ok=True); json.dump(dict(reg, stem=f'{site}__{prior}'), open(p, 'w'), indent=1)
print('ok')
