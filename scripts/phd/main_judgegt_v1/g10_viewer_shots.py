"""뷰어 확인 화면용 패치 고르기: 건물마다 가2 정답 '사전 정보(영상 틀림)'(없으면 '영상')인 패치 가운데 넓이 큰 순 첫 번째의 번호. 사용: g10_viewer_shots.py"""
from common import *
import pandas as pd
BLD = ['DEBY_LOD2_4959460', 'DEBY_LOD2_4906968', 'DEBY_LOD2_108580336']
def main():
    out = []
    for p in PRIORS:
        f = pd.read_csv(O/f'forward_{p}_ga2.csv.gz', usecols=['patch_id', 'building', 'answer', 'area_m2', 'site'])
        for b in BLD:
            g = f[f.building == b]
            for a in ['사전 정보(영상 틀림)', '영상']:
                h = g[g.answer == a].sort_values(['area_m2', 'patch_id'], ascending=[False, True])
                if len(h): out.append(dict(prior=p, building=b, site=h.site.iloc[0], answer=a, patch_id=h.patch_id.iloc[0], pick=int(h.patch_id.iloc[0].split(':')[-1]))); break
    dump(D/'viewer/가2/shots_pick.json', dict(at=now(), rule=__doc__, rows=out, scientific_verdict=None)); [print(r) for r in out]
if __name__ == '__main__': main()
