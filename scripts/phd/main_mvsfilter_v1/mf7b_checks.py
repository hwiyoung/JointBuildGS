"""9절 점검 1·2·4 를 표·저장 값에서 따로 셈 (점검 3 은 mf1 의 masks/A.json). 참값은 읽지 않음(이미 낸 표만 비교).
점검 1: 방법을 안 넣고 다시 낸 구조 하한 행 = JUDGESTRUCT-v1 구조 하한 행, 모든 칸(점·패치 × 네 경우·전체·평균·최솟값·격차).
점검 2: 구역마다 지금 점 수 = 살아남은 점 + 지워진 점(지워진 점은 마스크 0 비트를 화소 지도로 따로 셈). 패치마다 원통 안 점 raw_n(방법) ≤ raw_n(지금).
점검 4: 차이가 유의한 패치의 수·넓이·처음 상태 수(지금 점군) = JUDGESTRUCT-v1 t11_initial_state '전체' 행.
사용: mf7b_checks.py <method> [...]"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_mvsfilter_v1')
from mfcommon import *
import mfcommon as MC
import pandas as pd

DOC = Path('/docs/tables')
JST = Path('/repo/docs/experiments/phd/main_judgestruct_v1/tables')

def main(methods):
    MC.cfg(); T = Timer(); out = []
    # 점검 1
    R = pd.read_csv(DOC/'t6_rejudge.csv'); num = [c for c in R.columns if c.startswith(('ok_', 'patch_ok_'))]
    a = R[R.line == '구조 하한 (JUDGESTRUCT-v1)'].set_index(['prior', 'surface'])[num]
    b = R[R.line == '구조 하한 (지금 점군) — 이 셈에서 다시 냄'].set_index(['prior', 'surface'])[num]
    b = b.loc[a.index]; eq = (a.values == b.values) | (np.isnan(a.values) & np.isnan(b.values))
    out.append(dict(check='점검 1: 방법 없이 다시 낸 구조 하한 = JUDGESTRUCT-v1 구조 하한 (모든 칸, 정확히 같음)', cells=int(eq.size), equal=int(eq.sum()),
                    max_abs_diff=float(np.nanmax(np.abs(a.values - b.values))), passed=bool(eq.all())))
    # 점검 4
    J = pd.read_csv(JST/'t11_initial_state.csv'); J = J[(J['set'] == '차이가 유의한 패치') & (J['split'] == '전체')].set_index(['prior', 'surface'])
    I = pd.read_csv(DOC/'t6_initial_state.csv'); I = I[I.method == '지금 점군'].set_index(['prior', 'surface'])
    cols = ['patches', 'area_m2', 'area_with_state_m2'] + [c for c in I.columns if c.startswith('n_')]
    rows = []
    for k in J.index:
        for c in cols:
            x, y = J.loc[k, c], I.loc[k, c]; rows.append(dict(prior=k[0], surface=k[1], field=c, JS=float(x), mine=float(y), equal=bool(np.isclose(x, y, rtol=0, atol=1e-6))))
    q = pd.DataFrame(rows)
    out.append(dict(check='점검 4: 차이가 유의한 패치의 수·넓이·처음 상태 수 = JUDGESTRUCT-v1 t11_initial_state (전체 행)', cells=len(q), equal=int(q.equal.sum()), passed=bool(q.equal.all()),
                    not_equal=q[~q.equal].to_dict('records')))
    # 점검 2
    for m in methods:
        M = np.load(O/'masks'/f'{m}.npy'); tot = sur = rem = 0; bad_tiles = []; raw_bad = 0; raw_n = 0
        for t in tiles():
            js = O/'patch'/m/f'{t}.json'
            if not js.exists(): continue
            rec = json.loads(js.read_text()); V = np.load(WI/'points'/t/'mvs_a_view.npy'); pix = np.load(O/'pixmap'/f'{t}.npy')
            removed = 0
            order = np.argsort(V, kind='stable'); Vs = V[order]; cuts = np.flatnonzero(np.diff(Vs)) + 1
            for seg in np.split(order, cuts):
                row = np.unpackbits(M[int(V[seg[0]])], count=H*Wd); removed += int((row[pix[seg]] == 0).sum())
            ok = rec['points'] == len(V) and rec['points'] == rec['survived'] + removed
            if not ok: bad_tiles.append(dict(tile=t, points=rec['points'], survived=rec['survived'], removed=removed))
            tot += len(V); sur += rec['survived']; rem += removed
            zn = np.load(O/'patch'/'none'/f'{t}.npz'); zm = np.load(O/'patch'/m/f'{t}.npz')
            for p in zm['priors']:
                a_, b_ = zn[f'{p}__raw_n'], zm[f'{p}__raw_n']; v = a_ >= 0; raw_n += int(v.sum()); raw_bad += int((b_[v] > a_[v]).sum())
        out.append(dict(check=f'점검 2 ({m}): 구역마다 지금 점 = 살아남은 점 + 지워진 점 (지워진 점은 마스크 0 비트로 따로 셈)', points=tot, survived=sur, removed=rem,
                        passed=bool(not bad_tiles and tot == sur + rem), bad_tiles=bad_tiles))
        out.append(dict(check=f'점검 2 ({m}): 패치마다 원통 안 점 raw_n(방법) ≤ raw_n(지금 점군)', patches=raw_n, violations=raw_bad, passed=raw_bad == 0))
    a3 = json.loads((O/'masks'/'A.json').read_text())
    out.append(dict(check='점검 3: masks/A.json 기록(mf1)', record={k: v for k, v in a3.items() if 'check' in k.lower() or '검' in k}))
    dump(DOC/'t9_checks.json', dict(at=now(), checks=out, seconds=T.s(), GT_read=False, scientific_verdict=None))
    for c in out: print('CHECK', json.dumps(jsafe({k: v for k, v in c.items() if k not in ('not_equal', 'bad_tiles')}), ensure_ascii=False)[:400], flush=True)

if __name__ == '__main__': main(sys.argv[1:])
