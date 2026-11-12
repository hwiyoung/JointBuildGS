"""판정 규칙 (JUDGEAPPLY-v1 judgments.py 3절 + FINALTRAIN-v1 targets.py 11/4 규칙)을 배열 함수로 옮김. 참값 쓰지 않음.
영역: 0 일치, 1 사전정보 사용, 2 영상 깊이 사용, 3 제거, 4 결측, 9 미판정. 근거: 0 사진 지지, 1 사진 반박, 2 기본 판정, 9 해당 없음.
광도 결과: 0 지지, 1 반박, 2 둘 다 낮음, 3 둘 다 높음, 4 MVS 면 없음, 5 조각 부족, 6 무늬 없음, 7 사진 부족, 9 셈 안 함."""
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

VARIANTS = ['prior_only', 'image_only', 'geometry_only', 'photo_only', 'method', 'alt_na', 'alt_da', 'oracle']


def quantile(x, w, q):
    """JUDGEAPPLY judgments.py:5-9 그대로."""
    mask = np.isfinite(x) & np.isfinite(w) & (w > 0); x = x[mask]; w = w[mask]
    if not len(x): return np.nan
    ix = np.argsort(x, kind='stable'); x = x[ix]; w = w[ix]
    return float(x[min(np.searchsorted(np.cumsum(w), q*w.sum(), side='left'), len(x)-1)])


def threshold(s_P, area, pool, seed, cap=5000):
    """t = 넓이 가중 아래 5 % (한계 안 핵심점만 가진 사진 점), 5000개 넘으면 무작위 5000개."""
    pool = np.flatnonzero(pool); chosen = pool
    if len(pool) > cap: chosen = np.random.default_rng(seed).choice(pool, cap, replace=False)
    x = s_P[chosen]; w = area[chosen]
    return quantile(x, w, .05), quantile(x, w, .10), chosen


def photo_code(s_P, s_M, t, mvs_available, texture, n_selected):
    """JUDGEAPPLY judgments.py:26-30 의 차례 (7 > 6 > 4 > 5 > 0-3). texture (N,2), n_selected (N,2)."""
    N = len(s_P); code = np.full(N, 9, np.int8); t = np.broadcast_to(np.asarray(t, float), (N,))
    ok = np.isfinite(t)
    with np.errstate(invalid='ignore'):
        p, m = s_P, s_M
        code[ok & (p < t) & (m >= t)] = 1; code[ok & (p >= t) & (m < t)] = 0; code[ok & (p < t) & (m < t)] = 2; code[ok & (p >= t) & (m >= t)] = 3
    code[ok & ~(np.isfinite(p) & np.isfinite(m))] = 5
    code[~mvs_available] = 4
    with np.errstate(invalid='ignore'):
        code[(texture < 5).all(1)] = 6
    code[(n_selected < 3).any(1)] = 7
    return code


def geometry_code(n, d, L):
    g = np.full(len(n), 9, np.int8); valid = (n >= 4) & np.isfinite(d) & np.isfinite(L)
    g[(n >= 0) & (n < 4)] = 2
    with np.errstate(invalid='ignore'):
        g[valid & (np.abs(d) <= L)] = 0; g[valid & (np.abs(d) > L)] = 1
    return g


def decide(prior, n, geom, h_P, h_M, normal_ok, u, pcode, free):
    """반환: region[8,N], reason[8,N] (VARIANTS 차례; alt_da/oracle 은 따로 채움, 처음엔 method 복사)."""
    N = len(n); reg = np.full((len(VARIANTS), N), 9, np.int8); why = np.full((len(VARIANTS), N), 9, np.int8)
    default = 1 if prior == 'ALS' else 2
    valid = np.isfinite(h_P) & normal_ok
    missing = valid & (n >= 0) & (n < 4); present = valid & (n >= 4) & np.isfinite(h_M)
    inside = valid & (geom == 0); outside = valid & (geom == 1)
    nou = present & (geom == 9) & ~np.isfinite(u)          # 11/4 규칙 (FINALTRAIN targets.py:11-14)
    V = {v: i for i, v in enumerate(VARIANTS)}
    for v in ['prior_only', 'image_only', 'geometry_only', 'photo_only', 'method']: reg[V[v], missing] = 4
    for v in ['image_only', 'geometry_only', 'photo_only', 'method']: reg[V[v], missing & free] = 3
    reg[V['prior_only'], present] = 1; reg[V['image_only'], present] = 2
    g = V['geometry_only']; reg[g, inside] = 0; reg[g, outside | nou] = default; why[g, outside | nou] = 2
    for v, mask in [('photo_only', present), ('method', outside | nou)]:
        j = V[v]; reg[j, mask] = default; why[j, mask] = 2
        reg[j, mask & (pcode == 0)] = 1; why[j, mask & (pcode == 0)] = 0
        reg[j, mask & (pcode == 1)] = 2; why[j, mask & (pcode == 1)] = 1
    reg[V['method'], inside] = 0
    m = V['method']; a = V['alt_na']; reg[a] = reg[m]; why[a] = why[m]
    opp = 2 if prior == 'ALS' else 1; dflt = why[m] == 2; reg[a, dflt] = opp
    reg[V['alt_da']] = reg[m]; why[V['alt_da']] = why[m]; reg[V['oracle']] = reg[m]; why[V['oracle']] = why[m]
    return reg, why


