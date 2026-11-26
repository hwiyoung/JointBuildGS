"""뷰어 v2 점검: 파일마다 화면 갈래 넓이(area_by_mode)가 (1) '목표 맞음·틀림'은 judge4_v2(판 4) 넓이 합과 같고, (2) 그 밖 색은 앞 판(figures/viewer)과 같은지. 사용: GT_STAGE=ga3 g25_viewer_v2_check.py"""
from common import *
import pandas as pd
from target_check import T4
def main():
    V1, V2 = D/'figures/viewer', D/'figures/viewer_v2'; rows = []
    idx = json.loads((V2/'index.json').read_text())['files']; F = {p: loadz(O/'work'/STAGE/f'judge4_v2_{p}.npz') for p in PRIORS}
    A = {}
    for p in PRIORS:
        P = loadz(inp('patches', prior=p), ['area', 'building']); i = F[p]['patch_index']; A[p] = pd.DataFrame(dict(building=P['building'][i], area_m2=P['area'][i], target_ok=F[p]['ok_판 4'], answer=F[p]['answer']))
    for e in idx:
        j2 = json.loads((V2/(Path(e['file']).stem + '.json')).read_text())['area_by_mode']; j1 = json.loads((V1/(Path(e['file']).stem + '.json')).read_text())['area_by_mode']
        t = A[e['prior']]; t = t[t.building == e['building']]; inm = t.answer.map(lambda x: T4.get(int(x), -1)).values >= 0
        exp = {'맞음': t.area_m2[inm & t.target_ok.values].sum(), '틀림': t.area_m2[inm & ~t.target_ok.values].sum(), '채점 밖': t.area_m2[~inm].sum()}
        okt = max(abs(j2['okt'][k] - v) for k, v in exp.items())
        same = all(np.allclose(list(j1[m].values()), list(j2[m].values())) for m in j1 if m != 'okt')
        rows.append(dict(file=e['file'], okt_max_diff_m2=okt, other_modes_same_as_v1=same, okt_v1_ok_m2=j1['okt']['맞음'], okt_v2_ok_m2=j2['okt']['맞음'], mb=e['mb']))
    df = pd.DataFrame(rows); out = D/'figures/viewer_v2/check_v2.csv'; df.to_csv(out, index=False); print(df.round(2).to_string(index=False))
    assert (df.okt_max_diff_m2 < 1e-6).all() and df.other_modes_same_as_v1.all(); progress(f'뷰어 v2 점검: 20개 목표 넓이 = judge4_v2, 다른 색 = 앞 판')
if __name__ == '__main__': main()
