"""덧붙임 1 5절 검산 1 의 기록: A2 에서 c = 1 인(자기 말고 일치 시점이 없는) 화소를 나눔 — 본 다른 영상 없음(m = 1) / 깊이는 1 % 안이었으나 되비춤·법선에서 빠짐(q ≥ 1) / 나머지(앞에 다른 면·지나쳐 봄만).
값을 고르거나 바꾸지 않음, 기록만. 참값 읽지 않음. 사용: mf14_a2_diag.py"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
from mfcommon import *
def main():
    cfg(); n = 819; mm = {k: np.memmap(O/'a2'/f'px_{k}.u16', dtype='<u2', mode='r', shape=(n, H*Wd)) for k in 'cfomq'}; none = load_mask('none').reshape(n, -1)
    agg = dict(valid=0, c1=0, c1_m1=0, c1_q=0, c1_other=0, c1_only_o=0, c1_only_f=0, q_any=0, c_ge2=0)
    for i in range(n):
        v = none[i]; c = np.asarray(mm['c'][i])[v]; m = np.asarray(mm['m'][i])[v]; q = np.asarray(mm['q'][i])[v]; o = np.asarray(mm['o'][i])[v]; f = np.asarray(mm['f'][i])[v]
        one = c == 1; agg['valid'] += len(c); agg['c1'] += int(one.sum()); agg['c_ge2'] += int((c >= 2).sum()); agg['q_any'] += int((q >= 1).sum())
        agg['c1_m1'] += int((one & (m == 1)).sum()); agg['c1_q'] += int((one & (m > 1) & (q >= 1)).sum()); rest = one & (m > 1) & (q == 0); agg['c1_other'] += int(rest.sum())
        agg['c1_only_o'] += int((rest & (f == 0)).sum()); agg['c1_only_f'] += int((rest & (o == 0)).sum())
    pct = {k: 100*v/agg['valid'] for k, v in agg.items() if k != 'valid'}
    dump(O/'masks/A2_diag.json', dict(at=now(), counts=agg, pct_of_valid=pct, note='c1_q = c 가 1 이고 깊이는 1 % 안이었던 영상이 하나 이상(되비춤 2 화소·법선 10° 에서 빠짐)', scientific_verdict=None)); print('A2DIAG', json.dumps(jsafe(pct)), flush=True)
if __name__ == '__main__': main()
