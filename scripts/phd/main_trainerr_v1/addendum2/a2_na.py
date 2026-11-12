"""Addendum 2 work 나 (order 3): Gaussians at the wrong-surface spots and at the GT spots, counted in space (no visibility). CPU container.
  sets <arm>     : nine point sets (wrong + controls) -> addendum2/points/na_<arm>.npz (+ json)
  tables         : per set: states (count, opacity), none share, opacity/size quantiles, born kind, bound |h| and band; same for the GT spot; spot -> GT spot distance
  figures        : south-wall horizontal + two vertical sections (B0 LoD2), annex vertical section (B0 ALS), both arms"""
from a2_common import *
SETS = ['south_behind', 'south_face', 'long_face', 'annex_under', 'annex_control', 'edge_wrong', 'edge_control', 'floor_wrong', 'floor_control']
SET_KO = {'south_behind': '남쪽 끝 벽 벽 뒤 점', 'south_face': '대조: 남쪽 끝 벽 벽면 점', 'long_face': '대조: 길 쪽 긴 벽 벽면 점', 'annex_under': '별채 지붕 아래 면', 'annex_control': '대조: B0 항공 LiDAR 경우 2 τ 안 결과 점',
          'edge_wrong': 'B0 가장자리 띠 틀린 면(칸 ① 잃은 점)', 'edge_control': '대조: 칸 ① 대조 점', 'floor_wrong': 'R1 바닥 띠 뜬 면(칸 ② 잃은 점)', 'floor_control': '대조: 칸 ② 대조 점'}
STEM_OF = {'south_behind': 'B0_b10__LoD2', 'south_face': 'B0_b10__LoD2', 'long_face': 'B0_b10__LoD2', 'annex_under': 'B0_b10__ALS', 'annex_control': 'B0_b10__ALS',
           'edge_wrong': 'B0_b10__LoD2', 'edge_control': 'B0_b10__LoD2', 'floor_wrong': 'R1rep_b10__ALS', 'floor_control': 'R1rep_b10__ALS'}

def result_data(stem, arm):
    rm = TRAINED_METHOD[arm]; Z = np.load(GT/'addendum12/distance_A1'/f'{stem}.npz') if arm == 'gt' else np.load(GT/'addendum11/final_data'/f'{stem}.npz')
    r = {k: Z[f'result__{rm}__{k}'] for k in ['point_id', 'xyz', 'normal', 'tau_m', 'case_id', 'eligible_new', 'within_tau1', 's_m']}; Z.close(); return r
def pick(idx, mx, rng):
    n_all = len(idx)
    if n_all > mx: idx = np.sort(rng.choice(idx, mx, replace=False))
    return idx, n_all

