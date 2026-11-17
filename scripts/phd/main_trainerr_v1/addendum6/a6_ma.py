"""Work ma (order 7): patches without seeds and invalid patches. CPU, reads stored inputs only.
Seed rule (read, not changed): scripts/phd/main_finaltrain_v1/prepare_inputs.py 20-46 - one prior seed per prior SfM point (sparse/0 origin == 1) that has a seat (seat >= 0),
is located on a target row (src/phd/prior_propagation_v6/locations.locate) and whose row has surface_exists; the seed sits at the row's target anchor with the row's normal.
Valid patch rule: scripts/phd/main_trainerr_v1/common.py valid_patch (region >= 0, finite target / normal / sigma, sigma > 0).
  tables : tables/ma_seedless (per scene, valid patches with 0 seeds by judgment / area / prior points n / image depth / surface_exists),
           ma_invalid (lost and other points on an invalid patch: which condition), ma_seedless_30000 (bound Gaussians at FINALTRAIN 30000 on seedless patches and where they came from),
           ma_points (four groups: share of points on seedless / invalid patches)"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum6')
from a6_common import *
PTS = A6O/'points'
BORN_KO6 = ['사전 정보 씨앗', '사전 정보 씨앗의 자식', '배경 씨앗', '배경 씨앗의 자식']

def tables():
    c = cfg6(); seedless, invalid, s30, prow = [], [], [], []
    for stem in c['points']['scenes']:
        t = loadz(targets_of(stem, 'own')); N = len(t['area']); vp = valid_patch(t)
        sd = loadz(FT/'stage1'/stem/'seeds.npz', ['patch', 'origin']); sc = np.bincount(sd['patch'][(sd['origin'] == 1) & (sd['patch'] >= 0)], minlength=N)
        img = np.isfinite(t['mvs_mean_m']); n = t['n']; area = t['area']; jr = t['judge_region']; se = t['surface_exists'].astype(bool)
        zero = vp & (sc == 0)
        base = dict(stem=stem, patches=N, valid=int(vp.sum()), valid_seedless=int(zero.sum()), valid_seedless_pct=pct(zero[vp]),
                    check_seed_patches_have_n_gt0_pct=pct(n[vp & (sc > 0)] > 0), check_seed_patches_surface_exists_pct=pct(se[vp & (sc > 0)]))
        seedless.append(dict(base, split='전체'))
        qa = np.quantile(area[vp], [.25, .5, .75])
        splits = [(f'판정: {JNAME.get(int(k), k)}', jr == k) for k in np.unique(jr[vp])] + \
                 [(f'넓이: {lab}', m) for lab, m in [(f'< {qa[0]:.3g} m²', area < qa[0]), (f'{qa[0]:.3g}–{qa[1]:.3g} m²', (area >= qa[0]) & (area < qa[1])), (f'{qa[1]:.3g}–{qa[2]:.3g} m²', (area >= qa[1]) & (area < qa[2])), (f'≥ {qa[2]:.3g} m²', area >= qa[2])]] + \
                 [(f'사전 정보 점 수 n: {lab}', m) for lab, m in [('0', n == 0), ('1–2', (n >= 1) & (n <= 2)), ('3–9', (n >= 3) & (n <= 9)), ('≥ 10', n >= 10)]] + \
                 [('영상 깊이 있음', img), ('영상 깊이 없음', ~img), ('surface_exists 참', se), ('surface_exists 거짓', ~se)]
        for lab, m in splits:
            mm = vp & m
            if mm.any(): seedless.append(dict(stem=stem, split=lab, valid=int(mm.sum()), valid_seedless=int((zero & m).sum()), valid_seedless_pct=pct(zero[mm]), share_of_seedless_pct=100*float((zero & m).sum())/max(1, int(zero.sum()))))
        # points
        z = loadz(O/'addendum2/points'/f'ra_{stem}__own.npz', ['patch_raw', 'patch_row', 'group'])
        pr = z['patch_raw']; ok = pr >= 0; g = z['group']
        cond = {'열 조각 없음(patch_raw < 0)': ~ok}
        q = np.clip(pr, 0, N-1)
        cond['region < 0'] = ok & (t['region'][q] < 0); cond['목표점 유한 아님'] = ok & ~np.isfinite(t['target'][q]).all(1); cond['법선 유한 아님'] = ok & ~np.isfinite(t['normal'][q]).all(1)
        cond['σ 유한 아님 또는 ≤ 0'] = ok & ~(np.isfinite(t['sigma'][q]) & (t['sigma'][q] > 0))
        inv = z['patch_row'] < 0
        for gk in range(4):
            m = g == gk; nm = int(m.sum())
            r = dict(stem=stem, group=GROUP_KO[gk], n=nm, invalid_patch_pct=pct(inv[m]), seedless_valid_patch_pct=pct((~inv[m]) & (sc[q[m]] == 0)))
            on_sl = m & ~inv & (sc[q] == 0); r['on_seedless_patch'] = int(on_sl.sum())
            prow.append(r)
            for lab, cm in cond.items():
                invalid.append(dict(stem=stem, group=GROUP_KO[gk], n_invalid=int((m & inv).sum()), condition=lab, points=int((m & inv & cm).sum()), share_of_invalid_pct=100*float((m & inv & cm).sum())/max(1, int((m & inv).sum())),
                                    rule='conditions may overlap'))
        # 30000 on seedless patches
        S = Snap(stem, 'own'); bound = (S.tag == 1); slp = np.flatnonzero(zero); has = np.isin(S.patch, slp) & bound
        cnt = np.bincount(S.patch[has], minlength=N)[slp] if len(slp) else np.zeros(0)
        r = dict(stem=stem, seedless_valid_patches=int(len(slp)), with_bound_30000_pct=pct(cnt > 0) if len(slp) else None, bound_gaussians=int(has.sum()))
        for k, nm in enumerate(BORN_KO6): r[f'from_{nm}_pct'] = pct(S.born[has] == k) if has.any() else None
        ptsl = (~inv) & (sc[q] == 0)
        for gk in range(4):
            m = ptsl & (g == gk); r[f'{GROUP_KO[gk]}_on_seedless_patch_with_bound_pct'] = pct(np.isin(z['patch_row'][m], np.unique(S.patch[has]))) if m.any() else None
        s30.append(r); print('MA6', stem, int(zero.sum()), flush=True)
    table6('ma_seedless', seedless); table6('ma_invalid', invalid); table6('ma_seedless_30000', s30); table6('ma_points', prow)

if __name__ == '__main__': tables()
