"""Work ra (order 5): what draws the surface at fixed points (target wrong, result right). GPU (/source = r31).
  draw <stem>     : 2000 fixed + 2000 kept points (seed 0), three views each, splat weight within +-tau of the GT depth by kind and judgment;
                    record-run history of the top-weight Gaussian where a full-scene record exists; fate of the seeds first bound to the fixed points' patches
  tables          : tables/ra_*.csv"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4')
from a4_common import *
from a4_da import contrib, gmodel, gpu_setup, load_pt, TLCASE
import time
RA = A4O/'ra'; SCENES = ['B0_b10__ALS', 'B0_b10__LoD2', 'B173nb_b10__ALS', 'B173nb_b10__LoD2', 'R1rep_b10__ALS', 'R1rep_b10__LoD2']
RECORD = {'B0_b10__LoD2': (TLCASE, 'scene'), 'R1rep_b10__ALS': (RUNS4['tl_R1_ALS_own']['model'], 'scene13')}
JUD = {0: '일치', 1: '보존', 2: '보정'}

def points(stem):
    A = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); el = A['reference__eligible'].astype(bool)
    tw = A['reference__judgment_mesh__within_tau1'].astype(bool); rw = A['reference__FINALTRAIN_30000__within_tau1'].astype(bool)
    grp = np.where(tw, np.where(rw, 0, 1), np.where(rw, 2, 3)); rng = np.random.default_rng(0); out = {}
    for name, g in [('fixed', 2), ('kept', 0), ('both_wrong', 3)]:
        ii = np.flatnonzero(el & (grp == g)); ii = np.sort(rng.choice(ii, min(2000, len(ii)), replace=False)) if len(ii) else ii
        out[name] = dict(pid=A['reference__point_id'][ii], xyz=A['reference__xyz'][ii].astype('f8'), tau=A['reference__tau_m'][ii].astype('f8'), case=A['reference__case_id'][ii])
    return out

def model_of(stem, kind):
    import torch
    if kind == 'final':
        md = model_dir(stem, 'own'); s = loadz(md/'target_monitor/snapshot_30000.npz', ['target_tag', 'target_index', 'init_id'])
        sys.path.insert(0, '/source'); from scene import GaussianModel; g = GaussianModel(3); g.load_ply(str(md/'point_cloud/iteration_30000/point_cloud.ply'))
        return g, dict(tag=s['target_tag'], tidx=s['target_index'], init_id=s['init_id'], uid=None)
    m, _ = RECORD[stem]; S = load_pt(m, '30000'); return gmodel(S), dict(tag=S['target_tag'].numpy(), tidx=S['target_index'].numpy(), init_id=S['init_id'].numpy(), uid=S['uid'].numpy())

def draw(stem):
    import torch
    camera = gpu_setup(); t0 = time.monotonic(); RA.mkdir(parents=True, exist_ok=True); P = points(stem); T = Targets(stem)
    t = loadz(targets_of(stem, 'own'), ['judge_region']); praw_all = gt_row_patch(stem); md = maps_dir(stem, 'own'); mi = json.loads((md/'index.json').read_text())['views']; names = sorted(mi)
    variants = [('final', None)] + ([('record', None)] if stem in RECORD else []); res = {}
    for kind, _ in variants:
        with torch.no_grad():
            g, meta = model_of(stem, kind); from gaussian_renderer import render; from types import SimpleNamespace
            pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False); depth = {}
            allX = np.concatenate([P[k]['xyz'] for k in P]); nset = {k: len(P[k]['xyz']) for k in P}
            cand = []   # (point, view, |rd - z|, u, v, z)
            for j, nm in enumerate(names):
                m = mi[nm]; K = np.asarray(m['K']); M = np.asarray(m['W2C']); Xc = allX@M[:3, :3].T+M[:3, 3]; zc = Xc[:, 2]; okz = zc > .2
                u = np.floor(K[0, 0]*Xc[:, 0]/np.where(okz, zc, 1)+K[0, 2]).astype('i8'); v = np.floor(K[1, 1]*Xc[:, 1]/np.where(okz, zc, 1)+K[1, 2]).astype('i8')
                ins = np.flatnonzero(okz & (u >= 0) & (u < 1024) & (v >= 0) & (v < 741))
                if not len(ins): continue
                rd = render(camera(1024, 741, K, M, nm), g, pipe, torch.zeros(3, device='cuda'))['surf_depth'].squeeze().cpu().numpy()
                cand.append(np.c_[ins, np.full(len(ins), j), np.abs(rd[v[ins], u[ins]]-zc[ins]), u[ins], v[ins], zc[ins]])
            cand = np.concatenate(cand); o = np.lexsort((cand[:, 2], cand[:, 0])); cand = cand[o]; first = np.r_[True, cand[1:, 0] != cand[:-1, 0]]
            rank = np.arange(len(cand))-np.maximum.accumulate(np.where(first, np.arange(len(cand)), 0)); sel = cand[rank < 3]   # three least-occluded views per point
            tau = np.concatenate([P[k]['tau'] for k in P]); pr = praw_all[np.concatenate([P[k]['pid'] for k in P])]; vrow = T.v_of_rows(pr)
            Wk = np.zeros((len(sel), 4)); top = np.full(len(sel), -1, 'i8'); topw = np.zeros(len(sel))
            for j in np.unique(sel[:, 1]).astype('i8'):
                q = np.flatnonzero(sel[:, 1] == j); nm = names[j]; m = mi[nm]; C = contrib(g, camera(1024, 741, np.asarray(m['K']), np.asarray(m['W2C']), nm), sel[q, 3].astype('i8'), sel[q, 4].astype('i8'))
                p = C[:, 0].astype('i8'); pt = sel[q, 0].astype('i8')[p]; ok = np.abs(C[:, 3]-sel[q, 5][p]) <= tau[pt]; gi = C[:, 1].astype('i8')
                kd = np.where(meta['tag'][gi] == 1, np.where(meta['tidx'][gi] == vrow[pt], 0, 1), np.where(meta['tag'][gi] == 2, 2, 3))
                np.add.at(Wk, (q[p[ok]], kd[ok]), C[ok, 2])
                for a_, gg, ww in zip(q[p[ok]], gi[ok], C[ok, 2]):
                    if ww > topw[a_]: topw[a_] = ww; top[a_] = gg
        offs = np.cumsum([0]+[nset[k] for k in P]); setof = np.searchsorted(offs[1:], sel[:, 0].astype('i8'), side='right')
        out = dict(point=sel[:, 0].astype('i8'), view=sel[:, 1].astype('i8'), set=setof, w=Wk, top=top, topw=topw, judge=np.where(pr >= 0, t['judge_region'][np.clip(pr, 0, None)], -1)[sel[:, 0].astype('i8')],
                   case=np.concatenate([P[k]['case'] for k in P])[sel[:, 0].astype('i8')], top_uid=meta['uid'][np.clip(top, 0, None)] if meta['uid'] is not None else np.full(len(top), -1), top_init=meta['init_id'][np.clip(top, 0, None)])
        res[kind] = out
    savez(RA/f'draw_{stem}.npz', **{f'{k}__{f}': v for k, o in res.items() for f, v in o.items()}, set_names=np.array(list(P)))
    fate(stem, P, T, pr_all=praw_all); print('RA_DRAW', stem, round(time.monotonic()-t0), flush=True)

def fate(stem, P, T, pr_all):
    """seeds bound at initialization to the fixed points' column patches: state of their init_id lineage in the FINALTRAIN 30000 snapshot."""
    sd = loadz(PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/stage1'/stem/'seeds.npz', ['patch', 'origin']); s = loadz(model_dir(stem, 'own')/'target_monitor/snapshot_30000.npz', ['target_tag', 'target_index', 'init_id'])
    rows = []
    for name in P:
        pr = np.unique(pr_all[P[name]['pid']]); pr = pr[pr >= 0]; seeds = np.flatnonzero((sd['origin'] == 1) & np.isin(sd['patch'], pr))
        vr = T.v_of_rows(sd['patch'][seeds]); live = np.isin(s['init_id'], seeds); ii = s['init_id'][live]; tg = s['target_tag'][live]; ti = s['target_index'][live]
        own_v = dict(zip(seeds.tolist(), vr.tolist())); same = np.array([ti[k] == own_v[int(ii[k])] for k in range(len(ii))]) if len(ii) else np.zeros(0, bool)
        st = np.full(len(seeds), 0)   # 0 제거됨, 1 풀림, 2 다른 목표, 3 그대로 (lineage: best state among descendants: same > other > released)
        best = {}
        for k in range(len(ii)):
            c = 3 if (tg[k] == 1 and same[k]) else (2 if tg[k] == 1 else 1); best[int(ii[k])] = max(best.get(int(ii[k]), 0), c)
        for k, sid in enumerate(seeds): st[k] = best.get(int(sid), 0)
        rows.append(dict(stem=stem, set=name, patches=len(pr), seeds=len(seeds), deleted_pct=pct(st == 0), released_pct=pct(st == 1), other_target_pct=pct(st == 2), same_target_pct=pct(st == 3),
                         rule='lineage by init_id in the FINALTRAIN 30000 snapshot; a seed counts by its best descendant: same patch > other patch > released; no descendant = deleted'))
    dtable(f'ra_fate_{stem}', rows)

def tables():
    rows = []; hist = []
    for stem in SCENES:
        f = RA/f'draw_{stem}.npz'
        if not f.exists(): continue
        z = loadz(f); names = list(z['set_names'])
        for kind in ['final', 'record']:
            if f'{kind}__w' not in z: continue
            w = z[f'{kind}__w']; st = z[f'{kind}__set']; jd = z[f'{kind}__judge']; cs = z[f'{kind}__case']
            for si, sn in enumerate(names):
                for jn, jm in [('전체', np.ones(len(st), bool))]+[(v, jd == k) for k, v in JUD.items()]:
                    m = (st == si) & jm
                    if sn == 'both_wrong' or (sn == 'fixed' and jn != '전체') or sn == 'kept' and jn == '전체' or (sn == 'fixed' and jn == '전체'):
                        tot = w[m].sum(0); r = dict(stem=stem, model='FINALTRAIN 30,000' if kind == 'final' else '기록 판 30,000', set={'fixed': '고친 점', 'kept': '지킨 점', 'both_wrong': '둘 다 틀림'}[sn], judgment=jn, pixels=int(m.sum()),
                                                    surface_weight_mean=float(w[m].sum(1).mean()) if m.any() else None, **{f'{k}_share_pct': 100*float(tot[i]/max(tot.sum(), 1e-12)) for i, k in enumerate(['같은 목표', '다른 목표', '풀린 것', '묶이지 않은 것'])})
                        rows.append(r)
            # prior-error region (case 1), agreement judgment: fixed vs both wrong
            for sn in ['fixed', 'both_wrong']:
                si = names.index(sn); m = (st == si) & (cs == 1) & (jd == 0); tot = w[m].sum(0)
                rows.append(dict(stem=stem, model='FINALTRAIN 30,000' if kind == 'final' else '기록 판 30,000', set=('고친 점' if sn == 'fixed' else '둘 다 틀림')+' · 사전정보 오류 · 일치', judgment='일치', pixels=int(m.sum()),
                                 surface_weight_mean=float(w[m].sum(1).mean()) if m.any() else None, **{f'{k}_share_pct': 100*float(tot[i]/max(tot.sum(), 1e-12)) for i, k in enumerate(['같은 목표', '다른 목표', '풀린 것', '묶이지 않은 것'])}))
    dtable('ra_surface_weight', rows)
    for stem in RECORD: history(stem)
    fr = []
    for stem in SCENES:
        p = A4D/'tables'/f'ra_fate_{stem}.json'
        if p.exists(): fr += json.loads(p.read_text())['rows']
    dtable('ra_fate', fr)

def history(stem):
    """record run: the top-weight Gaussian per fixed-point pixel: first placement distance to GT, release / retarget iteration, first state within 0.2 m of GT."""
    import torch
    z = loadz(RA/f'draw_{stem}.npz'); names = list(z['set_names']); m_, _ = RECORD[stem]; sv = saves(m_)
    scn = sorted({s['name'] for s in sv if (m_/'trainlog/scene'/f'{s["name"]}.pt').exists()}, key=lambda n: (int(n.split('_')[0]), 0 if 'pre' in n else 1))
    P = points(stem); allX = np.concatenate([P[k]['xyz'] for k in P]); uid = z['record__top_uid']; pt = z['record__point']; st = z['record__set']; good = (z['record__top'] >= 0) & (st == names.index('fixed'))
    U = np.unique(uid[good]); first_pos = {}; first_near = {}; tagseq = {}
    for n in scn:
        S = load_pt(m_, n); ix = {int(u): i for i, u in enumerate(S['uid'].tolist())}; X = S['xyz'].double().numpy()
        for u in U:
            i = ix.get(int(u))
            if i is None: continue
            if int(u) not in first_pos: first_pos[int(u)] = (n, X[i].copy())
            tagseq.setdefault(int(u), []).append((n, int(S['target_tag'][i]), int(S['target_index'][i]), int(S['target_released_at'][i])))
    G = cKDTree(a11_ref(stem)['xyz'].astype('f8')); rows = []
    for u in U:
        fp = first_pos.get(int(u)); seq = tagseq.get(int(u), [])
        d0 = float(G.query(fp[1])[0]) if fp else np.nan
        rel = max([s[3] for s in seq], default=-1); ret = None
        for a, b in zip(seq, seq[1:]):
            if a[1] == 1 and b[1] == 1 and a[2] != b[2]: ret = b[0]; break
        rows.append((u, d0, rel, ret, seq[-1][1] if seq else -1, fp[0] if fp else None))
    # first state within 0.2 m of GT
    near_state = {}
    for n in scn:
        S = load_pt(m_, n); ix = {int(u): i for i, u in enumerate(S['uid'].tolist())}; X = S['xyz'].double().numpy()
        for u in U:
            if int(u) in near_state: continue
            i = ix.get(int(u))
            if i is not None and G.query(X[i])[0] <= .2: near_state[int(u)] = n
    d0 = np.array([r[1] for r in rows]); rel = np.array([r[2] for r in rows]); tags = np.array([r[4] for r in rows])
    out = dict(stem=stem, top_gaussians=len(U), first_place_gt_dist_m_median=med(d0), first_place_within_02m_pct=pct(d0 <= .2), released_pct=pct(rel >= 0), released_at_median=med(rel[rel >= 0]),
               retargeted_pct=pct(np.array([r[3] is not None for r in rows])), tag30000_bound_pct=pct(tags == 1), tag30000_released_pct=pct(tags == 2), tag30000_unbound_pct=pct(tags == 0),
               first_within_02m_state_median=med([int(near_state[int(u)].split('_')[0]) for u in U if int(u) in near_state]), never_within_02m_pct=pct(np.array([int(u) not in near_state for u in U])),
               states_used=len(scn), rule='record run saved full-scene states only (coarse iterations)')
    dtable(f'ra_history_{stem}', [out]); print('HIST', out, flush=True)

if __name__ == '__main__' and sys.argv[1] != 'fixed_cases':
    a = sys.argv[1:]
    {'draw': lambda: draw(a[1]), 'tables': tables}[a[0]]()

def fixed_cases():
    """two representative fixed places in B0 x LoD2 (record run exists): largest 0.5 m-linked cluster of fixed points whose majority judgment is 보정, and the
    largest with majority 일치 or 보존 (order 7: different judgments)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    stem = 'B0_b10__LoD2'; A = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); el = A['reference__eligible'].astype(bool)
    tw = A['reference__judgment_mesh__within_tau1'].astype(bool); rw = A['reference__FINALTRAIN_30000__within_tau1'].astype(bool); ii = np.flatnonzero(el & ~tw & rw)
    X = A['reference__xyz'][ii].astype('f8'); pid = A['reference__point_id'][ii]; t = loadz(targets_of(stem, 'own'), ['judge_region']); pr = gt_row_patch(stem)[pid]; jd = np.where(pr >= 0, t['judge_region'][np.clip(pr, 0, None)], -1)
    pairs = cKDTree(X).query_pairs(.5, output_type='ndarray'); n, lab = connected_components(coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(X), len(X))), directed=False)
    sizes = np.bincount(lab); out = {}; rows = []
    for key, want, label in [('a', {2}, '판정 보정'), ('b', {0, 1}, '판정 일치·보존')]:
        for k in np.argsort(-sizes):
            m = lab == k; vals, cnt = np.unique(jd[m], return_counts=True); maj = int(vals[np.argmax(cnt)])
            if maj in want and sizes[k] >= 50:
                out[f'{key}__xyz'] = X[m]; out[f'{key}__pid'] = pid[m]; out[f'{key}__label'] = np.array(f'{label}, 고친 점 {int(m.sum())}개'); rows.append(dict(case=f'fixed_{key}', label=label, points=int(m.sum()), majority_judgment=JUD.get(maj, maj), centre=X[m].mean(0).tolist())); break
    (A4O/'ba').mkdir(parents=True, exist_ok=True); savez(A4O/'ba'/'fixed_cases.npz', **out); dtable('ba_fixed_cases', rows); print('FIXED', rows, flush=True)
if __name__ == '__main__' and sys.argv[1] == 'fixed_cases': fixed_cases()
