import sys; sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1')  # addendum-1 copy of te_tables.py (tag a1 tables -> addendum1/tables)
"""Stage 2 tables (order 4.1-4.5, 7.1): per cell x arm class counts, shares and ratios (lost / control), cross tables, culprit candidates,
tau-multiplier drops, |s| quantiles, check-2 distributions, 3-가 detail, page-50 recount, check-4 four-depth summaries. argv: [tag]"""
from common import *
from a1_te_checks import C1, C1R, C2, C3, C3E, C4, NA
CELLS = ['c1', 'c2', 'c3']

def load(stem, arm, tag):
    name = f'{stem}__{arm}' + (f'__{tag}' if tag else '')
    base = O/'addendum1' if tag == 'a1' else O
    if not (base/'checks'/f'{name}.npz').exists(): return None, None
    return loadz(base/'checks'/f'{name}.npz'), loadz(base/'checks'/f'{name}_pairs.npz')

def share_rows(cell, arm, key, classes, z, m_lost, m_ctrl, tag):
    rows = []; nl, nc = int(m_lost.sum()), int(m_ctrl.sum())
    for k in classes+[NA, '맞음(τ 안)']:
        a = int((z[key][m_lost] == k).sum()); b = int((z[key][m_ctrl] == k).sum())
        if k in (NA, '맞음(τ 안)') and a == 0 and b == 0: continue
        pa = 100*a/nl if nl else None; pb = 100*b/nc if nc else None
        rows.append(dict(cell=cell, arm=arm, run=tag or 'stored', check=key, cls=k, lost_n=a, lost_pct=pa, control_n=b, control_pct=pb,
                         ratio=(pa/pb if pa is not None and pb else (None if not pa else 'inf'))))
    return rows

