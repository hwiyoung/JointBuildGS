import sys, json, numpy as np
from zones import *
region, task, fp_path, out = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
prior = np.load(f'{task}/evaluation/geometry/{region}/prior_mesh/sample0.1_reference0.1.npz')
R = prior['reference_points']; d_rp = prior['reference_to_triangle_distance']
fp_fn, ids = load_footprint_mask_fn(fp_path, region)
ras = build_zone_raster(region, R, d_rp, fp_fn)
labels = zone_labels(region, ras)
ref_lab = label_points(region, ras, labels, R[:, :2])
zones = [z for z in sorted(set(labels)) if z != 'empty']
print('region', region, 'footprints', ids, 'ref points', len(R))
print('cells per zone:', {z: int((labels == z).sum()) for z in zones})
cands = ['prior_mesh', 'als_points', 'mvs_points', 'D005_Pnative.final.raw', 'D0005_Pnative.final.raw', 'D0_Pnative.final.raw',
         'D005_Prelease.final.raw', 'D0005_Prelease.final.raw', 'D0_Prelease.final.raw', 'D005_Pnative.final.post', 'D0005_Pnative.final.post']
rows = []
for c in cands:
    try:
        z = np.load(f'{task}/evaluation/geometry/{region}/{c}/sample0.1_reference0.1.npz')
    except FileNotFoundError:
        continue
    S = z['prediction_surface_samples']; ds = z['prediction_to_reference_distance']
    dr = z['reference_to_triangle_distance'] if 'reference_to_triangle_distance' in z.files else z['reference_to_candidate_distance']
    s_lab = label_points(region, ras, labels, S[:, :2])
    for zn in ['ALL'] + zones:
        ms = np.ones(len(S), bool) if zn == 'ALL' else (s_lab == zn)
        mr = np.ones(len(R), bool) if zn == 'ALL' else (ref_lab == zn)
        for tau in [0.25, 0.5, 1.0]:
            p = float((ds[ms] <= tau).mean()) if ms.sum() else float('nan')
            r = float((dr[mr] <= tau).mean()) if mr.sum() else float('nan')
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            rows.append(dict(region=region, candidate=c, zone=zn, tau=tau, precision=p, recall=r, f1=f1,
                             n_samples=int(ms.sum()), n_ref=int(mr.sum()),
                             mean_p2r=float(ds[ms].mean()) if ms.sum() else float('nan'), mean_r2p=float(dr[mr].mean()) if mr.sum() else float('nan')))
import csv
with open(f'{out}/zone_f1_{region}.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
# compact print: F1@0.5 per candidate x zone
print('\nF1@0.5 (precision/recall) by zone')
hdr = ['candidate'] + ['ALL'] + zones
print('\t'.join(hdr))
for c in cands:
    rr = [x for x in rows if x['candidate'] == c and x['tau'] == 0.5]
    if not rr: continue
    line = [c]
    for zn in ['ALL'] + zones:
        x = [y for y in rr if y['zone'] == zn]
        line.append('%.3f(%.2f/%.2f)' % (x[0]['f1'], x[0]['precision'], x[0]['recall']) if x else '-')
    print('\t'.join(line))
print('\nzone n_ref:', {zn: int((ref_lab == zn).sum()) for zn in zones})
np.savez(f'{out}/zone_raster_{region}.npz', labels=labels.astype(str), nx=ras['nx'], ny=ras['ny'], ground_z=ras['ground_z'], prior_state=ras['prior_state'], elevated=ras['elevated'], footprint=ras['footprint'])
