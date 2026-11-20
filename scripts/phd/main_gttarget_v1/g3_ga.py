"""Stage 3 (order 7.2, 7.3): point groups and tables ga / na / da of the GT target run (CPU, reads stored per-point scores only).
usage: g3_ga.py            -> every scene whose gtt_s0 base mesh is scored (scenes without one are listed as absent)

Arms (side by side in every table):
  method  = FINALTRAIN 30,000 (target = judgment_mesh, result = FINALTRAIN_30000; GTJUDGE addendum11 final_data)
  A-1     = patch-majority GT judgment run (target = gt_judgment_mesh, result = A1; GTJUDGE addendum12 distance_A1)
  GTT     = this run (target = O/meshes/<stem>__gtt_target, result = O/meshes/<stem>__gtt_<run>_<variant>)
Groups (per GT row, eligible rows): kept = target within tau and result within tau; lost = target within tau and result outside;
  method / A-1 also fixed (target outside, result within) and both wrong; GTT rows with the target outside tau are counted as 'target outside'.
Point data (order 7.2): the addendum 2 point set (ra_<stem>__own point_id) plus every GTT lost row outside it; all GTT lost points and
  20,000 GTT kept points per scene (numpy default_rng(points.rng_seed + scene index in cfg scenes), without replacement, sorted).
Patch edge (stage-1 decision 2026-11-19_precheck): a GT row is 'near a patch edge' when its covering patch square (nearest square centre with
  in-plane |u|,|v| <= 0.125 + 0.02 m, g1_cover rule) has fewer than 4 same-surface squares at centre distance 0.20-0.30 m.
Outputs: O/points/ga_<stem>.npz (+ .json), tables ga_size, ga_scene, ga_edge, na_cross, na_seed, da_cells, da_places (csv + json, title TITLE)."""
import sys, time
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
from scipy.spatial import cKDTree

A12D = GT/'addendum12/distance_A1'
VARIANTS = ['base', 'occl', 'median_depth', 'occl_median']
ARM_KO = {'method': '본 방법 판(FINALTRAIN)', 'A1': '패치 다수결 판(A-1)', 'gtt': '참값 목표 판'}
G4 = {0: '지킴', 1: '잃음', 2: '고침', 3: '둘 다 틀림'}
GG = {0: '지킴', 1: '잃음', 2: '목표 밖(지킴)', 3: '목표 밖(틀림)'}
TE_CELLS = json.loads((R/'configs/phd/main_trainerr_v1/trainerr_v1.json').read_text())['cells']
PLACES = [('visible_low', 'B0 잘 보이는 벽 0–5 m', TE/'addendum4/places/visible_low.npz'), ('visible_high', 'B0 잘 보이는 벽 5–10 m', TE/'addendum4/places/visible_high.npz'),
          ('south_wall', 'B0 남쪽 끝 벽', TE/'addendum4/places/south_wall.npz'), ('r1_lod2_wall1', 'R1 × LoD2 1번 벽', TE/'addendum5/places/r1_lod2_wall1.npz'),
          ('floor_band', 'R1 바닥 띠', TE/'addendum4/places/floor_band.npz'), ('edge_annex', '별채 가장자리', TE/'addendum4/places/edge_annex.npz')]
FLOATER = TE/'addendum3/ma/points.npz'   # edge_face_centres: B173 x ALS edge floater faces (addendum 3 ma)

def pct(m): m = np.asarray(m, bool); return round(100*float(m.mean()), 3) if len(m) else None
def small(n): return 'n<30' if n < 30 else ''
def mesh_pts(key, keys=('reference__within_tau1',)):
    p = O/'meshes'/key/'points.npz'
    return loadz(p, list(keys)) if p.exists() else None
def res_keys(prefix=''): return [f'{prefix}eligible_new', f'{prefix}within_tau1', f'{prefix}case_id', f'{prefix}xyz']

