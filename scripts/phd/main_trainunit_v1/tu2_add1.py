"""PHD-MAIN-TRAINUNIT-v2 addendum 1: why the R1 accuracy of the group units (전체, 넷, 아홉) is below the building unit.
No training, no GPU: existing targets, seeds, splits, cameras.json, saved models, meshes and scores only (run2_cpu.sh).
Sites: R1rep_b10 (difference) and B173nb_b10 (no difference). Everything inside the GTJUDGE evaluation box of the site.

  python tu2_add1.py inputs <site>        # items 1-5 -> tables add1_<1..5>_<site>, figure add1_targets_only_<site>
  python tu2_add1.py gauss  <site>        # item 6   -> tables add1_6_<site>
  python tu2_add1.py mesh   <site> <plan> # items 7-8 per plan -> parts (one mesh per container)
  python tu2_add1.py join   <site>        # items 7-8 -> tables add1_7_<site>, add1_8_<site>, figure add1_case0_out_<site>
Reference (GT) is used for scoring masks and figures only.
"""
import gc
import sys

sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
import common as gcommon
from tu_common import *

gcommon.O = TU / 'gt'
gcommon.C = Path('/repo/configs/phd/main_gtjudge_v1')
gcommon.D = TU / 'gt/docs'
import add2_scores  # noqa: E402
from geometry_add1 import read_surface  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402
from tu2_stop import write as _write, plt_ko  # noqa: E402


def _clean(v):
    if isinstance(v, float) and not np.isfinite(v):
        return None
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    return v


def write(name, rows, note):
    _write(name, [_clean(r) for r in rows], note)

TU1 = Path('/tu1')
G = PH / 'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
SHORT = dict(R1rep_b10='R1rep', B173nb_b10='B173nb', B0_b10='B0')
REGION = {1: '일치', 2: '보존', 3: '보정', 0: '결측', 5: '보정(빈 공간)', -1: '목표 없음'}
PARTS = D / 'figures/_parts_add1'
WIDTH = 30000


def box(site):
    b = np.array(json.loads((G / 'views' / f'{site}.json').read_text())['box'], float)
    return b[0], b[1]


def inside(xyz, lo, hi):
    return ((xyz >= lo) & (xyz <= hi)).all(1)


def final_att(run):
    r = json.loads((run / 'receipt.json').read_text())
    return run / f'attempt{r["attempts"][-1]["attempt"]}'


def cells_json(plan):
    return json.loads(((TU1 if plan == '넷' else TU) / 'cells/cells.json').read_text())


def owner_cells(site, plan):
    return next(x for x in cells_json(plan)['evaluation_boxes'] if x['site'] == site)['cells']


def units(site, plan):
    """(unit label, targets npz, seeds npz, split json, run dir) of the units of a plan that own part of the box."""
    s = SHORT[site]
    if plan.startswith('건물단위'):
        seed = plan[-1]
        return [(f'{s}ef_ALS_s{seed}', FT / 'targets' / f'{site}__ALS.npz', FT / 'stage1' / f'{site}__ALS/seeds.npz',
                 S0 / 'fork_inputs/s61' / site / 'split.json', TU1 / 'runs/ef' / f'{s}ef_ALS_s{seed}')]
    if plan == '전체':
        return [('campus', TU1 / 'targets/campus__ALS.npz', TU1 / 'stage1/campus__ALS/seeds.npz', TU1 / 'scenes/campus/split.json', TU1 / 'runs/ef/campusef30k_ALS_s0')]
    base, run = (TU1, lambda k: TU1 / 'runs/ef' / f'cellsef_ALS_s0_cell{k}') if plan == '넷' else (TU, lambda k: TU / 'runs' / f'cells9ef_ALS_s0_cell{k}')
    return [(f'{plan} 칸 {k}', base / 'targets' / f'cell{k}__ALS.npz', base / 'stage1' / f'cell{k}__ALS/seeds.npz', base / 'scenes' / f'cell{k}/split.json', run(k))
            for k in owner_cells(site, plan)]