def main(tag=''):
    c = cfg(); T = {k: [] for k in ['check1', 'check2', 'check3', 'check3_empty', 'check4', 'cross', 'culprit', 'tau', 'quantiles', 'check2_dist', 'check3_detail', 'page50', 'four_depths', 'summary']}
    for cell in CELLS:
        stem = STEMS[cell]; site, prior = stem.split('__'); cs = c['cells'][cell]
        for arm in ARMS:
            z, pr = load(stem, arm, tag)
            if z is None: continue
            m = z['cell'] == int(cell[1]); L = m & (z['set'] == 0); K = m & (z['set'] == 1); res = cell == 'c3'
            for key, cl in [('check1', C1R if res else C1), ('check2', C2), ('check3', C3), ('check3_empty', C3E), ('check4', C4)]:
                if res and key in ['check2', 'check3_empty']: continue
                T[key] += share_rows(cell, arm, key, cl, z, L, K, tag)
            for a, b in [('check1', 'check2'), ('check2', 'check3'), ('check3', 'check4'), ('check3_empty', 'check4')]:
                if res and 'check2' in (a, b): continue
                if res and a == 'check3_empty': continue
                keys = sorted(set(zip(z[a][L], z[b][L])))
                for x, y in keys:
                    k = int(((z[a][L] == x) & (z[b][L] == y)).sum()); T['cross'].append(dict(cell=cell, arm=arm, run=tag or 'stored', rows=a, cols=b, row_cls=x, col_cls=y, n=k, pct_of_lost=100*k/max(1, int(L.sum()))))
            nl = int(L.sum()); nc = int(K.sum())
            cand = []
            for k in ['3-가', '3-나', '3-다', '3-라']:
                a = int((z['check3'][L] == k).sum()); b = int((z['check3'][K] == k).sum()); pa = 100*a/nl if nl else 0; pb = 100*b/nc if nc else 0
                r = pa/pb if pb else (float('inf') if pa else None); ok = pa >= 100*c['culprit']['share_min'] and r is not None and r >= c['culprit']['ratio_min']
                T['culprit'].append(dict(cell=cell, arm=arm, run=tag or 'stored', cls=k, lost_pct=pa, control_pct=pb, ratio=r if r != float('inf') else 'inf', candidate=ok))
                if ok: cand.append(k)
            # tau multipliers (stored point data, cells fixed at tau=1)
            if not tag:
                A11 = np.load(GT/'addendum11/final_data'/f'{stem}.npz'); A12 = np.load(GT/'addendum12/distance_A1'/f'{stem}.npz')
                src = lambda mth: A12 if mth == 'A1' else A11
                for f in c['check1']['tau_multipliers']:
                    vals = {}
                    for stage, mth in [('target', TARGET_METHOD[arm]), ('trained', TRAINED_METHOD[arm])]:
                        Z = src(mth)
                        if not res:
                            s = Z[f'reference__{mth}__s_m'].astype(float); tt = Z['reference__tau_m'].astype(float); cc = Z['reference__case_id'] == cs['case_id']
                            vals[stage] = 100*float((np.isfinite(s[cc]) & (np.abs(s[cc]) <= f*tt[cc]+(1e-7 if f == 1 else 0))).mean()) if f != 1 else 100*float(Z[f'reference__{mth}__within_tau1'][cc].astype(bool).mean())
                        else:
                            s = Z[f'result__{mth}__s_m'].astype(float); tt = Z[f'result__{mth}__tau_m'].astype(float); e = Z[f'result__{mth}__eligible_new'].astype(bool) & (Z[f'result__{mth}__case_id'] == cs['case_id'])
                            w = Z[f'result__{mth}__within_tau1'].astype(bool) if f == 1 else (np.isfinite(s) & (np.abs(s) <= f*tt))
                            vals[stage] = 100*float((e & w).sum())/max(1, int(e.sum()))
                    T['tau'].append(dict(cell=cell, arm=arm, tau_multiplier=f, target=vals['target'], trained=vals['trained'], drop_pp=vals['target']-vals['trained']))
                A11.close(); A12.close()
            s = np.abs(z['s_used'][L]) if not res else np.abs(loadz(O/('sets_'+tag if tag and tag != 'a1' else 'sets')/f'{cell}_{arm}_lost.npz', ['trained_s_m'])['trained_s_m'])
            fin = np.isfinite(s); q = np.quantile(s[fin], c['check1']['quantiles']).tolist() if fin.any() else [None]*3
            T['quantiles'].append(dict(cell=cell, arm=arm, run=tag or 'stored', lost=nl, with_distance=int(fin.sum()), no_surface_or_missing=int((~fin).sum()), abs_s_p50=q[0], abs_s_p683=q[1], abs_s_p95=q[2]))
            if not res:
                for setname, mm in [('lost', L), ('control', K)]:
                    for key in ['seen_views', 'owner_match_views', 'weight_floor_views', 'mean_weight_matching']:
                        v = z[key][mm].astype(float); v = v[np.isfinite(v)]
                        T['check2_dist'].append(dict(cell=cell, arm=arm, run=tag or 'stored', set=setname, quantity=key, n=len(v), mean=float(v.mean()) if len(v) else None,
                                                     p10=float(np.quantile(v, .1)) if len(v) else None, p50=float(np.median(v)) if len(v) else None, p90=float(np.quantile(v, .9)) if len(v) else None))
            g3 = L & (z['check3'] == '3-가')
            if g3.any():
                tilt = np.abs(z['drawer_point_normal_m'][g3]) <= z['tau'][g3]
                T['check3_detail'].append(dict(cell=cell, arm=arm, run=tag or 'stored', n_3ga=int(g3.sum()), disc_tilt_centre_within_tau=int(tilt.sum()), within_interval_beyond_tau=int((~tilt).sum()),
                                               target_height_abs_p50_m=float(np.median(np.abs(z['drawer_target_height_m'][g3]))), interval_p50_m=float(np.median(z['drawer_interval_m'][g3]))))
            beyond = L & (np.isfinite(z['page50_distance_m']))
            if not res: beyond &= np.isfinite(z['s_used'])
            kk = K & np.isfinite(z['page50_distance_m'])
            for rule in ['outside_fixed', 'outside_patch']:
                pa = 100*float(z['page50_'+rule][beyond].mean()) if beyond.any() else None; pb = 100*float(z['page50_'+rule][kk].mean()) if kk.any() else None
                T['page50'].append(dict(cell=cell, arm=arm, run=tag or 'stored', rule=rule, lost_beyond_tau_n=int(beyond.sum()), lost_pct=pa, control_n=int(kk.sum()), control_pct=pb, ratio=pa/pb if pa is not None and pb else None))
            ii = np.flatnonzero(L); mpair = np.isin(pr['point'], ii)
            for k in C4:
                sel = np.isin(pr['point'], np.flatnonzero(L & (z['check4'] == k)))
                if not sel.any(): continue
                ref = pr['ref_z'][sel].astype(float); ref[~np.isfinite(ref)] = np.nan  # empty reference z-buffer pixel (c3) = missing
                T['four_depths'].append(dict(cell=cell, arm=arm, run=tag or 'stored', cls=k, pairs=int(sel.sum()), render_minus_ref_p50=float(np.nanmedian(pr['render_z'][sel]-ref)),
                                             mesh_minus_ref_p50=float(np.nanmedian(pr['mesh_z'][sel]-ref)), target_minus_ref_p50=float(np.nanmedian(np.where(pr['target_z'][sel] > 0, pr['target_z'][sel]-ref, np.nan))),
                                             empty_pct=100*float(pr['empty'][sel].mean())))
            big = {}
            for key, cl in [('check1', C1R if res else C1), ('check2', C2), ('check3', C3), ('check4', C4)]:
                if res and key == 'check2': continue
                vals = z[key][L]; vals = vals[vals != NA]
                if len(vals):
                    u, cnt = np.unique(vals, return_counts=True); j = int(np.argmax(cnt)); big[key] = (str(u[j]), 100*cnt[j]/nl)
            T['summary'].append(dict(cell=cell, arm=arm, run=tag or 'stored', lost=nl, control=nc, few=nl < 1000, culprit=','.join(cand) or '후보 없음',
                                     **{f'{k}_largest': v[0] for k, v in big.items()}, **{f'{k}_largest_pct_of_lost': v[1] for k, v in big.items()}))
    suf = f'_{tag}' if tag else ''
    def clean(v):
        if isinstance(v, (float, np.floating)) and not np.isfinite(v): return None if np.isnan(v) else ('inf' if v > 0 else '-inf')
        return v.item() if isinstance(v, np.generic) else v
    for k, rows in T.items():
        if rows: table(f'{k}{suf}', [{a_: clean(b_) for a_, b_ in r.items()} for r in rows], folder=(D/'addendum1/tables') if tag == 'a1' else None)
    print('TABLES', {k: len(v) for k, v in T.items()}); [print(r) for r in T['summary']]

if __name__ == '__main__': main(*sys.argv[1:])