def sets(arm):
    c = bcfg(); t0 = Timer(f'a2_na_sets_{arm}'); mx = c['work_na']['max_points']; rng = np.random.default_rng(c['common']['seed']); P = {}; info = {}
    r = result_data('B0_b10__LoD2', arm); x = r['xyz'].astype('f8'); e = r['eligible_new'].astype(bool); w = r['within_tau1'].astype(bool)
    a, d, zs = wall_coords(x, 'south'); _, _, zl = wall_coords(x, 'long')
    for nm, m in [('south_behind', zs & e & ~w & (d < -.64)), ('south_face', zs & e & w), ('long_face', zl & e & w)]:
        idx, n_all = pick(np.flatnonzero(m), mx, rng); P[nm] = dict(spot=x[idx], point_id=r['point_id'][idx], case_id=r['case_id'][idx], kind='result', src_idx=idx); info[nm] = dict(all=n_all, used=len(idx))
    r2 = result_data('B0_b10__ALS', arm); x2 = r2['xyz'].astype('f8'); e2 = r2['eligible_new'].astype(bool); w2 = r2['within_tau1'].astype(bool); s2 = r2['s_m'].astype('f8'); bx = c['places']['annex_under']
    inbox = (x2[:, 0] >= bx['x'][0]) & (x2[:, 0] <= bx['x'][1]) & (x2[:, 1] >= bx['y'][0]) & (x2[:, 1] <= bx['y'][1]) & (r2['case_id'] == 2) & e2
    info['annex_under_box_case2_eligible'] = int(inbox.sum()); info['annex_under_nonfinite_s'] = int((inbox & ~np.isfinite(s2)).sum())
    for nm, m in [('annex_under', inbox & np.isfinite(s2) & (np.abs(s2) > 1.0)), ('annex_control', (r2['case_id'] == 2) & e2 & w2)]:
        idx, n_all = pick(np.flatnonzero(m), mx, rng); P[nm] = dict(spot=x2[idx], point_id=r2['point_id'][idx], case_id=r2['case_id'][idx], kind='result', src_idx=idx); info[nm] = dict(all=n_all, used=len(idx))
    for nm, cell, sv in [('edge_wrong', 'c1', 'lost'), ('edge_control', 'c1', 'control'), ('floor_wrong', 'c2', 'lost'), ('floor_control', 'c2', 'control')]:
        z = loadz(O/'sets'/f'{cell}_{arm}_{sv}.npz', ['point_id', 'xyz', 'normal', 'trained_s_m', 'patch_row']); idx, n_all = pick(np.arange(len(z['point_id'])), mx, rng)
        nn = z['normal'][idx]/np.linalg.norm(z['normal'][idx], axis=1)[:, None]; s = z['trained_s_m'][idx].astype('f8'); sp = z['xyz'][idx]+np.where(np.isfinite(s), s, np.nan)[:, None]*nn
        P[nm] = dict(spot=sp, point_id=z['point_id'][idx], gt_xyz=z['xyz'][idx], patch_row=z['patch_row'][idx], trained_s_m=s, kind='gt_point'); info[nm] = dict(all=n_all, used=len(idx), no_surface=int((~np.isfinite(s)).sum()))
    out, jinfo = {}, {}
    for stem in ['B0_b10__LoD2', 'B0_b10__ALS', 'R1rep_b10__ALS']:
        names = [n for n in SETS if STEM_OF[n] == stem]; S = Snap(stem, arm); vp = valid_rows(stem, arm)
        ref = loadz(GT/'addendum11/final_data'/f'{stem}.npz', ['reference__xyz']); rtree = cKDTree(ref['reference__xyz'])
        for nm in names:
            p = P[nm]; n = len(p['spot'])
            if p['kind'] == 'result':
                cp = result_patch(stem, arm, p['spot'], p['point_id'], nm); gd, gi = rtree.query(p['spot'], workers=8); gxyz = ref['reference__xyz'][gi]
            else:
                cp = p['patch_row'].astype('i8'); gxyz = p['gt_xyz']; gd = np.linalg.norm(p['spot']-gxyz, axis=1)
            cp = np.where(np.isin(cp, vp), cp, -1); fin = np.isfinite(p['spot']).all(1)
            sp_list = S.spots(np.where(fin[:, None], p['spot'], 1e9)); sv, _, _ = spot_values(S, sp_list, cp)
            gl = S.spots(gxyz); gv, _, _ = spot_values(S, gl, cp)
            # unique Gaussians of the set (spot / GT spot) for opacity, size, born and bound distributions
            ug = np.unique(np.concatenate([g for g, f in zip(sp_list, fin) if f])) if fin.any() and sum(len(g) for g in sp_list) else np.zeros(0, 'i8')
            ugg = np.unique(np.concatenate(gl)) if sum(len(g) for g in gl) else np.zeros(0, 'i8')
            rec = dict(spot=p['spot'].astype('f4'), spot_finite=fin.astype('u1'), gt_spot=np.asarray(gxyz, 'f4'), spot_to_gt_m=np.where(fin, gd, np.nan).astype('f4'), column_patch=cp, point_id=p['point_id'],
                       **{f'spot_{k}': v for k, v in sv.items()}, **{f'gt_{k}': v for k, v in gv.items()}, uniq_spot=ug, uniq_gt=ugg)
            if 'case_id' in p: rec['case_id'] = p['case_id']
            if 'trained_s_m' in p: rec['trained_s_m'] = p['trained_s_m'].astype('f4')
            out.update({f'{nm}__{k}': v for k, v in rec.items()}); jinfo[nm] = dict(info[nm], stem=stem, snapshot=str(S.path), seed_rows=S.n_seed_rows, gaussians=len(S.xyz))
            print('NA_SET', arm, nm, n, int(fin.sum()), flush=True)
        # per-Gaussian fields needed by the tables for the unique sets
        for nm in names:
            for key in ['uniq_spot', 'uniq_gt']:
                g = out[f'{nm}__{key}']; out[f'{nm}__{key}_opacity'] = S.opacity[g]; out[f'{nm}__{key}_size'] = S.size[g]; out[f'{nm}__{key}_born'] = S.born[g]; out[f'{nm}__{key}_tag'] = S.tag[g]
                out[f'{nm}__{key}_h'] = S.h[g].astype('f4'); out[f'{nm}__{key}_band'] = S.band[g].astype('f4')
        del S
    savez(A2O/'points'/f'na_{arm}.npz', **out); dump(A2O/'points'/f'na_{arm}.json', dict(at=now(), arm=arm, sets=jinfo, seconds=t0.done(), scientific_verdict=None))