PLANS = ['건물단위_s0', '건물단위_s1', '전체', '넷', '아홉']
FAM = {'건물단위_s0': 'ef_s0', '건물단위_s1': 'ef_s1', '전체': 'campusef30k_ALS_s0', '넷': 'cellsef_ALS_s0', '아홉': 'cells9ef_ALS_s0'}


# ---------------------------------------------------------------- items 1-5

def inputs(site):
    cfg()
    lo, hi = box(site)
    bu = units(site, '건물단위_s0')[0]
    T0 = loadz(bu[1])
    m0 = inside(T0['centre'], lo, hi)
    tree0 = cKDTree(T0['centre'][m0])
    i0 = np.flatnonzero(m0)
    ref0 = float(T0['sigma_ref'])
    t1, t2, t3, t45 = [], [], [], []
    only_fig = {}
    btrain = json.loads(bu[3].read_text())['train']
    from tu_campus import cameras
    from tu_cells import coverage
    for plan in PLANS:
        for label, tp, sp, splitp, run in units(site, plan):
            # 1 targets
            T = loadz(tp)
            m = inside(T['centre'], lo, hi)
            ref = float(T['sigma_ref'])
            row = dict(site=site, plan=plan, unit=label, targets_file=str(tp), sigma_ref=ref, patches_in_box=int(m.sum()), active_in_box=int((m & T['surface_exists']).sum()),
                       area_in_box_m2=float(T['area'][m].sum()))
            for code, name in REGION.items():
                row[f'갈래_{name}'] = int((m & (T['region'] == code)).sum())
            other = sorted(set(np.unique(T['region'][m]).tolist()) - set(REGION))
            for code in other:
                row[f'갈래_코드{code}'] = int((m & (T['region'] == code)).sum())
            if 'source' in T:
                row['site_rows_in_box'] = int((m & (T['source'] < 3)).sum()); row['judgecheck_rows_in_box'] = int((m & (T['source'] == 3)).sum())
            # pair with the building-unit targets by position
            im = np.flatnonzero(m)
            d, j = tree0.query(T['centre'][im], workers=4) if len(im) else (np.array([]), np.array([], int))
            pair = d < 1e-4
            pj = i0[j[pair]]; pi = im[pair]
            only_here = im[~pair]
            matched0 = np.zeros(len(i0), bool); matched0[j[pair]] = True
            only_bu = i0[~matched0]
            w = lambda S, r, idx: np.clip(r / S['sigma'][idx], .1, 10)
            act_pair = T['surface_exists'][pi] & T0['surface_exists'][pj]
            row.update(paired=int(pair.sum()), only_this_plan=int(len(only_here)), only_this_plan_area_m2=float(T['area'][only_here].sum()),
                       only_this_plan_active=int(T['surface_exists'][only_here].sum()), only_building_unit=int(len(only_bu)),
                       only_building_unit_area_m2=float(T0['area'][only_bu].sum()),
                       paired_target_max_abs_diff_m=float(np.abs(T['target'][pi] - T0['target'][pj]).max()) if len(pi) else None,
                       paired_sigma_max_rel_diff=float(np.nanmax(np.abs(T['sigma'][pi] / T0['sigma'][pj] - 1))) if len(pi) else None,
                       paired_region_same_pct=100. * float((T['region'][pi] == T0['region'][pj]).mean()) if len(pi) else None,
                       paired_active_same_pct=100. * float((T['surface_exists'][pi] == T0['surface_exists'][pj]).mean()) if len(pi) else None,
                       paired_weight_ratio_median=float(np.median(w(T, ref, pi[act_pair]) / w(T0, ref0, pj[act_pair]))) if act_pair.any() else None,
                       paired_weight_this_q10_q50_q90=np.quantile(w(T, ref, pi[act_pair]), [.1, .5, .9]).tolist() if act_pair.any() else None,
                       paired_weight_building_q10_q50_q90=np.quantile(w(T0, ref0, pj[act_pair]), [.1, .5, .9]).tolist() if act_pair.any() else None,
                       only_this_plan_buildings=sorted(set(T['building'][only_here].tolist()))[:12] if 'building' in T and len(only_here) else [],
                       only_this_plan_buildings_n=len(set(T['building'][only_here].tolist())) if 'building' in T else None)
            t1.append(row)
            if plan in ('전체',):
                only_fig[plan] = dict(this=T['centre'][only_here][:, :2], this_active=T['surface_exists'][only_here], bu=T0['centre'][only_bu][:, :2])
            # 2 seeds
            S = loadz(sp, ['xyz', 'origin'])
            ms = inside(S['xyz'].astype(float), lo, hi)
            t2.append(dict(site=site, plan=plan, unit=label, seeds_file=str(sp), prior_seeds_in_box=int((ms & (S['origin'] == 1)).sum()),
                           background_sfm_seeds_in_box=int((ms & (S['origin'] == 0)).sum()), prior_seeds_total=int((S['origin'] == 1).sum()),
                           background_sfm_seeds_total=int((S['origin'] == 0).sum())))
            # 3 images
            tr = json.loads(splitp.read_text())['train']
            cams = {}
            for n in tr:
                try:
                    cams[n] = cameras([n])[0]
                except KeyError:
                    pass
            cov = np.array([coverage(cams[n], lo, hi) for n in tr if n in cams])
            t3.append(dict(site=site, plan=plan, unit=label, train_images=len(tr), building_unit_images_in=len(set(btrain) & set(tr)),
                           building_unit_images_missing=len(set(btrain) - set(tr)), images_not_in_building_unit=len(set(tr) - set(btrain)),
                           images_without_campus_pose=len(tr) - len(cams), box_seen_any=int((cov > 0).sum()), box_seen_ge25pct=int((cov >= .25).sum()),
                           box_coverage_median_of_seen=float(np.median(cov[cov > 0])) if (cov > 0).any() else None,
                           building_unit_images_missing_box_seen_any=int(sum(1 for n in set(btrain) - set(tr) if n in cams_all(n) and coverage(cams_all(n)[n], lo, hi) > 0))))
            # 4, 5 training amount and scene size
            att = final_att(run)
            cj = json.loads((att / 'model/cameras.json').read_text())
            C = np.array([c['position'] for c in cj], float)
            r = 1.1 * float(np.linalg.norm(C - C.mean(0), axis=1).max())
            ov = json.loads((att / 'extent_override.json').read_text()) if (att / 'extent_override.json').exists() else None
            used = (ov or {}).get('used_radius')
            t45.append(dict(site=site, plan=plan, unit=label, train_images=len(tr), cameras_json_all=len(cj), iterations=WIDTH, iterations_per_image=WIDTH / len(tr),
                            radius_from_cameras_json_all_m=r, fork_radius_train_m=(ov or {}).get('fork_radius'), radius_fixed=(ov or {}).get('fixed'), radius_used_m=used, clone_split_threshold_m=0.01 * used if used else None, big_gaussian_prune_m=0.1 * used if used else None,
                            run=str(att)))
            del T, S; gc.collect()
    write(f'add1_1_targets_{site}', t1, 'addendum 1 item 1: targets inside the evaluation box per plan/unit; region codes (tu_campus labels; other codes by number); pairing with the building-unit targets (FINALTRAIN targets) by centre (< 0.1 mm); paired differences of target xyz, sigma, region, active flag and the map weight clip(sigma_ref/sigma, 0.1, 10)')
    write(f'add1_2_seeds_{site}', t2, 'addendum 1 item 2: initial points inside the box: prior seeds (origin 1) and SfM background (origin 0) of seeds.npz')
    write(f'add1_3_images_{site}', t3, 'addendum 1 item 3: training images per unit; building-unit 333 (R1) images in / missing; images whose camera sees the box (coverage of the projected 3D box: > 0 and >= 25 %, tu_cells.coverage on the campus poses)')
    write(f'add1_45_amount_size_{site}', t45, 'addendum 1 items 4-5: iterations per training image = 30,000 / training images; radius used = extent_override.json used_radius written by the run (fork getNerfppNorm over the training cameras, addendum 12 record); radius_from_cameras_json_all = same rule over cameras.json (train + test) for reference; clone/split threshold 0.01 r, big-Gaussian prune 0.1 r')
    if only_fig:
        plt = plt_ko()
        f = only_fig['전체']
        fig, ax = plt.subplots(figsize=(9, 8))
        ax.scatter(f['this'][f['this_active'], 0], f['this'][f['this_active'], 1], s=1, c='tab:blue', label=f'무리 단위 목표에만 있음, 목표 있음 ({int(f["this_active"].sum())})')
        ax.scatter(f['this'][~f['this_active'], 0], f['this'][~f['this_active'], 1], s=1, c='tab:cyan', label=f'무리 단위 목표에만 있음, 목표 없음 ({int((~f["this_active"]).sum())})')
        ax.scatter(f['bu'][:, 0], f['bu'][:, 1], s=1, c='tab:red', label=f'건물 단위 목표에만 있음 ({len(f["bu"])})')
        ax.set(xlim=(lo[0], hi[0]), ylim=(lo[1], hi[1]), aspect='equal', xlabel='x (m)', ylabel='y (m)')
        ax.legend(fontsize=8, markerscale=6)
        ax.set_title(f'{site}: 평가 상자 안 목표 패치 중 한쪽에만 있는 것 (전체 = campus 목표; 넷·아홉 칸 목표는 그 부분집합)')
        out = D / 'figures' / f'add1_targets_only_{site}'
        fig.savefig(out.with_suffix('.png'), dpi=150); plt.close(fig)
        dump(out.with_suffix('.json'), dict(site=site, box=[lo.tolist(), hi.tolist()], only_campus=int(len(f['this'])), only_campus_active=int(f['this_active'].sum()),
             only_building_unit=int(len(f['bu'])), scientific_verdict=None))
    print('INPUTS', site, flush=True)


