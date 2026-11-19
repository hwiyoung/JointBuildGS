"""검증: js1 코드를 쓰지 않고 원자료(JP 패치, JC 참값 점, 덧붙임 2 처음 상태)에서 정의와 핵심 값을 따로 다시 센다.
격자 안쪽 칸은 무작위로 실제로 바꿔 본 값(여러 번)과 기댓값 식을 견준다. 사용: vf1_verify.py <prior>"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
PH = Path('/art/phase-payloads/phd'); JC = PH/'main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2'; JP = PH/'main_judgeprobe_v1/PHD-MAIN-JUDGEPROBE-v1'
JABL = PH/'main_judgeabl_v1/PHD-MAIN-JUDGEABL-v1'; D = Path('/docs'); O = Path('/out')
CASES = [0, 1, 2, 4]; CN = ['두 자료 모두 유효', '사전정보 오류', '영상 깊이 오류', '영상 깊이 결측']
def lz(p, k):
    with np.load(p) as z: return {x: z[x] for x in k}
def dist(x, g, c, n, h, wall):   # 참값 점 법선을 따라 목표 면(c + h n, 법선 n)까지 거리; 벽 5 m, 지붕 10 m 넘으면 없음
    p0 = c + h[:, None]*n; den = (g*n).sum(1)
    with np.errstate(all='ignore'): t = ((p0 - x)*n).sum(1)/den
    t[~np.isfinite(h) | (np.abs(den) < 1e-9) | (np.abs(t) > np.where(wall, 5., 10.))] = np.nan
    return t
def main(prior):
    P = lz(JP/f'patch_{prior}.npz', ['kind', 'area', 'n', 'geometry', 'L_m', 'prior_height_m', 'mvs_mean_m', 'normal', 'centre', 'target_h', 'j_region', 'region', 'place'])
    mi = 4; A = P['area']; N = len(A); hP = P['prior_height_m']; hM = P['mvs_mean_m']; hb = P['target_h'][:, mi]
    valid = np.isfinite(hP) & np.isfinite(P['normal']).all(1)
    g1 = P['geometry'] == 1
    R = dict(prior=prior, geom1=int(g1.sum()), geom1_but_n_lt4=int((g1 & (P['n'] < 4)).sum()), geom1_not_valid=int((g1 & ~valid).sum()), geom1_no_mvs=int((g1 & ~np.isfinite(hM)).sum()))
    sig = valid & (P['n'] >= 4) & g1
    pc = np.load(JABL/'addendum2'/f'patch_case_{prior}.npz')['pc'].astype(int)
    # 처음 상태를 majority_counts 에서 따로 다시 냄
    cnt = np.load(JC/'analysis'/f'patches_{prior}.npz')['majority_counts']; tot = cnt.sum(1); mx = cnt.max(1); nw = (cnt == mx[:, None]).sum(1)
    pc2 = np.full(N, -2); s1 = (tot > 0) & (nw == 1); pc2[s1] = cnt.argmax(1)[s1]; pc2[(tot > 0) & (nw > 1) & (cnt[:, 0] == mx)] = 0; pc2[tot == 0] = -9; pc2[(tot > 0) & (tot < 3)] = -3
    R['patch_state_recomputed_equal_pct'] = 100*float(np.mean(pc2 == pc))
    E = sig & (pc == 2); Oth = sig & ~E
    rows = []
    surf = [('지붕', [1]), ('벽', [2]), ('모두', [1, 2])] if prior == 'LoD2' else [('지붕', [1])]
    for sn, kk in surf:
        km = np.isin(P['kind'], kk) & sig; st = km & np.isin(pc, [0, 1, 2, 4, 3]); a = A[st].sum()
        rows.append(dict(prior=prior, surface=sn, what='처음 상태 넓이 % (유효/사전/영상/결측/밖)', value=' / '.join(f'{100*A[km & (pc == s)].sum()/a:.1f}' for s in [0, 1, 2, 4, 3])))
    # 참값 점
    g = lz(JC/'analysis'/f'gt_{prior}.npz', ['paired', 'gid', 'case', 'xyz', 'normal', 'gt_kind', 'tau', 'target_ok_v'])
    k = np.flatnonzero(g['paired'] & np.isin(g['case'], CASES)); gid = g['gid'][k]; cs = g['case'][k]; x = g['xyz'][k]; gn = g['normal'][k]; wall = g['gt_kind'][k] == 2; tau = g['tau'][k]
    ok_base = g['target_ok_v'][mi][k]
    def ok_with(h):     # 목표가 본 방법과 같은 패치는 저장된 채점, 바뀐 패치만 다시 셈
        ch = ~((h == hb) | (np.isnan(h) & np.isnan(hb)))
        o = ok_base.copy(); s = ch[gid]; t = dist(x[s], gn[s], P['centre'][gid[s]], P['normal'][gid[s]], h[gid[s]], wall[s]); o[s] = np.abs(t) <= tau[s]; return o
    hL = hb.copy(); hL[sig] = hM[sig]                   # 구조 하한: 차이가 유의한 패치 = 영상 깊이 평균 높이
    hU = hL.copy(); hU[E] = hP[E]                       # 구조 상한: 영상 오류 패치 = 사전 정보 높이
    hA = hL.copy(); hA[sig] = hP[sig]                   # 모두 사전정보 사용
    oL, oU, oA = ok_with(hL), ok_with(hU), ok_with(hA)
    kind_g = P['kind'][gid]
    for sn, kk in surf:
        kp = np.isin(kind_g, kk)
        for nm, o in [('구조 하한', oL), ('구조 상한', oU)]:
            rows.append(dict(prior=prior, surface=sn, what=f'{nm} 점 목표 맞음 % (네 경우 / 전체)', value=' / '.join(f'{100*o[kp & (cs == c)].mean():.2f}' for c in CASES) + f' / {100*o[kp].mean():.2f}'))
        # 닿는 범위
        for c in [1, 2]:
            m = kp & (cs == c); rows.append(dict(prior=prior, surface=sn, what=f'닿는 범위 {CN[CASES.index(c)]}: 유의 패치 안 %', value=f'{100*sig[gid[m]].mean():.2f}'))
        # 격자 칸을 실제로 무작위로 바꿔 봄: R=0.3, F=0.05 (20번), 기댓값 식과 견줌
        rng = np.random.default_rng(7); vals = []
        for _ in range(20):
            sw = (E & (rng.random(N) < .3)) | (Oth & (rng.random(N) < .05)); o = np.where(sw[gid], oA, oL); vals.append(100*o[kp].mean())
        e_lin = 100*np.where(E[gid], .7*oL + .3*oA, np.where(Oth[gid], .95*oL + .05*oA, oL))[kp].mean()
        rows.append(dict(prior=prior, surface=sn, what='격자 R=0.3 F=0.05 전체: 무작위 20번 평균±SD / 기댓값 식', value=f'{np.mean(vals):.3f}±{np.std(vals):.3f} / {e_lin:.3f}'))
    R['rows'] = rows
    (O/'verify').mkdir(exist_ok=True); (O/'verify'/f'vf1_{prior}.json').write_text(json.dumps(R, ensure_ascii=False, indent=1))
    print(json.dumps(R, ensure_ascii=False, indent=1), flush=True)
if __name__ == '__main__': main(sys.argv[1])