def summary(z, nm, side):
    """side: 'spot' or 'gt'."""
    pre = f'{nm}__{side}_'; fin = z[f'{nm}__spot_finite'].astype(bool) if side == 'spot' else np.ones(len(z[f'{nm}__point_id']), bool)
    n_all = z[pre+'n_all'][fin]; tot = max(1, int(n_all.sum())); opt = max(1e-12, float(z[pre+'op_sum'][fin].sum()))
    r = dict(spots=int(fin.sum()), no_gaussian_pct=pct(n_all == 0), gaussians_per_spot_median=med(n_all))
    for k in STATES: r[f'{k}_count_pct'] = 100*float(z[pre+f'n_{k}'][fin].sum())/tot; r[f'{k}_opacity_pct'] = 100*float(z[pre+f'op_{k}'][fin].sum())/opt
    for k in STATES: r[f'spots_with_{k}_pct'] = pct(z[pre+f'n_{k}'][fin] > 0)
    r['spot_opacity_max_median'] = med(z[pre+'op_max'][fin]); r['spot_opacity_sum_median'] = med(z[pre+'op_sum'][fin])
    u = 'uniq_spot' if side == 'spot' else 'uniq_gt'; op = z[f'{nm}__{u}_opacity']; sz = z[f'{nm}__{u}_size']; bn = z[f'{nm}__{u}_born']; tg_ = z[f'{nm}__{u}_tag']; h = z[f'{nm}__{u}_h']; band = z[f'{nm}__{u}_band']
    r['unique_gaussians'] = len(op); r.update({f'opacity_{k}': v for k, v in qs(op).items()}); r.update({f'size_m_{k}': v for k, v in qs(sz).items()})
    for k, b in enumerate(BORN): r[f'{b}_pct'] = pct(bn == k) if len(bn) else None
    bb = tg_ == 1; r['bound_unique'] = int(bb.sum()); r.update({f'bound_abs_h_m_{k}': v for k, v in qs(np.abs(h[bb])).items()}); r.update({f'bound_band_m_{k}': v for k, v in qs(band[bb]).items()})
    r['bound_at_band_limit_pct'] = pct(np.abs(h[bb]) >= band[bb]-1e-4) if bb.any() else None
    return r

def tables():
    rows, dist = [], []
    for arm in ARMS:
        f = A2O/'points'/f'na_{arm}.npz'
        if not f.exists(): continue
        z = loadz(f); info = json.loads(f.with_suffix('.json').read_text())['sets']
        for nm in SETS:
            for side, lab in [('spot', '틀린 면 자리' if nm.endswith(('behind', 'under', 'wrong')) else '그 점의 자리'), ('gt', '참값 면 자리')]:
                rows.append(dict(arm=arm, set=nm, set_ko=SET_KO[nm], side=lab, points=int(info[nm]['used']), points_all=int(info[nm]['all']), no_surface=info[nm].get('no_surface'), **summary(z, nm, side)))
            fin = z[f'{nm}__spot_finite'].astype(bool); dist.append(dict(arm=arm, set=nm, **{f'spot_to_gt_m_{k}': v for k, v in qs(z[f'{nm}__spot_to_gt_m'][fin]).items()}))
    btable('na_states', rows); btable('na_spot_to_gt', dist); print('NA_TABLES', len(rows), flush=True)

def mesh_tris(path, lo, hi):
    m = o3d.io.read_triangle_mesh(str(path)); V = np.asarray(m.vertices); F = np.asarray(m.triangles); ins = ((V >= lo) & (V <= hi)).all(1); F = F[ins[F].any(1)]; return V, F