_CAMS = {}


def cams_all(n):
    from tu_campus import cameras
    if n not in _CAMS:
        try:
            _CAMS[n] = cameras([n])[0]
        except KeyError:
            _CAMS[n] = None
    return {n: _CAMS[n]} if _CAMS[n] is not None else {}


# ---------------------------------------------------------------- item 6

def plan_ply(site, plan):
    if plan == '넷':
        return TU1 / 'runs/ef/cellsef_ALS_s0/merged/point_cloud.ply'
    if plan == '아홉':
        return TU / 'runs/cells9ef_ALS_s0/merged/point_cloud.ply'
    run = units(site, plan)[0][4]
    return final_att(run) / 'model/point_cloud/iteration_30000/point_cloud.ply'


def gauss(site):
    cfg()
    from plyfile import PlyData
    lo, hi = box(site)
    rows = []
    for plan in PLANS:
        p = plan_ply(site, plan)
        v = PlyData.read(str(p))['vertex'].data
        xyz = np.c_[v['x'], v['y'], v['z']].astype(float)
        m = inside(xyz, lo, hi)
        op = 1 / (1 + np.exp(-v['opacity'][m].astype(float)))
        sc = np.exp(np.c_[[v[n][m] for n in sorted(x for x in v.dtype.names if x.startswith('scale_'))]].T.astype(float))
        q = lambda a: np.quantile(a, [.1, .5, .9]).tolist() if len(a) else None
        row = dict(site=site, plan=plan, ply=str(p), gaussians_in_box=int(m.sum()), opacity_q10_q50_q90=q(op), scale_max_q10_q50_q90_m=q(sc.max(1)),
                   scale_min_q10_q50_q90_m=q(sc.min(1)), elong_lt_001_pct=100. * float((sc.min(1) / sc.max(1) < .01).mean()) if len(sc) else None)
        if plan in ('넷', '아홉'):
            cj = cells_json(plan)
            for c in cj['cells']:
                o = np.array(c['original_min'], float); h = np.array(c['original_max'], float)
                k = m & (xyz[:, 0] >= o[0]) & (xyz[:, 0] < h[0]) & (xyz[:, 1] >= o[1]) & (xyz[:, 1] < h[1])
                if k.any():
                    row[f'gaussians_in_box_cell{c["id"]}'] = int(k.sum())
        rows.append(row)
        del v, xyz; gc.collect()
    write(f'add1_6_gaussians_{site}', rows, 'addendum 1 item 6: Gaussians of the saved 30,000 model inside the box (넷/아홉: merged model, also per owner cell): opacity sigmoid, scales exp (2DGS two axes), 10/50/90 % values')
    print('GAUSS', site, flush=True)