def scene_cols(ref_w, el, res):
    """completeness = eligible GT rows within tau; accuracy = eligible_new result points within tau (all cases)."""
    e = res['eligible_new'].astype(bool)
    return dict(completeness_pct=pct(ref_w[el]), accuracy_pct=pct(res['within_tau1'].astype(bool)[e]), result_points_eligible=int(e.sum()))

def edge_flag(site, X):
    p = loadz(O/'surface'/site/'patches.npz', ['centre', 'normal', 'surf']); C = p['centre'].astype('f8'); Nn = p['normal'].astype('f8'); tree = cKDTree(C); h = .125+.02
    d, j = tree.query(X, k=8, distance_upper_bound=1.0, workers=16); best = np.full(len(X), np.inf); cov = np.full(len(X), -1)
    for q in range(8):
        jj = j[:, q]; v = jj < len(C); jj = np.where(v, jj, 0); r = X-C[jj]; w = np.abs((r*Nn[jj]).sum(1)); ip = np.linalg.norm(r-(r*Nn[jj]).sum(1)[:, None]*Nn[jj], axis=1)
        ok = v & (ip <= np.sqrt(2)*h) & (w < best); best = np.where(ok, w, best); cov = np.where(ok, jj, cov)
    nb = np.zeros(len(C), 'i2'); pairs = tree.query_pairs(.30, output_type='ndarray'); dd = np.linalg.norm(C[pairs[:, 0]]-C[pairs[:, 1]], axis=1)
    pairs = pairs[(dd >= .20) & (p['surf'][pairs[:, 0]] == p['surf'][pairs[:, 1]])]; np.add.at(nb, pairs[:, 0], 1); np.add.at(nb, pairs[:, 1], 1)
    return np.where(cov >= 0, nb[np.clip(cov, 0, None)] < 4, False), cov >= 0

