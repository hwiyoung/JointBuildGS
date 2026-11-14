"""Work sa values (order 8) after the meshes. CPU.
  sa2 : B0 x LoD2 occlusion-mask run: visible-wall completeness (7000/10000/15000/30000), south wall (result points behind > 0.64 m, wall accuracy, wall completeness),
        edge-band bound Gaussians, scene values, masked-pixel share per place; beside the record run, the original run and addendum-3 ba1 / ba2b
  sa3 : B173 x ALS judgment-off run: edge floater area, building-scope area > 1 m from GT, scene values, Gaussians within 0.5 m of its edge-floater faces"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4')
from a4_common import *
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum3')
from a3_ra_out import face_values, scope
SA2 = A4O/'runs/B0_b10/sa2_B0_LoD2_occlmask/attempt1/model'; SA3 = A4O/'runs/B173nb_b10/sa3_B173_ALS_nojudge/attempt1/model'; ITS = ['7000', '10000', '15000', '30000']

def scene_rows(score_json, label, it):
    if not Path(score_json).exists(): return []
    return [dict(run=label, iteration=int(it), surface=x['surface'], case_id=str(x['case_id']), n_gt=x['n_gt'], completeness_pct=x['completeness_pct'], accuracy_pct=x.get('accuracy_pct'))
            for x in json.loads(Path(score_json).read_text())['rows'] if x['surface'] in ('all', 'wall', 'roof') and str(x['case_id']) in ('all', '1', '2')]

def comp_of(dist_npz, P):
    if not Path(dist_npz).exists(): return None
    rs = loadz(dist_npz, ['row_s'])['row_s']; tau = loadz(GT/'scenes/B0_b10__LoD2/rows.npz', ['row_tau_m'])['row_tau_m']; v = rs[P['point_id']]
    return 100*float((np.isfinite(v) & (np.abs(v) <= tau[P['point_id']])).mean())

def sa2():
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum1'); import a1_common as A1
    places = {p: place_points(p) for p in ['visible_low', 'visible_high', 'visible_side', 'south_wall', 'long_wall', 'edge_back', 'edge_annex']}
    runs = [('사-2 가림 화소 감독 끔', A4O/'gtj/scenes/B0_b10__LoD2/distances', 'sa2_{}', A4O/'meshes', A4O/'gtj/meshes'),
            ('기록 판(TRAINLOG)', TLC/'gtj/scenes/B0_b10__LoD2/distances', 'tl_{}', TLC/'meshes', TLC/'gtj/meshes'),
            ('바-1 법선 항 없음', A3O/'gtj/scenes/B0_b10__LoD2/distances', 'ba1_{}', A3O/'meshes', A3O/'gtj/meshes'),
            ('바-2 다시 학습(재설정 7,000 뒤 없음)', A3O/'gtj/scenes/B0_b10__LoD2/distances', 'ba2b_{}', A3O/'meshes', A3O/'gtj/meshes')]
    comp = []; scene = []; south = []
    for lab, dd, fam, md, gm in runs:
        for it in ITS:
            f = fam.format(it); r = dict(run=lab, iteration=int(it))
            for p in ['visible_low', 'visible_high', 'visible_side', 'south_wall', 'long_wall', 'edge_back', 'edge_annex']: r[f'{p}_completeness_pct'] = comp_of(dd/f'{f}.npz', places[p])
            comp.append(r); scene += scene_rows(md/f'B0_b10__LoD2__{f}'/'score.json', lab, it)
            pz = md/f'B0_b10__LoD2__{f}'/'points.npz'
            if pz.exists():
                z = loadz(pz, ['result__xyz', 'result__eligible_new', 'result__within_tau1']); X = z['result__xyz'].astype('f8'); a_, d_, zone = A1.wall_coords(X, 'south'); e = z['result__eligible_new'].astype(bool); w = z['result__within_tau1'].astype(bool)
                sw = A1.acfg()['places']['south_wall']; zz = (a_ >= sw['along_m'][0]) & (a_ <= sw['along_m'][1]) & (X[:, 2] >= sw['z_m'][0]) & (X[:, 2] <= sw['z_m'][1])
                south.append(dict(run=lab, iteration=int(it), south_zone_result_points=int(zone.sum()), south_behind_064_pct=pct(d_[zone] < -.64) if zone.any() else None,
                                  behind_064_points_any_offset=int((zz & (d_ < -.64)).sum()), south_wall_accuracy_pct=100*float((zone & e & w).sum())/max(1, int((zone & e).sum())),
                                  south_wall_completeness_pct=r['south_wall_completeness_pct']))
    # original FINALTRAIN run (30000 only): GTJUDGE addendum11
    A = np.load(GT/'addendum11/final_data/B0_b10__LoD2.npz'); lut = {int(p): i for i, p in enumerate(A['reference__point_id'])}; wv = A['reference__FINALTRAIN_30000__within_tau1'].astype(bool)
    r = dict(run='원래 판(FINALTRAIN)', iteration=30000)
    for p, P in places.items():
        ii = [lut[int(i)] for i in P['point_id'] if int(i) in lut]; r[f'{p}_completeness_pct'] = 100*float(wv[ii].mean()) if ii else None
    comp.append(r)
    dtable('sa2_place_completeness', comp); dtable('sa2_scene_values', scene); dtable('sa2_south_wall', south)
    # masked pixel share per place (all training views)
    mz = np.load(SA2/'a4_occl_mask/masked_pixels.npz'); md, = [maps_dir('B0_b10__LoD2', 'own')]; mi = json.loads((md/'index.json').read_text())['views']; rows = []
    praw = {p: np.unique(P['patch_row'][P['patch_row'] >= 0]) for p, P in places.items()}; tot = {p: 0 for p in praw}; msk = {p: 0 for p in praw}
    for nm, m in mi.items():
        with np.load(md/m['file']) as z: own = z['owner']; w0 = z['weight']
        mk = mz[nm] & (w0 > 0)
        for p, pr in praw.items():
            s = np.isin(own, pr); tot[p] += int((s & (w0 > 0)).sum()); msk[p] += int((s & mk).sum())
    rows = [dict(place=p, place_ko=PLACE_KO.get(p, p), target_pixels=tot[p], masked_pixels=msk[p], masked_pct=100*msk[p]/max(1, tot[p])) for p in praw]
    js = json.loads((SA2/'a4_occl_mask/summary.json').read_text())['totals']; rows.append(dict(place='scene', place_ko='장면 전체', target_pixels=js['target_pixels'], masked_pixels=js['masked'], masked_pct=100*js['masked']/js['target_pixels']))
    dtable('sa2_masked_pixels', rows)
    # edge-band bound Gaussians (scene dumps)
    eb = []
    for lab, model in [('사-2', SA2), ('기록 판(TRAINLOG)', TLC/'runs/B0_b10/tl_B0_b10_LoD2_s0/attempt1/model')]:
        for st in ['0', '1000', '3000_pre_reset', '6000_pre_reset', '7000', '15000', '30000']:
            p = model/'trainlog/scene'/f'{st}.pt'
            if not p.exists(): continue
            import torch; s = torch.load(p, map_location='cpu', weights_only=False); tg = s['target_tag'].numpy(); ti = s['target_index'].numpy()
            eb.append(dict(run=lab, state=st, **{f'{q}_bound': int(((tg == 1) & np.isin(ti, np.unique(places[q]['v'][places[q]['v'] >= 0]))).sum()) for q in ['edge_back', 'edge_annex', 'visible_low', 'visible_high', 'south_wall']}))
    dtable('sa2_bound_counts', eb); print('SA2 done', flush=True)

def sa3():
    import torch, shapely
    rows = []; scene = []
    for lab, gm, md, fam in [('사-3 판단 끔', A4O/'gtj/meshes', A4O/'meshes', 'sa3_{}'), ('본 방법 기록 판(TRAINLOG)', TLM/'gtj/meshes', TLM/'meshes', 'tl_{}')]:
        for it in ITS:
            f = fam.format(it); p = gm/f'B173nb_b10__ALS__{f}'/'final.ply'
            if not p.exists(): continue
            r = dict(run=lab, iteration=int(it), **face_values('B173nb_b10__ALS', p)); rows.append(r); scene += scene_rows(md/f'B173nb_b10__ALS__{f}'/'score.json', lab, it); print('SA3', r, flush=True)
    dtable('sa3_floater', rows); dtable('sa3_scene_values', scene)
    # Gaussians within 0.5 m of the sa-3 30000 edge-floater faces
    from a3_ga import load_mesh
    fp, g0 = scope('B173nb_b10__ALS'); V, F = load_mesh(A4O/'gtj/meshes/B173nb_b10__ALS__sa3_30000/final.ply'); ctr = V[F].mean(1); h = ctr[:, 2]-g0
    de = shapely.distance(fp, shapely.points(ctr[:, 0], ctr[:, 1])); G = cKDTree(loadz(GT/'reference/B173nb_b10/dense.npz', ['xyz'])['xyz'].astype('f8')); q = (h >= 12) & (de <= 3) & (de > 0)
    dg = np.full(len(F), np.nan); dg[q] = G.query(ctr[q], workers=8)[0]; C = ctr[q & (dg > 1.)]; out = []
    for lab, model in [('사-3 판단 끔', SA3), ('본 방법 기록 판(TRAINLOG)', RUNS4['tl_B173nb_b10_ALS_s0']['model'])]:
        s = torch.load(model/'trainlog/scene/30000.pt', map_location='cpu', weights_only=False); X = s['xyz'].double().numpy()
        if not len(C): out.append(dict(run=lab, floater_faces=0)); continue
        lo = C.min(0)-.6; hi = C.max(0)+.6; k = np.flatnonzero(np.all((X >= lo) & (X <= hi), 1)); d, _ = cKDTree(C).query(X[k]); g = k[d <= .5]; tg = s['target_tag'].numpy()[g]
        out.append(dict(run=lab, faces='사-3 30,000회 가장자리 뜬 면', floater_faces=int(len(C)), gaussians=len(g), bound=int((tg == 1).sum()), released=int((tg == 2).sum()), unbound=int((tg == 0).sum()),
                        prior_lineage_pct=pct(s['origin'].numpy()[g] == 1), child_pct=pct(s['born_how'].numpy()[g] >= 2), opacity_median=med(torch.sigmoid(s['opacity'][g, 0]).numpy())))
    dtable('sa3_floater_gaussians', out); print('SA3 done', out, flush=True)

if __name__ == '__main__':
    {'sa2': sa2, 'sa3': sa3}[sys.argv[1]]()