# ---------------------------------------------------------------- items 7-8

def mesh_path(m):
    for base in [TU / 'gt', TU1 / 'gt']:
        p = Path(str(base) + m[len('/gtjudge'):])
        if p.exists():
            return p
    raise FileNotFoundError(m)


def classes(site, fam):
    root = TU / 'gt/scenes' / f'{site}__ALS'
    z = loadz(root / 'distances' / f'{fam}.npz', ['sample_s', 'sample_tau', 'sample_eligible', 'sample_reference_row'])
    xyz = loadz(root / 'distances' / f'{fam}_samples.npz', ['xyz'])['xyz']
    labels = loadz(root / 'stage1_cells.npz', ['case_id'])['case_id']
    steep = abs(add2_scores.normal_z(site, 'ALS', fam)) < .5
    ix = z['sample_reference_row']; ok = ix >= 0
    case = np.full(len(ix), -1, 'i1'); case[ok] = labels[ix[ok]]
    s, t = z['sample_s'], z['sample_tau']
    used = z['sample_eligible'] & ~steep
    fin = np.isfinite(s)
    cl = np.full(len(s), 4, 'i1')                 # 4 = excluded from accuracy (no reference within 1 m, or steep)
    cl[used & ~fin] = 3                           # 3 = used, no distance
    cl[used & fin & (np.abs(s) <= t)] = 0         # in tau
    cl[used & fin & (s > t)] = 1                  # out +
    cl[used & fin & (s < -t)] = 2                 # out -
    return xyz, cl, case


