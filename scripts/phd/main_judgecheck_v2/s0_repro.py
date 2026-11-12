"""단계 0-5: 재현 확인. 세 실험 지역에서 지금 값(JUDGEAPPLY 고리·r·t·σ_W 2.14 cm)으로 판정을 다시 내려
JUDGEAPPLY 핵심점 + 11/4 규칙(= FINALTRAIN targets judge_region)과 넓이로 비교한다. 참값 읽지 않음.
확인하는 것: 한계 L 식, 기하 결과, t 셈(씨앗 20261103), 광도 결과 차례, 판정 규칙과 11/4 규칙 (jc2_judge)."""
from common import *
import jc2_judge as J
def main():
    cfg(); rows = []; cal = json.loads((JA/'calibration.json').read_text()); sw = cal['sigma_W_m']
    for site in SITES:
        for prior in ['LoD2', 'ALS']:
            c = loadz(JA/'core_points'/f'{site}__{prior}.npz'); p = loadz(JA/'photo_points'/f'{site}__{prior}.npz'); f = loadz(FT/'targets'/f'{site}__{prior}.npz')
            L = 1.96*(np.sqrt(c['u_mvs']**2 + c['sigma_P_m']**2 + sw**2) + np.abs(c['r_m']))
            dL = np.nanmax(np.abs(L - c['L_m'])); geom = J.geometry_code(c['n'], c['d_m'], L)
            t_new = {}; t_old = {}; tcode = np.full(len(p['s_P']), 9, np.int8)
            for kind in ([1, 2] if prior == 'LoD2' else [1]):
                part = p['kind'] == kind; pool = p['all_within'] & part
                t, t10, ch = J.threshold(p['s_P'], p['area'], pool, 20261103); t_new[kind] = t; t_old[kind] = float(np.unique(p['t'][part])[0])
            tt = np.array([t_new[k] for k in p['kind']])
            pc = J.photo_code(p['s_P'], p['s_M'], tt, p['available'][:, 1], p['texture'], p['selected_image_count'])
            allc = np.full(int(p['point_index'].max()) + 1 if len(p['point_index']) else 1, 9, np.int8); allc[p['point_index']] = pc
            core_pc = np.where(c['photo_point_index'] < len(allc), allc[np.clip(c['photo_point_index'], 0, len(allc)-1)], 9)
            free = np.where(c['kind'] == 1, c['free10'], c['free5'])
            reg, why = J.decide(prior, c['n'], geom, c['prior_height_m'], c['mvs_mean_m'], np.isfinite(c['normal']).all(1), c['u_mvs'], core_pc, free)
            m = reg[J.VARIANTS.index('method')]
            pos = {s: i for i, s in enumerate(f['patch_id'])}; fi = np.array([pos[s] for s in c['patch_id']]); ref = f['judge_region'][fi]
            a = c['area']; same = m == ref
            diff = {f'{int(x)}->{int(y)}': float(a[(ref == x) & (m == y)].sum()) for x in np.unique(ref) for y in np.unique(m) if x != y and ((ref == x) & (m == y)).any()}
            rows.append(dict(site=site, prior=prior, patches=len(m), area_m2=float(a.sum()), same_area_share=float(a[same].sum()/a.sum()), differing_area_m2=float(a[~same].sum()), differing_by_transition=diff,
                             L_max_abs_diff_m=float(dL), geometry_equal_share=float(np.mean(geom == c['geometry'])), t_recomputed=t_new, t_JUDGEAPPLY=t_old,
                             photo_code_equal_share=float(np.mean(pc == p['photo_code'])), core_photo_code_equal_share=float(np.mean(core_pc == c['photo_code'])),
                             method_vs_JA_region5_share=float(np.mean(m == c['region'][5])), sigma_W_m=sw))
    ok = all(r['same_area_share'] > .99 for r in rows)
    dump(O/'stage0/reproduction.json', dict(at=now(), status='PASS_99' if ok else 'BELOW_99', rows=rows, current_values=dict(sigma_W_m=sw, ring='B0 1.0 m, B173nb/R1 1.5 m (JUDGEAPPLY stage0 mvs_a_u)', r='JUDGEAPPLY calibration.json', t='recomputed with seed 20261103'), GT_read=False, scientific_verdict=None))
    for r in rows: print(r['site'], r['prior'], round(100*r['same_area_share'], 4), r['differing_by_transition'], 'dL', r['L_max_abs_diff_m'], 'geom', r['geometry_equal_share'], 't', r['t_recomputed'], r['t_JUDGEAPPLY'], 'pc', r['photo_code_equal_share'], r['core_photo_code_equal_share'])
if __name__ == '__main__': main()
