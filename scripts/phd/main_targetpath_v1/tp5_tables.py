"""Orders 2 and 3 tables (CPU, reads /tp/pairs, /tp/weight, /tp/points). usage: tp5_tables.py
tp_supervision: scene x run x group (and x the point's method judgment region): per-point shares of the five kinds (median, quartiles), points with
  kind 1 on more than half of their views, points with kinds 2+3 on more than half, supervision of occluded pixels, weight medians, sub-splits.
tp_cross (가): main kind in the method run x GTT kept / lost of the same point. tp_wrong (나): wrong targets (kinds 2, 4) at fixed / not fixed points.
tp_weight: order 3. Cells with fewer than 1,000 GT points keep counts only (ratio columns empty).
Also writes /tp/points/tp_<stem>.npz (per point: group, kind view counts per run, weight median, occluded supervised views, main Gaussian kind)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_targetpath_v1')
from tp_common import *
MIN = 1000
REGS = [('전체', None), ('일치', [0]), ('보존', [1]), ('보정', [2, 3]), ('결측', [4]), ('그 밖', [9, -1])]

def per_point(z, n):
    pt = z['pt']; kind = z['kind']; cnt = np.zeros((n, 5), 'i4'); np.add.at(cnt, (pt, kind), 1); return cnt

def gmed(key, val, n):
    out = np.full(n, np.nan); ok = np.isfinite(val); k = key[ok]; v = val[ok]
    if not len(k): return out
    o = np.lexsort((v, k)); k = k[o]; v = v[o]; st = np.searchsorted(k, np.arange(n+1)); c = st[1:]-st[:-1]; h = np.flatnonzero(c)
    out[h] = .5*(v[st[h]+(c[h]-1)//2]+v[st[h]+c[h]//2]); return out

def share(a, b): return round(100*a/b, 2) if b else None

def sup_rows(stem, run, P, z, vs='바깥쪽 모든 영상'):
    n = len(P['group']); cnt = per_point(z, n); nv = cnt.sum(1); fr = cnt/np.maximum(nv, 1)[:, None]; pt = z['pt']; tau = P['tau'][pt]
    k = z['kind']; w = z['w']; sup = k != 4
    rows = []
    for g in range(6):
        for rn, rv in REGS:
            sel = (P['group'] == g) & (nv > 0) & (np.ones(n, bool) if rv is None else np.isin(P['method_region'], rv))
            m = sel[pt]; npts = int(sel.sum()); big = npts >= MIN
            r = dict(title=TITLE, stem=STEM_KO[stem], run=RUN_KO[run], view_set=vs, group=GRP[g], point_region=rn, points=npts, points_in_group=int((P['group'] == g).sum()), pairs=int(m.sum()),
                     views_per_point_median=float(np.median(nv[sel])) if npts else None)
            for i in range(5):
                qq = q(fr[sel, i]) if (big and npts) else [None]*3
                r[f'kind{i+1}_share_q25'], r[f'kind{i+1}_share_median'], r[f'kind{i+1}_share_q75'] = qq
            r['kind1_half_n'] = int((fr[sel, 0] > .5).sum()); r['kind23_half_n'] = int((fr[sel, 1]+fr[sel, 2] > .5).sum())
            r['kind1_half_pct'] = share(r['kind1_half_n'], npts) if big else None; r['kind23_half_pct'] = share(r['kind23_half_n'], npts) if big else None
            for o_ in ['occ10', 'occ1']:
                oc = m & z[o_]; r[f'{o_}_pairs'] = int(oc.sum()); r[f'{o_}_supervised_pct'] = share(int((oc & sup).sum()), int(oc.sum())) if big else None
                for i in range(4): r[f'{o_}_kind{i+1}_pct'] = share(int((oc & (k == i)).sum()), int(oc.sum())) if big else None
            r['w_median_kind1'] = float(np.median(w[m & (k == 0)])) if (m & (k == 0)).any() else None
            r['w_median_kind23'] = float(np.median(w[m & ((k == 1) | (k == 2))])) if (m & ((k == 1) | (k == 2))).any() else None
            k2 = m & (k == 1); r['kind2_target_ok_pct'] = share(int((k2 & z['target_ok']).sum()), int(k2.sum())) if big else None
            for rg, nm in [(0, '일치'), (1, '보존'), (2, '보정'), (3, '보정(빈 공간)'), (4, '결측'), (9, '미판정')]:
                r[f'kind2_region_{nm}_pct'] = share(int((k2 & (z['owner_region'] == rg)).sum()), int(k2.sum())) if (big and run == 'ft') else None
            k3 = m & (k == 2)
            for pi, pn in enumerate(POS3): r[f'kind3_{pn}_pct'] = share(int((k3 & (z['pos'] == pi)).sum()), int(k3.sum())) if big else None
            k4 = m & (k == 3); r['kind4_target_ok_pct'] = share(int((k4 & z['target_ok']).sum()), int(k4.sum())) if big else None
            for rg, nm in [(0, '일치'), (1, '보존'), (2, '보정'), (4, '결측')]:
                r[f'kind4_region_{nm}_pct'] = share(int((k4 & (z['owner_region'] == rg)).sum()), int(k4.sum())) if (big and run == 'ft') else None
            for pi, pn in enumerate(POS3 + ['면 없음']):
                rp = z['rpos'] == (pi if pi < 3 else -1); r[f'render_{pn}_pct'] = share(int((m & rp).sum()), int(m.sum())) if big else None
                r[f'render_{pn}_kind1_pct'] = share(int((m & rp & (k == 0)).sum()), int((m & (k == 0)).sum())) if big else None
            rows.append(r)
    return rows, cnt, nv

def main():
    t0 = time.monotonic(); sup, cross, wrong, wt, wtp = [], [], [], [], []
    for stem in STEMS:
        P = loadz(O/'points'/f'sel_{stem}.npz'); n = len(P['group']); out = dict(point_id=P['point_id'], group=P['group'], group_gtt=P['group_gtt'], method_region=P['method_region'], xyz=P['xyz'])
        Z = {}
        for run in ['ft', 'gtt']:
            p = O/'pairs'/f'{run}_{stem}.npz'
            if not p.exists(): continue
            z = loadz(p); z.pop('views', None); Z[run] = z; rows, cnt, nv = sup_rows(stem, run, P, z); sup += rows
            vis = ~z['occ10']; zv = {k: v[vis] for k, v in z.items()}; rows_v, cnt_v, nv_v = sup_rows(stem, run, P, zv, '가려지지 않은 영상(10 m 규칙)'); sup += rows_v
            out[f'{run}_kind_views_visible'] = cnt_v
            out[f'{run}_kind_views'] = cnt; out[f'{run}_views'] = nv; out[f'{run}_w_median'] = gmed(z['pt'].astype('i8'), z['w'].astype('f8'), n).astype('f4')
            out[f'{run}_occ10_supervised_views'] = np.bincount(z['pt'], z['occ10'] & (z['kind'] != 4), n).astype('i4')
            out[f'{run}_occ1_supervised_views'] = np.bincount(z['pt'], z['occ1'] & (z['kind'] != 4), n).astype('i4')
        if 'ft' in Z:
            for vs, cnt in [('바깥쪽 모든 영상', out['ft_kind_views']), ('가려지지 않은 영상(10 m 규칙)', out['ft_kind_views_visible'])]:
              nv = cnt.sum(1); main_k = np.where(nv > 0, np.argmax(cnt, 1), -1); out['ft_main_kind' if vs[0] == '바' else 'ft_main_kind_visible'] = main_k.astype('i1')
              for g in [0, 1]:
                for mk in range(-1, 5):
                    s = (P['group'] == g) & (main_k == mk); tot = int(s.sum())
                    if not tot: continue
                    cross.append(dict(title=TITLE, stem=STEM_KO[stem], view_set=vs, group=GRP[g], method_main_kind=KIND[mk] if mk >= 0 else '본 영상 없음', points=tot,
                                      gtt_kept=int((s & (P['group_gtt'] == 0)).sum()), gtt_lost=int((s & (P['group_gtt'] == 1)).sum()),
                                      gtt_target_outside=int((s & np.isin(P['group_gtt'], [2, 3])).sum()), gtt_no_run=int((s & (P['group_gtt'] == -1)).sum()),
                                      gtt_lost_pct=share(int((s & (P['group_gtt'] == 1)).sum()), int((s & (P['group_gtt'] >= 0)).sum())) if tot >= MIN else None))
            # 나: wrong targets (kinds 2, 4) at fixed / not fixed
            z = Z['ft']; pt = z['pt']; tau = P['tau'][pt].astype('f8'); off = np.abs(z['tdepth'].astype('f8')-z['z'])/tau
            for g in [2, 3]:
                m = (P['group'][pt] == g); wk = m & np.isin(z['kind'], [1, 3]); npts = int((P['group'] == g).sum()); big = npts >= MIN
                pts_w = np.unique(pt[wk])
                wrong.append(dict(title=TITLE, stem=STEM_KO[stem], run=RUN_KO['ft'], group=GRP[g], points=npts, points_with_wrong_target_view=int(len(pts_w)),
                                  wrong_target_pairs=int(wk.sum()), pairs=int(m.sum()), wrong_target_pairs_pct=share(int(wk.sum()), int(m.sum())) if big else None,
                                  w_median=float(np.median(z['w'][wk])) if wk.any() else None, w_q25_q75=q(z['w'][wk], (25, 75)) if wk.any() else None,
                                  offset_tau_median=float(np.median(off[wk])) if wk.any() else None, offset_tau_q25_q75=q(off[wk], (25, 75)) if wk.any() else None,
                                  kind2_pairs=int((m & (z['kind'] == 1)).sum()), kind4_pairs=int((m & (z['kind'] == 3)).sum()),
                                  w10_pct=share(int((wk & (z['w'] >= 10-1e-5)).sum()), int(wk.sum())) if big else None,
                                  w01_pct=share(int((wk & (z['w'] <= .1+1e-6)).sum()), int(wk.sum())) if big else None,
                                  kind1_pairs=int((m & (z['kind'] == 0)).sum())))
            # order 3, pair part: kind-1 pixels of the target points with w at 10 (lost vs kept)
            for g in [0, 1, 2, 3, 4, 5]:
                m = (P['group'][pt] == g) & (z['kind'] == 0); npts = int((P['group'] == g).sum()); big = npts >= MIN
                wtp.append(dict(title=TITLE, stem=STEM_KO[stem], run=RUN_KO['ft'], group=GRP[g], points=npts, kind1_pairs=int(m.sum()),
                                kind1_w10_n=int((m & (z['w'] >= 10-1e-5)).sum()), kind1_w01_n=int((m & (z['w'] <= .1+1e-6)).sum()),
                                kind1_w10_pct=share(int((m & (z['w'] >= 10-1e-5)).sum()), int(m.sum())) if big else None,
                                kind1_w01_pct=share(int((m & (z['w'] <= .1+1e-6)).sum()), int(m.sum())) if big else None,
                                kind1_w_median=float(np.median(z['w'][m])) if m.any() else None))
        for run in ['ft', 'gtt']:
            p = O/'weight'/f'{run}_{stem}.json'
            if not p.exists(): continue
            W_ = json.loads(p.read_text()); T = W_['totals']; rows_ = W_['rows']; mw = [r['target_mean_weight'] for r in rows_ if r['target_mean_weight'] is not None]
            r = dict(title=TITLE, stem=STEM_KO[stem], run=RUN_KO[run], views=W_['views'], weight_formula=('clip(σ_ref/σ, 0.1, 10)' if W_['formula_power1_all'] else ('clip((σ_ref/σ)², 0.1, 10)' if W_['formula_power2_all'] else '그 밖')),
                     sigma_ref_min=W_['sigma_ref_min'], sigma_ref_median=W_['sigma_ref_median'], sigma_ref_max=W_['sigma_ref_max'],
                     target_mean_weight_view_min=min(mw) if mw else None, target_mean_weight_view_median=float(np.median(mw)) if mw else None, target_mean_weight_view_max=max(mw) if mw else None)
            for c, nm in [(0, '일치'), (1, '보존'), (2, '보정'), (3, '보정(빈 공간)'), (4, '결측'), (9, '미판정'), (-2, '영상 깊이 목표')]:
                nn = T[f'n_{c}']; r[f'{nm}_pixels'] = nn; r[f'{nm}_w10_pct'] = share(T[f'hi_{c}'], nn); r[f'{nm}_w01_pct'] = share(T[f'lo_{c}'], nn); r[f'{nm}_w_mean'] = (T[f'wsum_{c}']/nn) if nn else None
            if run == 'gtt': r['all_weights_one'] = all(r_.get('target_mean_weight') in (None, 1.0) for r_ in rows_) and all(set(r_['image_depth_weights']) <= {1.0} for r_ in rows_)
            wt.append(r)
        for run in ['ft', 'gtt']:   # order 4 per point: main kind of the largest-weight splat over the facing views (-1 = not computed); 0..3 = GKIND
            fp = O/'points'/f'front_{run}_{stem}.npz'
            if fp.exists(): out[f'{run}_main_gaussian_kind'] = loadz(fp, ['main_kind'])['main_kind']
        out['codes'] = np.array(json.dumps(dict(group=GRP, kind=KIND, gaussian_kind=GKIND, method_region=REGION, group_gtt={0: '지킴', 1: '잃음', 2: '목표 밖(지킴)', 3: '목표 밖(틀림)', -1: '판 없음'}), ensure_ascii=False))
        if 'ft' in Z: savez(O/'points'/f'tp_{stem}.npz', **out); savez(D/'points'/f'tp_{stem}.npz', **out)
        print('TP5', stem, round(time.monotonic()-t0), flush=True)
    table('tp_supervision', sup); table('tp_cross', cross); table('tp_wrong', wrong); table('tp_weight', wt); table('tp_weight_pairs', wtp)
    print('TP5_DONE', len(sup), len(cross), len(wrong), len(wt), round(time.monotonic()-t0), flush=True)

if __name__ == '__main__': main()