CLN = {0: 'τ 안', 1: 'τ 밖 +', 2: 'τ 밖 −', 3: '거리 없음', 4: '정확성에서 제외(참값 1 m 밖·가파름)'}


def mesh(site, plan):
    cfg()
    fam = FAM[plan]
    root = TU / 'gt/scenes' / f'{site}__ALS'
    meta = json.loads((root / 'distances' / f'{fam}.json').read_text())
    mp = mesh_path(meta['mesh'])
    xyz, cl, case = classes(site, fam)
    V, F = read_surface(str(mp))
    tri = V[F]; del V, F; gc.collect()
    area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    cen = tri.mean(1); del tri; gc.collect()
    lo, hi = box(site)
    inb = inside(cen, lo, hi)
    j = cKDTree(xyz).query(cen, workers=8)[1]
    fcl, fcase = cl[j], case[j]
    out = dict(site=site, plan=plan, family=fam, mesh=str(mp), faces=int(len(area)), faces_in_box=int(inb.sum()), area_m2=float(area[inb].sum()))
    for k, n in CLN.items():
        out[f'area_{n}_m2'] = float(area[inb & (fcl == k)].sum())
        out[f'area_둘다맞음_{n}_m2'] = float(area[inb & (fcl == k) & (fcase == 0)].sum())
        out[f'samples_{n}'] = int((cl == k).sum())
        out[f'samples_둘다맞음_{n}'] = int(((cl == k) & (case == 0)).sum())
    for nm, mm in [('all', np.ones(len(cl), bool)), ('둘다맞음', case == 0)]:
        u = mm & (cl <= 3)
        out[f'accuracy_{nm}_pct_check'] = 100. * float(((cl == 0) & mm).sum() / max(1, u.sum()))
    PARTS.mkdir(parents=True, exist_ok=True)
    c0 = (case == 0) & (cl <= 3)
    np.savez_compressed(PARTS / f'{site}_{plan}.npz', xy=xyz[c0, :2].astype('f4'), cl=cl[c0])
    dump(PARTS / f'{site}_{plan}.json', out | dict(scientific_verdict=None))
    print('MESH', site, plan, flush=True)


