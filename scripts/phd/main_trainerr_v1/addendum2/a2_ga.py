"""Addendum 2 work 가 (order 2). CPU container. No GT in the classification; GT only for the patch case label and the outcome columns.
  stats <stem> <arm> : every training view's target map vs the image (MVS) depth the run read -> per-patch pixel counts (front/same/behind/none, conf pass),
                       applied views, weight sums, per-view south/long-wall pixel counts (B0 LoD2) -> addendum2/ga/<stem>__<arm>.npz
  tables             : 2.2 tables (pixel shares by scene x arm x case [x place], patch front-share bins vs wrong result share, patch value check)"""
from a2_common import *
CLS = ['front', 'same', 'behind', 'none']

def stats(stem, arm):
    c = bcfg(); t0 = Timer(f'a2_ga_stats_{stem}_{arm}'); site = stem.split('__')[0]; md = maps_dir(stem, arm); index = json.loads((md/'index.json').read_text())['views']
    t = loadz(targets_of(stem, arm), ['area']); N = len(t['area'])
    cnt = {k: np.zeros(N, 'i8') for k in CLS+['target', 'conf_pass', 'behind_conf_pass', 'front_conf_pass']}; wsum = np.zeros(N); vcount = np.zeros(N, 'i4')
    zones = wall_zone_patches(stem, arm) if stem == 'B0_b10__LoD2' else {}; zlab = np.zeros(N, 'i1')
    for k, (w, rows_) in enumerate(zones.items(), 1): zlab[rows_] = k
    per_view = []; S0dir = Path('/s0/fork_inputs/s61')/site/'maps'
    for nm, mi in sorted(index.items()):
        with np.load(md/mi['file']) as z: own = z['owner']; dep = z['depth']; wt = z['weight']
        mvs = np.load(S0dir/'mvs'/f'{nm}.npy'); conf = np.load(S0dir/'conf'/f'{nm}.npy'); assert mvs.shape == own.shape
        k = own >= 0; o = own[k]; td = dep[k].astype('f8'); md_ = mvs[k].astype('f8'); have = np.isfinite(md_) & (md_ > 0); cp = have & (conf[k] > 0)
        assert np.isfinite(td).all() and (td > 0).all(), ('target depth not finite', nm)
        diff = np.where(have, md_-td, np.nan); cl = np.where(~have, 3, np.where(diff < -1.0, 0, np.where(diff > 1.0, 2, 1)))
        for j, nmc in enumerate(CLS): cnt[nmc] += np.bincount(o[cl == j], minlength=N)
        cnt['target'] += np.bincount(o, minlength=N); cnt['conf_pass'] += np.bincount(o[cp], minlength=N)
        cnt['behind_conf_pass'] += np.bincount(o[cp & (cl == 2)], minlength=N); cnt['front_conf_pass'] += np.bincount(o[cp & (cl == 0)], minlength=N)
        wsum += np.bincount(o, weights=wt[k].astype('f8'), minlength=N); vcount += np.bincount(o, minlength=N) > 0
        row = dict(view=nm, target_pixels=int(k.sum()))
        if zones:
            for kk, w in enumerate(zones, 1): zm = zlab[o] == kk; row[f'{w}_pixels'] = int(zm.sum()); row[f'{w}_front'] = int((zm & (cl == 0)).sum())
        per_view.append(row)
    savez(A2O/'ga'/f'{stem}__{arm}.npz', **{f'n_{k}': v for k, v in cnt.items()}, weight_sum=wsum, applied_views=vcount, area=t['area'], zone=zlab)
    dump(A2O/'ga'/f'{stem}__{arm}.json', dict(at=now(), stem=stem, arm=arm, maps=str(md), views=len(index), per_view=per_view, image_depth=str(S0dir), seconds=t0.done(), scientific_verdict=None))
    print('GA_STATS', stem, arm, len(index), int(cnt['target'].sum()), flush=True)