def cut(V, F, val):
    """segments where the triangles cross the level set val (per vertex)."""
    s = val[F]; sg = np.sign(s); m = (sg.min(1) < 0) & (sg.max(1) > 0); T = F[m]; S_ = s[m]; P = []
    for t, sv in zip(T, S_):
        q = []
        for a_, b_ in [(0, 1), (1, 2), (2, 0)]:
            if (sv[a_] < 0) != (sv[b_] < 0): u = sv[a_]/(sv[a_]-sv[b_]); q.append(V[t[a_]]+u*(V[t[b_]]-V[t[a_]]))
        if len(q) == 2: P.append(q)
    return np.array(P) if P else np.zeros((0, 2, 3))

def figures():
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; from matplotlib import font_manager as fm; from matplotlib.collections import LineCollection
    fm.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc'); plt.rcParams['font.family'] = fm.FontProperties(fname='/fonts/NotoSansCJK-Regular.ttc').get_name()
    c = bcfg(); FIG = A2D/'figures'; FIG.mkdir(parents=True, exist_ok=True); COL = ['#2CA02C', '#FF7F0E', '#9467BD', '#7F7F7F']
    LAB = {'south': ['묶임: 남쪽 끝 벽 패치', '묶임: 다른 패치', '풀림', '배경'], 'annex': ['묶임: 별채 상자 안 패치', '묶임: 다른 패치', '풀림', '배경']}
    sw = c['places']['south_wall'] if 'south_wall' in c.get('places', {}) else acfg()['places']['south_wall']; p0 = np.array(sw['p0']); e = np.array(sw['e']); nout = np.array(sw['n_out'])
    for arm in ARMS:
        for stem, which in [('B0_b10__LoD2', 'south'), ('B0_b10__ALS', 'annex')]:
            S = Snap(stem, arm); t = loadz(targets_of(stem, arm), ['target']); rows = loadz(GT/'addendum11/final_data'/f'{stem}.npz', ['reference__xyz'])['reference__xyz']
            if which == 'south': local = wall_zone_patches(stem, arm)['south']
            else: bx = c['places']['annex_under']; tt = t['target']; local = np.flatnonzero((tt[:, 0] >= bx['x'][0]) & (tt[:, 0] <= bx['x'][1]) & (tt[:, 1] >= bx['y'][0]) & (tt[:, 1] <= bx['y'][1]))
            code = np.where(S.tag == 1, np.where(np.isin(S.patch, local), 0, 1), np.where(S.tag == 2, 2, 3))
            lo = np.array([60., -30., -50.]); hi = np.array([130., 40., -15.]); meshes = {k: mesh_tris(p, lo, hi) for k, p in [('결과', trained_mesh(stem, arm)), ('목표', target_mesh(stem, arm))]}
            if which == 'south':
                def AD(X): return (X[:, :2]-p0)@e, (X[:, :2]-p0)@nout
                panels = [('수평', 'z -38 ~ -34.5 m', lambda X: (X[:, 2] >= -38) & (X[:, 2] <= -34.5), lambda X: AD(X), lambda X: X[:, 2]+36.25, ('벽 방향 a (m)', '벽에서 떨어진 거리 d (m, + 바깥)'), ((0, 20), (-5, 2)))]
                for a0 in [7.6, 13.5]:
                    panels.append((f'수직_a{a0}', f'벽 방향 {a0} m ± 0.25', (lambda a0: lambda X: np.abs(AD(X)[0]-a0) <= .25)(a0), lambda X: (AD(X)[1], X[:, 2]), (lambda a0: lambda X: AD(X)[0]-a0)(a0), ('벽에서 떨어진 거리 d (m, + 바깥)', '높이 z (m)'), ((-5, 2), (-44, -24))))
            else:
                panels = [('수직_y1.7', 'y 1.7 ± 0.25 m', lambda X: np.abs(X[:, 1]-1.7) <= .25, lambda X: (X[:, 0], X[:, 2]), lambda X: X[:, 1]-1.7, ('x (m)', '높이 z (m)'), ((84, 100), (-44, -31)))]
            for pname, ptitle, slab, proj, level, (xl, yl), (xr, yr) in panels:
                fig, ax = plt.subplots(figsize=(12, 6)); g = np.flatnonzero((S.opacity >= .1) & slab(S.xyz)); u, v = proj(S.xyz[g]); keep = (u >= xr[0]) & (u <= xr[1]) & (v >= yr[0]) & (v <= yr[1]); g = g[keep]; u, v = u[keep], v[keep]
                gr = slab(rows); ru, rv = proj(rows[gr]); ax.scatter(ru, rv, s=1.5, c='#BBBBBB', lw=0, rasterized=True, label='참값 점')
                for k in [3, 2, 1, 0]:
                    m = code[g] == k; ax.scatter(u[m], v[m], s=2+20*S.opacity[g][m], c=COL[k], lw=0, alpha=.75, rasterized=True, label=LAB[which][k])
                for (mk, (V, F)), col, lw in zip(meshes.items(), ['#D62728', '#1F77B4'], [1.4, 1.0]):
                    segs = cut(V, F, level(V))
                    if len(segs):
                        a1, b1 = proj(segs[:, 0]); a2, b2 = proj(segs[:, 1]); ax.add_collection(LineCollection(np.stack([np.c_[a1, b1], np.c_[a2, b2]], 1), colors=col, linewidths=lw, label=f'{mk} 메시'))
                ax.set_xlim(*xr); ax.set_ylim(*yr); ax.set_aspect('equal'); ax.set_xlabel(xl); ax.set_ylabel(yl); ax.legend(fontsize=7, markerscale=3, loc='upper right')
                ax.set_title(f'{stem} · {"본 방법 판정" if arm == "own" else "정답 판정"} · {ptitle} · 점 크기 = 불투명도', fontsize=9)
                p = FIG/f'na_section_{which}_{pname}_{arm}.png'; fig.savefig(p, dpi=170, bbox_inches='tight'); plt.close(fig)
                dump(p.with_suffix('.json'), dict(stem=stem, arm=arm, section=pname, rule=ptitle, gaussians_drawn=int(len(g)), counts={LAB[which][k]: int((code[g] == k).sum()) for k in range(4)}, opacity_min=0.1,
                                                  meshes={k: str(pp) for k, pp in [('결과', trained_mesh(stem, arm)), ('목표', target_mesh(stem, arm))]}, local_patches=int(len(local)), scientific_verdict=None))
            del S
    bprogress('일 나 단면 그림')