def join(site):
    cfg()
    rows = [json.loads((PARTS / f'{site}_{p}.json').read_text()) if (PARTS / f'{site}_{p}.json').exists() else dict(site=site, plan=p, status='없음') for p in PLANS]
    write(f'add1_7_mesh_{site}', rows, 'addendum 1 item 7: mesh faces inside the box; each face takes the class of its nearest scored sample (GTJUDGE samples): in tau, out + (s > tau), out - (s < -tau), no distance, excluded from accuracy (no reference within 1 m or steep, the §3.4 rule); areas all cases and case 0 (둘 다 맞음); accuracy recomputed from the samples as a check')
    P = {p: np.load(PARTS / f'{site}_{p}.npz') for p in PLANS if (PARTS / f'{site}_{p}.npz').exists()}
    lo, hi = box(site)
    # 넷 only: out-of-tau 넷 samples whose nearest building-unit (s0) case-0 sample within 0.1 m is in tau, or none within 0.1 m
    t8 = []
    plt = plt_ko()
    fig, ax = plt.subplots(1, 3, figsize=(22, 8))
    only = {}
    if '건물단위_s0' in P:
        b = P['건물단위_s0']; tb = cKDTree(b['xy'])
        for plan in ['전체', '넷', '아홉']:
            if plan not in P:
                continue
            q = P[plan]; out = q['cl'] != 0
            out &= q['cl'] != 3
            d, j = tb.query(q['xy'][out], workers=8, distance_upper_bound=.1)
            near = np.isfinite(d)
            jj = np.where(near, j, 0)
            b_in = near & (b['cl'][jj] == 0)
            only[plan] = dict(xy=q['xy'][out][b_in | ~near], kind=np.where(b_in, 1, 2)[b_in | ~near])
            t8.append(dict(site=site, plan=plan, case0_out_samples=int(out.sum()), building_s0_in_tau_within_0p1m=int(b_in.sum()),
                           building_s0_out_within_0p1m=int((near & ~b_in).sum()), no_building_s0_sample_within_0p1m=int((~near).sum()),
                           case0_out_building_s0=int(((b['cl'] != 0) & (b['cl'] != 3)).sum()), case0_used_building_s0=int(len(b['cl']))))
    for a, (title, key) in zip(ax, [('건물 단위 씨앗 0', '건물단위_s0'), ('넷', '넷')]):
        if key not in P:
            a.text(.5, .5, '없음', transform=a.transAxes); continue
        q = P[key]
        for k, c in [(1, 'tab:red'), (2, 'tab:blue')]:
            mm = q['cl'] == k
            a.scatter(q['xy'][mm, 0], q['xy'][mm, 1], s=.2, c=c, label=f'{CLN[k]} ({int(mm.sum()):,})', rasterized=True)
        a.set_title(f'{title}: 둘 다 맞음 경우의 τ 밖 표본 (τ 안 {100 * float((q["cl"] == 0).sum() / max(1, len(q["cl"]))):.1f} %)')
    if '넷' in only:
        o = only['넷']
        for k, c, n in [(1, 'tab:purple', '건물 단위는 0.1 m 안에 τ 안 표본'), (2, 'tab:gray', '건물 단위는 0.1 m 안에 표본 없음')]:
            mm = o['kind'] == k
            ax[2].scatter(o['xy'][mm, 0], o['xy'][mm, 1], s=.2, c=c, label=f'{n} ({int(mm.sum()):,})', rasterized=True)
        ax[2].set_title('넷에만 τ 밖')
    for a in ax:
        a.set(xlim=(lo[0], hi[0]), ylim=(lo[1], hi[1]), aspect='equal', xlabel='x (m)', ylabel='y (m)')
        a.legend(fontsize=8, markerscale=20, loc='lower left')
    nc = cells_json('넷')
    for a in ax:
        for sg in nc['boundaries']:
            l_, h_ = np.clip(np.array(sg['lo']), lo[:2] - 5, hi[:2] + 5), np.clip(np.array(sg['hi']), lo[:2] - 5, hi[:2] + 5)
            a.plot([l_[0], h_[0]], [l_[1], h_[1]], color='#00a0a0', ls='--', lw=1)
    fig.suptitle(f'{site} · 항공 LiDAR · 둘 다 맞음 경우 τ 밖 표본의 자리 (빨강 +, 파랑 −; 청록 점선 = 넷 원래 칸 경계)')
    fig.tight_layout()
    out = D / 'figures' / f'add1_case0_out_{site}'
    fig.savefig(out.with_suffix('.png'), dpi=150); plt.close(fig)
    dump(out.with_suffix('.json'), dict(site=site, rows=t8, rule='넷 τ 밖(둘 다 맞음, 정확성에 쓰는 표본) 중 건물 단위 씨앗 0의 가장 가까운 둘 다 맞음 표본이 0.1 m 안에서 τ 안이면 넷에만 τ 밖', scientific_verdict=None))
    # owner-cell accuracy of 넷 and 아홉 (case 0 and all used samples of case 0 parts only -> case 0)
    for plan in ['넷', '아홉']:
        if plan not in P:
            continue
        q = P[plan]
        for c in cells_json(plan)['cells']:
            o = np.array(c['original_min'], float); h = np.array(c['original_max'], float)
            k2 = (q['xy'][:, 0] >= o[0]) & (q['xy'][:, 0] < h[0]) & (q['xy'][:, 1] >= o[1]) & (q['xy'][:, 1] < h[1])
            if not k2.any():
                continue
            row = dict(site=site, plan=plan, cell=c['id'], case0_used_samples=int(k2.sum()), case0_in_tau=int((k2 & (q['cl'] == 0)).sum()),
                       case0_accuracy_pct=100. * float((k2 & (q['cl'] == 0)).sum() / k2.sum()))
            for ref in ['건물단위_s0', '건물단위_s1']:
                if ref in P:
                    b = P[ref]
                    kb = (b['xy'][:, 0] >= o[0]) & (b['xy'][:, 0] < h[0]) & (b['xy'][:, 1] >= o[1]) & (b['xy'][:, 1] < h[1])
                    row[f'{ref}_same_area_accuracy_pct'] = 100. * float((kb & (b['cl'] == 0)).sum() / max(1, kb.sum()))
                    row[f'{ref}_same_area_samples'] = int(kb.sum())
            t8.append(row)
    write(f'add1_8_where_{site}', t8, 'addendum 1 item 8: case 0 (둘 다 맞음) samples used for accuracy (§3.4: reference within 1 m, not steep; no-distance counted as not in tau): out-of-tau samples of each group plan against the nearest building-unit s0 sample (0.1 m); 넷/아홉 accuracy per original owner cell with the building-unit accuracy over the same xy area')
    print('JOIN', site, flush=True)


if __name__ == '__main__':
    dict(inputs=inputs, gauss=gauss, mesh=mesh, join=join)[sys.argv[1]](*sys.argv[2:])
