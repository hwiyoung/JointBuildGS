"""PHD-MAIN-DESIGN-REALCHANGE-SURVEY-v1 step 6: report tables.

  candidates.csv   every ULS-based component (|d| > 2.5 m, >= 25 m2) + R1 Z08 with
                   magnitudes vs ALS and LoD2, agreement of the other prior, views,
                   analyst label (visual_labels_v1.json; LoD2-only default rule)
  crosscheck_199.csv  existing journal1 change tiers / AX-10 user labels vs this survey
  region_views.json   R1-R5 view counts split nadir (<= 20 deg) / oblique from the
                   frozen region_view_support candidate lists
scientific_verdict: null."""
import csv
import json
import sys
from pathlib import Path

import numpy as np
from matplotlib.path import Path as MPath

out = Path(sys.argv[1]); cfg = json.loads(Path(sys.argv[2]).read_text()); labels = json.loads(Path(sys.argv[3]).read_text())
art = Path(cfg['artifact_root_container'])
D = dict(np.load(out / 'derived.npz'))
g = cfg['grid']; res = g['res_m']
ny, nx = D['dtm'].shape
ec = g['e_min'] + (np.arange(nx) + 0.5) * res; nc = g['n_min'] + (np.arange(ny) + 0.5) * res
EE, NN = np.meshgrid(ec, nc); pts = np.column_stack([EE.ravel(), NN.ravel()])
dtm = D['dtm'].astype(float)
nd = {k: D[k].astype(float) - dtm for k in ('uls', 'mvs', 'als')}
fid = D['fid']
nd['lod'] = np.where(np.isfinite(D['lod']), D['lod'].astype(float) - dtm, np.where(fid >= 0, np.nan, 0.0))
veg = (D['veg'] > 0.3) | ((D['als_veg'] > 0.5) & (D['als_n_c6'] == 0))
tv = {r['tid']: r for r in json.loads((out / 'targets_views.json').read_text())}
regs = json.loads((out / 'regions.json').read_text())
reg_masks = {rid: MPath(np.array(r['corners_epsg25832'])).contains_points(pts).reshape(ny, nx) for rid, r in regs.items()}
blds = json.loads((out / 's1' / 'lod2_buildings.json').read_text())


def med(x):
    x = x[np.isfinite(x)]
    return round(float(np.median(x)), 2) if len(x) else None


rows = []
for tid, r in tv.items():
    if r['kind'] not in ('component', 'zone'):
        continue
    poly = np.array(r['poly'])
    inside = MPath(poly).contains_points(pts).reshape(ny, nx)
    if r['kind'] == 'zone':
        m = inside & (nd['als'] > 2.5) & (nd['uls'] < 1.0)
        prior = 'als'; sign = -1
    else:
        prior = 'als' if r['prior'] == 'als' else 'lod'
        sign = -1 if r['d_med'] < 0 else 1
        d = nd['uls'] - nd[prior]
        m = inside & np.isfinite(d) & (np.abs(d) > 2.5) & (np.sign(d) == sign) & ~veg
    area = float(m.sum()) * res * res
    rec = dict(tid=tid, screen_prior='ALS' if prior == 'als' else 'LoD2', area_m2=round(area, 1),
               e=round(float(EE[m].mean()), 1) if m.any() else None, n=round(float(NN[m].mean()), 1) if m.any() else None,
               h_uls=med(nd['uls'][m]), h_mvs=med(nd['mvs'][m]), h_als=med(nd['als'][m]), h_lod2=med(nd['lod'][m]),
               d_uls_als=med((nd['uls'] - nd['als'])[m]), d_uls_lod2=med((nd['uls'] - nd['lod'])[m]),
               d_mvs_als=med((nd['mvs'] - nd['als'])[m]), d_mvs_lod2=med((nd['mvs'] - nd['lod'])[m]),
               als_c6_share=round(float((D['als_n_c6'][m] > 0).mean()), 2) if m.any() else None,
               lod2_footprint_share=round(float((fid[m] >= 0).mean()), 2) if m.any() else None,
               buildings=r.get('buildings', ''), regions=';'.join(rid for rid, mk in reg_masks.items() if (mk & m).sum() > 0.05 * max(m.sum(), 1)),
               views_cover=r['n_cover'], views_cover_nadir=r['n_cover_nadir'], views_cover_oblique=r['n_cover_oblique'],
               views_depth_consistent=r['n_consistent'], views_consistent_nadir=r['n_consistent_nadir'], views_consistent_oblique=r['n_consistent_oblique'],
               crop=(r.get('crop_nadir') or {}).get('image'))
    lab = labels['labels'].get(tid)
    a_als = abs(rec['d_uls_als']) if rec['d_uls_als'] is not None else None
    a_lod = abs(rec['d_uls_lod2']) if rec['d_uls_lod2'] is not None else None
    if lab is None:
        if prior == 'lod' and a_als is not None and a_als < 0.5:
            lab = dict(cat='LOD2_ONLY', basis='LoD2', type_ko='LoD2만 다름', note_ko='항공 LiDAR 2022와 현재가 일치(|ULS-ALS| 중앙값 %.2f m)' % a_als)
        else:
            lab = dict(cat='UNCERTAIN', basis='?', type_ko='판정 보류', note_ko='자동 규칙 밖')
    rec.update(category=lab['cat'], basis=lab['basis'], type_ko=lab['type_ko'], note_ko=lab['note_ko'])
    # magnitude of change with respect to each prior, independent of the screen
    rec['change_vs_ALS'] = bool(a_als is not None and a_als > 2.5)
    rec['change_vs_LoD2'] = bool(a_lod is not None and a_lod > 2.5)
    rows.append(rec)