def main():
    c = cfg(3); t0 = time.monotonic(); scenes = c['scenes']; pc = c['points']
    size, scene, edge, cross, seedx, cells, places, absent = [], [], [], [], [], [], [], []
    for stem in STEMS:
        site, prior = stem.split('__')
        tgt = mesh_pts(f'{stem}__gtt_target', ['reference__within_tau1']+res_keys('result__'))
        base = mesh_pts(f'{stem}__gtt_s0_base', ['reference__within_tau1']+res_keys('result__'))
        if tgt is None or base is None: absent.append(stem); print('GA_ABSENT', stem, flush=True); continue
        A = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); el = A['reference__eligible'].astype(bool); N = len(el)
        arms = {'method': (A['reference__judgment_mesh__within_tau1'].astype(bool), A['reference__FINALTRAIN_30000__within_tau1'].astype(bool),
                           {k: A[f'result__judgment_mesh__{k}'] for k in ['eligible_new', 'within_tau1', 'case_id']}, {k: A[f'result__FINALTRAIN_30000__{k}'] for k in ['eligible_new', 'within_tau1', 'case_id']})}
        if (A12D/f'{stem}.npz').exists():
            B = np.load(A12D/f'{stem}.npz'); assert np.array_equal(B['reference__point_id'], A['reference__point_id'])
            arms['A1'] = (A['reference__gt_judgment_mesh__within_tau1'].astype(bool), B['reference__A1__within_tau1'].astype(bool),
                          {k: A[f'result__gt_judgment_mesh__{k}'] for k in ['eligible_new', 'within_tau1', 'case_id']}, {k: B[f'result__A1__{k}'] for k in ['eligible_new', 'within_tau1', 'case_id']})
        strip = lambda z: {k.split('__', 1)[1]: v for k, v in z.items() if k.startswith('result__')}
        arms['gtt'] = (tgt['reference__within_tau1'].astype(bool), base['reference__within_tau1'].astype(bool), strip(tgt), strip(base))
        G = {}
        for arm, (tw, rw, tres, rres) in arms.items():
            g = np.where(tw, np.where(rw, 0, 1), np.where(rw, 2, 3)).astype('i1'); G[arm] = g; ok = el & tw; lost = ok & ~rw
            size.append(dict(title=TITLE, stem=stem, arm=ARM_KO[arm], gt_rows=int(el.sum()), target_within_n=int(ok.sum()), target_within_pct=pct(tw[el]),
                             lost_n=int(lost.sum()), lost_pct_of_target_within=round(100*lost.sum()/max(1, ok.sum()), 3), kept_n=int((ok & rw).sum()),
                             fixed_n=int((el & ~tw & rw).sum()), both_wrong_n=int((el & ~tw & ~rw).sum()), small=small(int(lost.sum()))))
            scene.append(dict(title=TITLE, stem=stem, arm=ARM_KO[arm], surface='목표 메시', variant='', **scene_cols(tw, el, tres)))
            scene.append(dict(title=TITLE, stem=stem, arm=ARM_KO[arm], surface='결과 메시', variant='base', **scene_cols(rw, el, rres)))
        W = {'base': arms['gtt'][1]}
        for v in VARIANTS[1:]:
            z = mesh_pts(f'{stem}__gtt_s0_{v}', ['reference__within_tau1']+res_keys('result__'))
            if z is None: scene.append(dict(title=TITLE, stem=stem, arm=ARM_KO['gtt'], surface='결과 메시', variant=v, completeness_pct=None, accuracy_pct=None, note='추출 없음')); continue
            W[v] = z['reference__within_tau1'].astype(bool); scene.append(dict(title=TITLE, stem=stem, arm=ARM_KO['gtt'], surface='결과 메시', variant=v, **scene_cols(W[v], el, strip(z))))
        # ---- patch edge (lost share near patch edges vs elsewhere) ----
        X = A['reference__xyz'].astype('f8'); near, covered = edge_flag(site, X); tw, rw = arms['gtt'][0], arms['gtt'][1]
        for nm, m in [('조각 가장자리 근처', near), ('조각 안쪽', covered & ~near), ('덮는 조각 없음', ~covered)]:
            mm = el & m; ok = mm & tw; lo = ok & ~rw
            edge.append(dict(title=TITLE, stem=stem, where=nm, gt_rows=int(mm.sum()), target_within_pct=pct(tw[mm]), lost_n=int(lo.sum()), lost_pct_of_target_within=round(100*lo.sum()/max(1, ok.sum()), 3), small=small(int(mm.sum()))))
        # ---- table na: cross with method / A-1 (all eligible rows) ----
        for arm in [a for a in ('method', 'A1') if a in G]:
            for k in range(4):
                m = el & (G[arm] == k)
                cross.append(dict(title=TITLE, stem=stem, other=ARM_KO[arm], other_group=G4[k], n=int(m.sum()),
                                  **{f'gtt_{GG[q]}': int((m & (G['gtt'] == q)).sum()) for q in range(4)},
                                  gtt_lost_pct_of_row=round(100*(m & (G['gtt'] == 1)).sum()/max(1, m.sum()), 3), small=small(int(m.sum()))))
        s1 = mesh_pts(f'{stem}__gtt_s1_base')
        if s1 is not None:
            g1 = np.where(tw, np.where(s1['reference__within_tau1'].astype(bool), 0, 1), np.where(s1['reference__within_tau1'].astype(bool), 2, 3))
            for k in range(4):
                m = el & (G['gtt'] == k)
                seedx.append(dict(title=TITLE, stem=stem, seed0_group=GG[k], n=int(m.sum()), **{f'seed1_{GG[q]}': int((m & (g1 == q)).sum()) for q in range(4)}, small=small(int(m.sum()))))
            for arm in ('method',):
                for k in range(4):
                    m = el & (G[arm] == k)
                    seedx.append(dict(title=TITLE, stem=stem, seed0_group=f'{ARM_KO[arm]} {G4[k]}', n=int(m.sum()), **{f'seed1_{GG[q]}': int((m & (g1 == q)).sum()) for q in range(4)}, small=small(int(m.sum()))))
        # ---- point data (order 7.2) ----
        A2 = loadz(TE/'addendum2/points'/f'ra_{stem}__own.npz', ['point_id', 'group']); A2g = loadz(TE/'addendum2/points'/f'ra_{stem}__gt.npz', ['point_id', 'group']) if (TE/'addendum2/points'/f'ra_{stem}__gt.npz').exists() else None
        pid = A['reference__point_id']; o = np.argsort(pid); row = lambda q: o[np.searchsorted(pid[o], q)]
        U = row(A2['point_id']); lost_all = np.flatnonzero(el & (G['gtt'] == 1)); U = np.union1d(U, lost_all)
        rng = np.random.default_rng(pc['rng_seed']+scenes.index(stem)); keep_all = U[el[U] & (G['gtt'][U] == 0)]
        keep = np.sort(rng.choice(keep_all, min(pc['others_per_scene'], len(keep_all)), replace=False)); sel = np.sort(np.r_[U[G['gtt'][U] == 1], keep])
        a2grp = np.full(N, -1, 'i1'); a2grp[row(A2['point_id'])] = A2['group']
        a2gt = np.full(N, -1, 'i1')
        if A2g is not None: a2gt[row(A2g['point_id'])] = A2g['group']
        out = dict(a11_row=sel, point_id=pid[sel], xyz=A['reference__xyz'][sel].astype('f4'), normal=A['reference__normal'][sel].astype('f4'), tau=A['reference__tau_m'][sel].astype('f4'),
                   case_id=A['reference__case_id'][sel], wall=A['reference__wall'][sel], group_gtt=G['gtt'][sel], group_method=G['method'][sel], group_method_a2=a2grp[sel],
                   group_a1=G['A1'][sel] if 'A1' in G else np.full(len(sel), -1, 'i1'), group_a1_a2=a2gt[sel], in_a2_set=np.isin(sel, row(A2['point_id'])),
                   near_patch_edge=near[sel], **{f'within_{v}': w[sel] for v, w in W.items()})
        if s1 is not None: out['group_gtt_s1'] = g1[sel].astype('i1')
        savez(O/'points'/f'ga_{stem}.npz', **out)
        dump(O/'points'/f'ga_{stem}.json', dict(at=now(), stem=stem, title=TITLE, a2_points=len(A2['point_id']), lost_outside_a2=int((~np.isin(lost_all, row(A2['point_id']))).sum()),
                                               lost=int((G['gtt'][sel] == 1).sum()), kept_selected=len(keep), kept_all=len(keep_all), variants=list(W), seed1=s1 is not None,
                                               a2_group_equals_a11_group_pct=pct(a2grp[U][a2grp[U] >= 0] == G['method'][U][a2grp[U] >= 0]), scientific_verdict=None))
        # ---- table da: TRAINERR cells 1-3 (same rule as s0_sets: completeness over case rows, accuracy over eligible_new result points of the case) ----
        for cell, cs in TE_CELLS.items():
            if f"{cs['site']}__{cs['prior']}" != stem: continue
            case = cs['case_id']; m = A['reference__case_id'] == case
            for arm, (tw_, rw_, tres, rres) in arms.items():
                vals = {}
                for stage, wv, res in [('target', tw_, tres), ('trained', rw_, rres)]:
                    if cs['metric'] == 'completeness': vals[stage] = (pct(wv[m]), int(m.sum()))
                    else: e = res['eligible_new'].astype(bool) & (res['case_id'] == case); vals[stage] = (pct(res['within_tau1'].astype(bool)[e]), int(e.sum()))
                cells.append(dict(title=TITLE, cell=cell, place=f"{cs['site']} × {cs['prior']} {cs['case_name']} {'완전성' if cs['metric'] == 'completeness' else '정확성'}", arm=ARM_KO[arm], variant='base',
                                  target_pct=vals['target'][0], trained_pct=vals['trained'][0], target_n=vals['target'][1], trained_n=vals['trained'][1],
                                  te_expected=None if arm == 'gtt' else str(cs['expected']['own' if arm == 'method' else 'gt']), small=small(vals['trained'][1])))
            for v in VARIANTS[1:]:
                z = mesh_pts(f'{stem}__gtt_s0_{v}', ['reference__within_tau1']+res_keys('result__'))
                if z is None: continue
                if cs['metric'] == 'completeness': val, n = pct(z['reference__within_tau1'].astype(bool)[m]), int(m.sum())
                else: e = z['result__eligible_new'].astype(bool) & (z['result__case_id'] == case); val, n = pct(z['result__within_tau1'].astype(bool)[e]), int(e.sum())
                cells.append(dict(title=TITLE, cell=cell, place=cells[-1]['place'], arm=ARM_KO['gtt'], variant=v, target_pct=None, trained_pct=val, target_n=None, trained_n=n, te_expected=None, small=small(n)))
        # ---- table da: fixed places (GT rows of the stored place points) ----
        for key, ko, path in PLACES:
            P = loadz(path, ['stem', 'point_id']);
            if str(P['stem']) != stem: continue
            j = row(P['point_id'])
            for arm, (tw_, rw_, _, _) in arms.items():
                places.append(dict(title=TITLE, place=ko, stem=stem, arm=ARM_KO[arm], variant='base', gt_points=len(j), target_pct=pct(tw_[j]), trained_pct=pct(rw_[j]), small=small(len(j))))
            for v in VARIANTS[1:]:
                if v in W: places.append(dict(title=TITLE, place=ko, stem=stem, arm=ARM_KO['gtt'], variant=v, gt_points=len(j), target_pct=None, trained_pct=pct(W[v][j]), small=small(len(j))))
        if stem == 'B173nb_b10__ALS':
            F = loadz(FLOATER, ['edge_face_centres'])['edge_face_centres'].astype('f8'); tree = cKDTree(F)
            for arm, (_, _, _, rres) in [(a, arms[a]) for a in arms]:
                if 'xyz' in rres: Xr = rres['xyz']
                elif arm == 'method': Xr = A['result__FINALTRAIN_30000__xyz']
                else: Xr = B['result__A1__xyz']
                d, _ = tree.query(np.asarray(Xr, 'f8'), distance_upper_bound=.5, workers=16); m = np.isfinite(d)
                places.append(dict(title=TITLE, place='가장자리 뜬 면(결과 점 0.5 m 안)', stem=stem, arm=ARM_KO[arm], variant='base', result_points_near=int(m.sum()),
                                   trained_pct=pct(np.asarray(rres['within_tau1'], bool)[m & np.asarray(rres['eligible_new'], bool)]), small=small(int(m.sum()))))
        A.close(); print('GA', stem, round(time.monotonic()-t0), flush=True)
    # ---- totals ----
    for arm in ARM_KO.values():
        r = [x for x in size if x['arm'] == arm]
        if r:
            T = {k: sum(x[k] for x in r) for k in ['gt_rows', 'target_within_n', 'lost_n', 'kept_n', 'fixed_n', 'both_wrong_n']}
            size.append(dict(title=TITLE, stem=f"합({len(r)} 장면: {', '.join(x['stem'] for x in r)})", arm=arm, **T, target_within_pct=round(100*T['target_within_n']/T['gt_rows'], 3),
                             lost_pct_of_target_within=round(100*T['lost_n']/T['target_within_n'], 3), small=''))
    for s in absent: size.append(dict(title=TITLE, stem=s, arm=ARM_KO['gtt'], note='결과 없음: 30,000회 모델 없음(15,000회 건강 점검 멈춤 3회) 또는 추출 미완'))
    for n, rows in [('ga_size', size), ('ga_scene', scene), ('ga_edge', edge), ('na_cross', cross), ('na_seed', seedx), ('da_cells', cells), ('da_places', places)]:
        if rows: table(n, rows)
    progress(f'g3_ga: tables ga_size/ga_scene/ga_edge/na_cross/na_seed/da_cells/da_places, absent {absent}, {round(time.monotonic()-t0)} s')

if __name__ == '__main__': main()