def radii():
    """Reference only (outside the order's 0.2 m rule; purpose: show whether the 0.2 m '없음' comes from large Gaussians centred farther away; no criterion):
    share of spots with >= 1 centre (opacity >= 0.1) within 0.2/0.5/1/2 m, and the Gaussians inside the annex_under box."""
    c = bcfg(); rows, box = [], []; bx = c['places']['annex_under']
    for arm in ARMS:
        z = loadz(A2O/'points'/f'na_{arm}.npz')
        for stem in ['B0_b10__LoD2', 'B0_b10__ALS', 'R1rep_b10__ALS']:
            S = Snap(stem, arm)
            for nm in [n for n in SETS if STEM_OF[n] == stem]:
                for side, key in [('spot', f'{nm}__spot'), ('gt', f'{nm}__gt_spot')]:
                    P = z[key].astype('f8'); P = P[np.isfinite(P).all(1)]; r = dict(arm=arm, set=nm, side='틀린 면 자리' if side == 'spot' and nm.endswith(('behind', 'under', 'wrong')) else ('그 점의 자리' if side == 'spot' else '참값 면 자리'), spots=len(P))
                    for rad in [0.2, 0.5, 1.0, 2.0]: r[f'within_{rad}m_pct'] = pct([len(q) > 0 for q in S.tree.query_ball_point(P, rad, workers=8)]) if len(P) else None
                    rows.append(r)
            if stem == 'B0_b10__ALS':
                x = S.xyz; m = (x[:, 0] >= bx['x'][0]) & (x[:, 0] <= bx['x'][1]) & (x[:, 1] >= bx['y'][0]) & (x[:, 1] <= bx['y'][1]) & (x[:, 2] >= -46) & (x[:, 2] <= -30)
                box.append(dict(arm=arm, box='annex_under x 86-98, y -1-7, z -46 to -30', gaussians=int(m.sum()), opacity_ge_0p1=int((m & (S.opacity >= .1)).sum()), **{f'size_m_{k}': v for k, v in qs(S.size[m]).items()},
                                bound=int((m & (S.tag == 1)).sum()), released=int((m & (S.tag == 2)).sum()), background=int((m & (S.tag == 0)).sum())))
            del S
    btable('na_reference_radii', rows); btable('na_reference_annex_box', box); print('NA_RADII', len(rows), flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]
    {'sets': lambda: sets(a[1]), 'tables': tables, 'figures': figures, 'radii': radii}[a[0]]()
