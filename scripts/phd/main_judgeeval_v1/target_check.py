"""덧붙임 1 2.2·2.3: 목표가 맞았나(참값은 여기서만 읽음, 채점용).
규칙: 패치 기둥(칸 0.25 x 0.25 m, 지붕 ±10 / 벽 ±5 m, 기준 0 = 패치 중심 + 사전 정보 높이 x 법선) 안 드론 LiDAR 참값 점이 [h − τ, h + τ]에 4개 이상이면 맞음(정답과 같은 규칙, evcols colk).
h 가 없으면(NaN) 맞지 않음으로 센다.

함수
  check(prior, patch_index, H, TAU, tag) -> (N, k) bool 맞음, (N, k) 띠 안 참값 점 수. H, TAU = (N, k) 법선 거리·허용 오차(m).
  trace(prior, patch_index, judge4, ok, ...) -> 3절 꼴 경우별 표(판단 정확도·목표 정확도)의 한 열.

학습 뒤 높이를 넣는 길(이번에는 쓰지 않음):
  1. 학습 결과 면이 패치 기둥 축(패치 중심 + 사전 정보 높이 x 법선, 방향 = 법선)과 만나는 법선 거리를 패치마다 구한다(사전 정보 면 = 0, 단위 m).
  2. csv 두 열 patch_index, h 로 저장한다(패치 번호 = JUDGEPROBE patch_<prior>.npz 줄 번호, 10동 패치만).
  3. GT_STAGE=ga3 run.sh target_check.py <prior> <csv> 학습뒤   (τ = 판 4 판정의 τ_T: 사전 정보 τ_P, 영상 τ_I, 두 자료 max).
  4. tables/다/t3_after_<prior>_학습뒤.csv 에 경우(정답 넷)마다 '학습 뒤' 목표 정확도가 나온다(판 4 의 판정 넷 행렬과 같은 분모).
  5. 같은 패치의 '학습 전 목표'(판 4)와 나란히 보면 학습이 목표를 지켰는지·고쳤는지를 경우마다 본다."""
import sys
from common import *
import pandas as pd
J4 = ['두 자료', '영상', '사전 정보·영상 없음', '사전 정보·영상 틀림']
T4 = {0: 0, 1: 1, 3: 2, 2: 3}   # 정답 코드(0 두 자료, 1 영상, 2 영상 틀림, 3 영상 없음) -> 행렬 차례(두 자료, 영상, 영상 없음, 영상 틀림)
def check(prior, patch_index, H, TAU, tag):
    c = cfg(); build(); T_ = c['truth']; P = loadz(inp('patches', prior=prior), ['tile', 'kind', 'centre', 'normal', 'tangent1', 'prior_height_m', 'tiles']); tiles = list(P['tiles'])
    N, k = H.shape; ok = np.zeros((N, k), bool); cnt = np.full((N, k), np.nan); idx = np.asarray(patch_index)
    for ti in np.unique(P['tile'][idx]):
        r = np.flatnonzero(P['tile'][idx] == ti); m = idx[r]; nor = P['normal'][m]; ph = P['prior_height_m'][m]; good = np.isfinite(ph) & np.isfinite(nor).all(1)
        c0 = P['centre'][m] + np.nan_to_num(ph)[:, None]*np.nan_to_num(nor); nn = np.where(good[:, None], nor, 0.)
        Hh = np.where(P['kind'][m] == 2, T_['column']['half_length_m']['wall'], T_['column']['half_length_m']['roof']).astype(float)
        base = np.c_[c0, nn, P['tangent1'][m], np.full(len(m), T_['column']['cell_half_m'][0]), Hh]
        for s in range(0, k, KW):
            e = min(k, s + KW); trip = np.full((len(m), 3*KW), np.nan); trip[:, 0:3*(e - s):3] = 0.; trip[:, 1:3*(e - s):3] = H[r, s:e]; trip[:, 2:3*(e - s):3] = TAU[r, s:e]
            ck = run('colk', inp('truth_points', tile=tiles[ti]), np.c_[base, trip], f'tc_{tag}_{prior}_{tiles[ti]}_{s}'); bI = ck[:, 3:3+2*(e - s):2]; bI[~good] = np.nan
            cnt[r, s:e] = bI
    with np.errstate(invalid='ignore'): ok = np.isfinite(H) & (np.nan_to_num(cnt, nan=-1) >= T_['min_points'][0])
    return ok, cnt
def trace(t, j4, ok, w):
    """t = 정답 코드(0~5, -1), j4 = 판정 넷 차례(0 두 자료, 1 영상, 2 영상 없음, 3 영상 틀림, -1 그 밖), ok = 목표 맞음, w = 넓이 또는 점.
    경우(정답 넷, 행렬 차례)마다 넓이, 판단 정확도, 목표 정확도, 그리고 전체."""
    tm = np.array([T4.get(int(x), -1) for x in t]); out = []
    for k, nm in enumerate(J4):
        m = tm == k; tot = w[m].sum(); out.append(dict(case=nm, area=tot, judgment_acc=100*w[m & (j4 == k)].sum()/tot if tot else np.nan, target_acc=100*w[m & ok].sum()/tot if tot else np.nan))
    m = tm >= 0; tot = w[m].sum(); out.append(dict(case='전체(채점한 넓이)', area=tot, judgment_acc=100*w[m & (j4 == tm)].sum()/tot if tot else np.nan, target_acc=100*w[m & ok].sum()/tot if tot else np.nan))
    return out
def main(prior, csv, label):
    A1 = json.loads((C/'judgeeval_v1_add1.json').read_text()); h = pd.read_csv(csv); Z = loadz(O/'work'/STAGE/f'truth_{prior}.npz'); idx = Z['patch_index']; pos = {int(x): i for i, x in enumerate(idx)}
    F = loadz(O/'work'/STAGE/f'judge4_{prior}.npz'); assert np.array_equal(F['patch_index'], idx); j4 = F['J4_판 4']; tauT = F['tauT_판 4']
    H = np.full(len(idx), np.nan); r = np.array([pos.get(int(x), -1) for x in h.patch_index]); H[r[r >= 0]] = h.h.values[r >= 0]
    ok, _ = check(prior, idx, H[:, None], tauT[:, None], f'after_{label}'); area = loadz(inp('patches', prior=prior), ['area'])['area'][idx]
    df = pd.DataFrame(trace(Z['answer'][:, 0], j4, ok[:, 0], area)); df.insert(0, 'column', label); (D/'tables/다').mkdir(parents=True, exist_ok=True); df.to_csv(D/'tables/다'/f't3_after_{prior}_{label}.csv', index=False); print(df)
if __name__ == '__main__': main(*sys.argv[1:4])