def alt_da(prior, region, reason, centre, area, group):
    """GTJUDGE add2_targets.py:13-28 (LoD2) 이웃 따르기, ALS 는 방향을 거꾸로. group = 건물|면 문자열. 바꿀 패치 bool 과 덩어리 기록."""
    if prior == 'LoD2': editable = (region == 2) & (reason == 2)
    else: editable = (region == 1) & (reason == 2)
    change = np.zeros(len(region), bool); comps = []
    order = np.argsort(group, kind='stable'); gs = group[order]; cuts = np.flatnonzero(gs[1:] != gs[:-1]) + 1
    for allix in np.split(order, cuts):
        ei = allix[editable[allix]]
        if not len(ei): continue
        pts = centre[ei]; pairs = cKDTree(pts).query_pairs(.36, output_type='ndarray')
        graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(ei), len(ei)))
        count, labels = connected_components(graph, directed=False); tree = cKDTree(centre[allix])
        for c in range(count):
            members = ei[labels == c]; near = tree.query_ball_point(centre[members], .36)
            boundary = np.setdiff1d(allix[np.unique(np.concatenate([np.asarray(x, int) for x in near]))], members)
            reg = region[boundary]; why = reason[boundary]
            prior_area = float(area[boundary[((reg == 1) & (why == 0)) | (reg == 4)]].sum())
            image_area = float(area[boundary[(reg == 2) & (why == 1)]].sum())
            choose = prior_area > image_area if prior == 'LoD2' else image_area > prior_area
            change[members] = choose
            comps.append((str(group[members[0]]), len(members), float(area[members].sum()), prior_area, image_area, bool(choose)))
    return change, comps


def oracle(region_method, case_ids, owners, u, h_M):
    """GTJUDGE majority.decide (참값 경우, 지금 정의 0..4)."""
    original = np.asarray(region_method); result = original.copy(); assigned = np.zeros(len(original), bool)
    counts = np.zeros((len(original), 5), np.int64)
    good = (owners >= 0) & (owners < len(original)) & (case_ids >= 0) & (case_ids <= 4)
    np.add.at(counts, (owners[good], case_ids[good]), 1)
    expected = {0: 0, 1: 2, 2: 1, 4: 4}
    has = counts.sum(1) > 0; mx = counts.max(1); nwin = (counts == mx[:, None]).sum(1)
    tie = has & (nwin > 1) & (counts[:, 0] == mx); result[tie] = 0; assigned[tie] = True
    single = has & (nwin == 1); win = counts.argmax(1)
    for c, r in expected.items():
        m = single & (win == c); result[m] = r; assigned[m] = True
    mu = assigned & (result == 0) & ~np.isfinite(u); result[mu] = 1
    mh = assigned & (result == 2) & ~np.isfinite(h_M); result[mh] = original[mh]
    return result, counts


def target_height(region, h_P, h_M, u, sigma_P, sigma_W):
    """JUDGEAPPLY judgments.py:59-63 (r 더하지 않음). 일치: 정밀도 가중 평균."""
    vm = u**2 + sigma_W**2; vp = sigma_P**2
    with np.errstate(divide='ignore', invalid='ignore'):
        mixed = (h_M*vp + h_P*vm)/(vp + vm)
    h = np.full(len(region), np.nan)
    h[region == 0] = mixed[region == 0]
    keep = np.isin(region, [1, 4]); h[keep] = h_P[keep]
    h[region == 2] = h_M[region == 2]
    return h