def tables():
    c = bcfg(); rows, place_rows, bins_rows, check_rows, view_rows = [], [], [], [], []
    edges = [(0, 0, '0'), (0, .1, '(0, 0.1]'), (.1, .3, '(0.1, 0.3]'), (.3, .6, '(0.3, 0.6]'), (.6, 1.0, '(0.6, 1]')]
    def shares(sel, z, key=None):
        tp = int(z['n_target'][sel].sum()); r = dict(target_pixels=tp)
        for k in CLS: r[f'{k}_pct'] = 100*float(z[f'n_{k}'][sel].sum())/tp if tp else None
        r['conf_pass_pct'] = 100*float(z['n_conf_pass'][sel].sum())/tp if tp else None
        r['front_after_mask_pct'] = 100*float(z['n_front_conf_pass'][sel].sum())/tp if tp else None
        r['patches_with_pixels'] = int((z['n_target'][sel] > 0).sum()); return r
    for stem in SCENES6:
        for arm in ARMS:
            f = A2O/'ga'/f'{stem}__{arm}.npz'
            if not f.exists(): continue
            z = loadz(f); N = len(z['area']); pc = patch_case(stem, N)
            rows.append(dict(stem=stem, arm=arm, case='all', **shares(np.ones(N, bool), z)))
            for cs in [-1, 0, 1, 2, 3, 4]: rows.append(dict(stem=stem, arm=arm, case=CNAME[cs], **shares(pc == cs, z)))
            if stem == 'B0_b10__LoD2':
                for k, nm in [(1, 'south_wall'), (2, 'long_wall'), (0, 'other')]:
                    place_rows.append(dict(stem=stem, arm=arm, place=nm, case='all', **shares(z['zone'] == k, z)))
                    for cs in [-1, 0, 1, 2, 3, 4]:
                        s = (z['zone'] == k) & (pc == cs)
                        if s.any(): place_rows.append(dict(stem=stem, arm=arm, place=nm, case=CNAME[cs], **shares(s, z)))
                vj = json.loads((A2O/'ga'/f'{stem}__{arm}.json').read_text())['per_view']
                for v in vj: view_rows.append(dict(arm=arm, **v))
            ra = loadz(A1O/'ra'/f'{stem}__{arm}.npz', ['patch_valid', 'patch_trained_n', 'patch_trained_far', 'patch_target_n', 'patch_target_far', 'patch_applied_views', 'patch_supervision'])
            has = z['n_target'] > 0; fr = np.where(has, z['n_front']/np.maximum(z['n_target'], 1), np.nan)
            for lo, hi, lab in edges:
                s = has & ((fr == 0) if hi == 0 else ((fr > lo) & (fr <= hi)))
                tn, tf, gn, gf = [int(ra[k][s].sum()) for k in ['patch_trained_n', 'patch_trained_far', 'patch_target_n', 'patch_target_far']]
                bins_rows.append(dict(stem=stem, arm=arm, front_share_bin=lab, patches=int(s.sum()), target_pixels=int(z['n_target'][s].sum()), trained_result_points=tn, trained_wrong_pct=100*tf/tn if tn else None,
                                      target_result_points=gn, target_wrong_pct=100*gf/gn if gn else None))
            bins_rows.append(dict(stem=stem, arm=arm, front_share_bin='화소 없음(제외)', patches=int((~has).sum())))
            sup = z['weight_sum']/np.maximum(z['area'], 1e-9)
            check_rows.append(dict(stem=stem, arm=arm, patches=N, applied_views_equal=bool(np.array_equal(z['applied_views'].astype(int), ra['patch_applied_views'].astype(int))),
                                   supervision_max_abs_diff=float(np.nanmax(np.abs(sup-ra['patch_supervision'].astype('f8')))), supervision_rel_diff_p99=float(np.nanpercentile(np.abs(sup-ra['patch_supervision'])/np.maximum(np.abs(sup), 1e-9), 99))))
    btable('ga_pixel_classes', rows); btable('ga_pixel_classes_B0_LoD2_places', place_rows); btable('ga_patch_front_bins', bins_rows); btable('ga_patch_value_check', check_rows); btable('ga_B0_LoD2_views_wall_pixels', view_rows)
    print('GA_TABLES', len(rows), len(place_rows), len(bins_rows), flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'stats': stats(a[1], a[2])
    else: tables()