keys = list(rows[0].keys())
with open(out / 'candidates.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); [w.writerow(r) for r in rows]
print('candidates', len(rows))
for r in rows:
    print(r['tid'], r['category'], r['basis'], r['area_m2'], 'dALS', r['d_uls_als'], 'dLoD2', r['d_uls_lod2'], 'h', r['h_uls'], r['h_als'], r['h_lod2'],
          'views', r['views_cover'], r['views_cover_nadir'], r['views_cover_oblique'], 'cons', r['views_depth_consistent'], r['regions'], r['buildings'][:30], r['type_ko'])

# ---- cross-check with the journal1 change tiers and AX-10 user labels -------------------------
tiers = {r['stable_id']: r for r in csv.DictReader(open(art / cfg['inputs']['change_label_candidates_199']))}
ax10 = json.loads((art / 'phase-payloads/p2/arrgs_v1/P2-ARRGS-AX10-v1/population_2x2.json').read_text())
user = {}
for cell, v in ax10['tables']['user_adjusted']['cells'].items():
    for s in v.get('stable_ids', []):
        user[s] = cell
bstats = {r['id']: r for r in csv.DictReader(open(out / 'buildings.csv'))}
fidx = {b['id']: i for i, b in enumerate(blds)}
cx = []
for sid, t in tiers.items():
    b = bstats.get(sid, {})
    linked = [r['tid'] + ':' + r['category'] for r in rows if sid.replace('DEBY_LOD2_', '') in r['buildings']]
    cx.append(dict(stable_id=sid, tier=t['tier'], e1_lod2_completeness=t['e1_lod2_completeness@0.5'], e1_lod2_acc_median=t['e1_lod2_acc_median_m'],
                   ax10_user=user.get(sid, 'not_in_93'), uls_cover=b.get('uls_cover'), h_uls=b.get('h_uls'), h_als=b.get('h_als'), h_lod2=b.get('h_lod2'),
                   uls_lod2_med=b.get('uls_lod2__med'), uls_lod2_area25=b.get('uls_lod2__comp_area2.5'), uls_als_med=b.get('uls_als__med'),
                   uls_als_area25=b.get('uls_als__comp_area2.5'), als_lod2_med=b.get('als_lod2__med'), linked_components=';'.join(linked),
                   creationDate=b.get('creationDate'), regions=b.get('regions')))
with open(out / 'crosscheck_199.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(cx[0].keys())); w.writeheader(); [w.writerow(r) for r in cx]
print('crosscheck rows', len(cx))
for r in cx:
    if r['tier'] in ('A_STRONG_MISMATCH',) or r['ax10_user'].startswith('change'):
        print(r['stable_id'].replace('DEBY_LOD2_', ''), r['tier'][:1], r['ax10_user'], 'cov', r['uls_cover'], 'h', r['h_uls'], r['h_als'], r['h_lod2'],
              'ULS-LoD2', r['uls_lod2_med'], r['uls_lod2_area25'], 'ULS-ALS', r['uls_als_med'], r['uls_als_area25'], r['linked_components'], r['regions'])

# ---- region views split by tilt ---------------------------------------------------------------
tilts = json.loads((out / 'image_tilts.json').read_text())
exp = art / cfg['inputs']['region_view_exports']
rv = {}
for rid in ('R1', 'R2', 'R3', 'R4', 'R5'):
    d = {}
    for part in ('candidates', 'train', 'evaluation'):
        names = [l.strip() for l in open(exp / ('%s_%s_names.txt' % (rid, part))) if l.strip()]
        tt = np.array([tilts[nm] for nm in names])
        d[part] = dict(total=len(names), nadir=int((tt <= 20).sum()), oblique=int((tt > 20).sum()), oblique_gt45=int((tt > 45).sum()))
    rv[rid] = d
(out / 'region_views.json').write_text(json.dumps(rv, indent=1))
print(json.dumps(rv))
