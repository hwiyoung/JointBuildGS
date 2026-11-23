"""Order 1 + reply 1 §2: new-judgement targets per scene (CPU). usage: df1_targets.py <stem>
- target type and score s (A2_c_ge5_frac) from the 나5 patches (campus judgement 'check + magnitude', mixture boundary, treatment W);
  heights, sigmas and the weighted-mean formula from the scene patch (FINALTRAIN targets.calculate, unchanged).
- join: scene patch -> JUDGEPROBE patch row (= 나5 csv patch_index) by centre. LoD2 exact (<= 1 mm), ALS nearest centre <= 0.125 m and same kind.
  Unjoined patches keep the FINALTRAIN judgement (and so its target) unchanged.
- type rule (MVSFILTER mf19 panel_lo, T = mixture boundary, treat W):
  lo = combo_D_judgment (= lower bound with combo-D returns); significant & not mix_large -> 0 (weighted mean).
  type: lo 0 -> 가중 평균, lo 2 -> 영상 깊이, significant & mix_large & combo_D_returned -> 되돌림, lo 4 or other lo 1 -> 결측(prior), lo 3 -> no target,
  lo 9 (미판정) -> FINALTRAIN undecided rule inside calculate().
- a type that needs the scene image height (가중 평균, 영상 깊이) where the scene patch has no finite image height / u -> 결측 (order 1 table, row 1), counted.
Writes /df/families/<fam>/targets/<stem>.npz for fam base (판 0~4), kA (κ of order 3: LoD2 .25, ALS .65), k1 (κ 1); and /df/patchinfo/<stem>.npz."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
import pandas as pd
from scipy.spatial import cKDTree

COLS = ['patch_index', 'patch_id', 'kind', 'area', 'none_significant', 'mix_large', 'combo_D_returned', 'combo_D_judgment', 'A2_c_ge5_frac', 'L_m', 'd_m', 'initial_state']

def join(t, prior):
    jp = loadz(JP/f'patch_{prior}.npz', ['centre', 'kind', 'mvs_mean_m', 'prior_height_m', 'n', 'u_M', 'd_m', 'd_for_check', 'L_m', 'geometry', 'normal'])
    tree = cKDTree(jp['centre']); dist, j = tree.query(t['centre'], workers=16)
    lim = 1e-3 if prior == 'LoD2' else .125
    ok = (dist <= lim) & (jp['kind'][j] == t['kind'])
    # one campus patch may be nearest to two scene patches (ALS): keep the closer, the other is unjoined
    order = np.argsort(dist); seen = np.zeros(len(jp['kind']), bool); uniq = np.zeros(len(j), bool)
    for i in order[ok[order]]:
        if not seen[j[i]]: seen[j[i]] = True; uniq[i] = True
    return jp, j, dist, ok & uniq, ok & ~uniq

def main(stem):
    c = cfg(False); site, prior = stem.split('__'); t0 = time.monotonic()
    ft = loadz(FT/'targets'/f'{stem}.npz'); N = len(ft['area']); calc = ft_calculate()
    jp, j, dist, joined, dup = join(ft, prior)
    csv_ = pd.read_csv(NA5/f'patches_{prior}.csv.gz', usecols=COLS); assert np.array_equal(csv_['patch_index'].values, np.arange(len(csv_)))
    row = np.where(joined, j, -1)
    J = np.full(N, -1, 'i1'); sig = np.zeros(N, bool); big = np.zeros(N, bool); ret = np.zeros(N, bool); s = np.full(N, np.nan)
    m = joined; r = row[m]
    J[m] = csv_['combo_D_judgment'].map(JN).values[r]; sig[m] = csv_['none_significant'].values[r].astype(bool)
    big[m] = (csv_['mix_large'].values[r] == 1); ret[m] = csv_['combo_D_returned'].values[r].astype(bool); s[m] = csv_['A2_c_ge5_frac'].values[r]
    assert (J[m] >= 0).all(), 'unknown 나5 judgement text'
    lo = J.copy(); lo[m & sig & ~big] = 0
    returned = m & sig & big & ret; assert (lo[returned] == 1).all()
    region = ft['judge_region'].copy()   # FINALTRAIN (post-calculate) judgement for unjoined patches: unchanged target
    region[m] = lo[m]
    # scene image height needed for 가중 평균 / 영상 깊이
    hm, um, n = ft['mvs_mean_m'], ft['u_mvs'], ft['n']
    need_m = m & np.isin(region, [0, 2]); no_scene = need_m & ~(np.isfinite(hm) & (n >= 4)); no_u0 = m & (region == 0) & ~no_scene & ~(np.isfinite(um) & (um > 0))
    region[no_scene | no_u0] = 4
    d = {k: ft[k] for k in ['centre', 'normal', 'kind', 'area', 'in_eval', 'source_index', 'patch_id', 'n', 'u_mvs', 'sigma_P_m', 'prior_height_m', 'mvs_mean_m', 'photo_code', 'reason']}
    d['judge_region'] = region.astype('i1')
    KEEP = ['h', 'sigma', 'target', 'target_height_m', 'target_sigma_m', 'region', 'judge_region', 'reason', 'undecided_before', 'sigma_replaced', 'surface_exists']
    def keep_unjoined(res):
        # reply 1 §2: unjoined patches use the FINALTRAIN target as is (calculate() alone would re-derive the undecided σ from new donors)
        res = dict(res); um_ = ~m
        for k in KEEP:
            a = np.array(res[k], copy=True); a[um_] = ft[k][um_]; res[k] = a
        return res
    base = keep_unjoined(calc(d, prior))
    # unjoined patches must keep the FINALTRAIN target exactly (reply 1 §2)
    um_ = ~m; same = np.array_equal(base['surface_exists'][um_], ft['surface_exists'][um_]) and np.allclose(base['target'][um_][base['surface_exists'][um_]], ft['target'][um_][ft['surface_exists'][um_]], atol=0, rtol=0)
    # type
    reg = base['judge_region']; act = base['surface_exists']
    typ = np.full(N, -1, 'i1'); typ[act & (reg == 0)] = 0; typ[act & (reg == 2)] = 1; typ[act & np.isin(reg, [1, 4])] = 3; typ[act & returned & (reg == 1)] = 2
    ft_typ = np.full(N, -1, 'i1'); fa = ft['surface_exists']; fr = ft['judge_region']; ft_typ[fa & (fr == 0)] = 0; ft_typ[fa & (fr == 2)] = 1; ft_typ[fa & np.isin(fr, [1, 4])] = 3
    split0 = act & sig & big & m          # switch 라 target patches: 영상 깊이 or 되돌림 among significant & large
    split = split0 & np.isin(typ, [1, 2]) & np.isfinite(hm) & (n >= 4) & np.isfinite(ft['sigma_P_m']) & (ft['sigma_P_m'] > 0) & np.isfinite(ft['prior_height_m'])   # no scene image height / prior σ (became 결측 above, or 되돌림 without one): no second surface
    umed = float(base['correction_u_median']) if np.isfinite(base['correction_u_median']) else float(np.median(um[(reg == 2) & np.isfinite(um) & (um > 0)]))
    u_fill = split & ~(np.isfinite(um) & (um > 0))   # image face without scene u: u = median of the scene's 보정 donors (FINALTRAIN replacement rule)
    fams = {'base': None}; kap = c['kappa'][prior]; fams['kA'] = kap; fams['k1'] = 1.0
    out = {}
    for fam, kappa in fams.items():
        if kappa is None: res = base; cc = np.full(N, np.nan)
        else:
            cc = np.full(N, np.nan); cc[split] = kappa*(1 - s[split]); assert np.isfinite(cc[split]).all()
            r2 = d['judge_region'].copy(); r2[split & (cc >= .5)] = 1; r2[split & (cc < .5)] = 2; u2 = d['u_mvs'].copy(); u2[u_fill] = umed
            d2 = dict(d, judge_region=r2.astype('i1'), u_mvs=u2)
            res = keep_unjoined(calc(d2, prior))
            if not np.array_equal(res['surface_exists'], base['surface_exists']):
                bad = res['surface_exists'] != base['surface_exists']
                print('BAD', fam, int(bad.sum()), 'r2', np.unique(r2[bad], return_counts=True), 'typ', np.unique(typ[bad], return_counts=True), 'sP finite', int(np.isfinite(d['sigma_P_m'][bad]).sum()),
                      'hp finite', int(np.isfinite(d['prior_height_m'][bad]).sum()), 'res sig', res['sigma'][bad][:5], 'res h', res['h'][bad][:5], flush=True)
                raise AssertionError('κ family changes active patches')
            res = dict(res, sigma_ref=base['sigma_ref'])   # order 2.4: other patches unchanged -> keep the scene's base σ_ref
        tf = O/'families'/fam/'targets'/f'{stem}.npz'; result = {**d, **res, 'any_replaced': res['sigma_replaced']}
        savez(tf, **result); out[fam] = dict(sha256=sha(tf), sigma_ref=float(res['sigma_ref']), kappa=kappa,
            split_patches_prior_face=int((split & (cc >= .5)).sum()) if kappa else None, split_patches_image_face=int((split & (cc < .5)).sum()) if kappa else None)
    # campus vs scene image height (reply 1 §2)
    camp_h = np.full(N, np.nan); camp_h[m] = jp['mvs_mean_m'][row[m]]
    roof, wall = tau_of(site, prior); tau = np.where(ft['kind'] == 2, wall if prior == 'LoD2' else roof, roof)
    # re-judge significance and magnitude with scene heights (photo check not redone)
    dfc = np.full(N, np.nan); dfc[m] = jp['d_for_check'][row[m]]; dcm = np.full(N, np.nan); dcm[m] = jp['d_m'][row[m]]; L = np.full(N, np.nan); L[m] = jp['L_m'][row[m]]
    dscene = hm - ft['prior_height_m']; dcampus = jp['mvs_mean_m'][np.maximum(row, 0)] - jp['prior_height_m'][np.maximum(row, 0)]
    off_check = dfc - dcampus   # d_for_check - (campus mvs - campus prior): carried over as is
    savez(O/'patchinfo'/f'{stem}.npz', joined=m, dup_unjoined=dup, row=row, join_dist=dist, judge_lo=lo, region=reg, type=typ, ft_type=ft_typ, returned=returned,
          significant=sig, mix_large=big, split=split, s=s, u_filled=u_fill, c_kA=np.where(split, fams['kA']*(1 - s), np.nan), c_k1=np.where(split, 1 - s, np.nan),
          campus_mvs_h=camp_h, scene_mvs_h=hm, scene_prior_h=ft['prior_height_m'], campus_prior_h=np.where(m, jp['prior_height_m'][np.maximum(row, 0)], np.nan),
          d_for_check=dfc, d_m_campus=dcm, L_m=L, d_scene=dscene, offset_check=off_check, campus_n=np.where(m, jp['n'][np.maximum(row, 0)], -1),
          campus_geometry=np.where(m, jp['geometry'][np.maximum(row, 0)], -1), tau=tau, no_scene_height=no_scene, no_scene_u=no_u0, area=ft['area'], kind=ft['kind'], in_eval=ft['in_eval'])
    A = ft['area']
    rec = dict(at=now(), stem=stem, title=TITLE, patches=N, joined=int(m.sum()), joined_area_m2=float(A[m].sum()), unjoined=int((~m).sum()), unjoined_area_m2=float(A[~m].sum()),
               unjoined_in_eval=int((~m & ft['in_eval']).sum()), unjoined_in_eval_area_m2=float(A[~m & ft['in_eval']].sum()), dup_unjoined=int(dup.sum()),
               join_rule='LoD2 exact centre <= 1 mm; ALS nearest centre <= 0.125 m, same kind, one scene patch per campus patch (closest)',
               join_dist_m_q50_q95_max=np.quantile(dist[m], [.5, .95, 1]).tolist() if m.any() else None,
               unjoined_keep_finaltrain_target=bool(same), no_scene_image_height_to_missing=dict(patches=int(no_scene.sum()), area_m2=float(A[no_scene].sum())),
               no_scene_u_to_missing=dict(patches=int(no_u0.sum()), area_m2=float(A[no_u0].sum())),
               types={TYPE_KO[k]: dict(patches=int((typ == k).sum()), area_m2=float(A[typ == k].sum())) for k in [0, 1, 2, 3, -1]},
               ft_types={TYPE_KO[k]: dict(patches=int((ft_typ == k).sum()), area_m2=float(A[ft_typ == k].sum())) for k in [0, 1, 3, -1]},
               split_patches=int(split.sum()), split_area_m2=float(A[split].sum()), split_u_filled=dict(patches=int(u_fill.sum()), u_m=umed), split_excluded_no_scene_height=dict(patches=int((split0 & ~split).sum()), area_m2=float(A[split0 & ~split].sum())), families=out, seconds=time.monotonic()-t0, scientific_verdict=None)
    dump(O/'families/targets_receipt'/f'{stem}.json', rec); print('TARGETS', stem, json.dumps({k: rec[k] for k in ['joined', 'unjoined_in_eval', 'types', 'split_patches']}, ensure_ascii=False), flush=True)

if __name__ == '__main__': main(sys.argv[1])
