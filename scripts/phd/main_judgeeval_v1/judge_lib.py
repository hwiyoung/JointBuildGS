"""새 판단 구조(5절)의 판정 함수. 참값을 읽지 않는다. 재료: step1(원통 값), step2(화소 표), step3(점마다 일관성).
① 결과: 0 같다, 1 다르다, 2 값 없음 · ② 결과: 0 사전 정보, 1 ③으로 · ③ 결과: 0 사전 정보, 1 영상 · 판정: 0 두 자료, 1 영상, 2 사전 정보."""
import numpy as np
SAME, DIFF, NONE = 0, 1, 2
J_BOTH, J_IMG, J_PRI = 0, 1, 2
JN = ['두 자료', '영상', '사전 정보']
def step1(S, prior, kind, h=2, rep='mean', size=False, Lver='pm', two_pass=False, size_thr=None):
    """S = step1 npz dict. h = 반길이 후보 차례(0,1,2 = 지붕 3/5/10, 벽 2/3/5 m). two_pass: 짧은(0) 길이로 먼저, 값 없는 패치만 긴(2) 길이로."""
    if two_pass:
        a = step1(S, prior, kind, 0, rep, size, Lver, False, size_thr); b = step1(S, prior, kind, 2, rep, size, Lver, False, size_thr); r = a.copy(); m = a == NONE; r[m] = b[m]; return r
    n = S['n'][:, h]; d = (S['d_mean'] if rep == 'mean' else S['d_med'])[:, h]
    if Lver == 'pm': L = S['L_m']
    else:
        sP2 = S['sigma_P']**2 if prior == 'LoD2' else np.where(S['als_n'] >= 2, S['als_sd']**2/np.maximum(S['als_n'], 1), np.nan)
        with np.errstate(invalid='ignore', divide='ignore'): L = 1.96*(np.sqrt(S['sd'][:, h]**2/np.maximum(n, 1) + sP2) + np.abs(S['r_m']))
    ok = (n >= 4) & np.isfinite(L) & np.isfinite(d)
    r = np.full(len(n), NONE, np.int8); r[ok] = np.where(np.abs(d[ok]) <= L[ok], SAME, DIFF)
    if size:
        thr = np.where(kind == 2, size_thr['LoD2_wall'], size_thr[f'{prior}_roof'])
        r[ok & (np.abs(d) < thr)] = SAME
    return r
def step2(C, rule='pixel', delta=1):
    """C = step2 counts (N, 20). rule: pixel(화소 표 안정도) / centre(중심 한 점 안정도, 영상 수) / one(지나감 영상 한 장 이상, 중심 판) / two(두 장 이상)."""
    k = 0 if delta == 1 else 1
    if rule == 'pixel': p, b, a = C[:, 6*k+1], C[:, 6*k+2], C[:, 6*k+3]; go = (p > b + a) & (p + b + a > 0)
    else:
        p, b, a = C[:, 12+4*k+1], C[:, 12+4*k+2], C[:, 12+4*k+3]
        go = {'centre': (p > b + a) & (p + b + a > 0), 'one': p >= 1, 'two': p >= 2}[rule]
    return np.where(np.nan_to_num(go).astype(bool), 1, 0).astype(np.int8)
def step3(cons, total, rule='main', a2=None):
    """cons = 패치의 일관된 점 수(COLMAP), total = 패치 영상 점 수, a2 = A2 로 일관된 점 수."""
    if rule == 'main': v = cons >= 4
    elif rule == 'major': v = cons > .5*total
    else: v = a2 >= 4
    return np.where(v, 1, 0).astype(np.int8)
def assemble(r1, r2, r3_from1, r3_from2, use2=True, use3=True):
    """5.4 표. 뺀 단계 자리: ② 뺌 -> 값 없음 = 사전 정보; ③ 뺌 -> ③으로 갈 것 = 영상."""
    j = np.full(len(r1), J_PRI, np.int8); j[r1 == SAME] = J_BOTH
    d = r1 == DIFF; j[d] = np.where(r3_from1[d] == 1, J_IMG, J_PRI) if use3 else J_IMG
    if use2:
        g = (r1 == NONE) & (r2 == 1); j[g] = np.where(r3_from2[g] == 1, J_IMG, J_PRI) if use3 else J_IMG
    return j
