"""다시 셀 것 5: '윤곽 밖의 새 면' 모임을 JC 그림 6 에 이미 실린 것 다음으로 넓이 큰 차례 20개 더 (한 건물 둘까지), JC 그림 6 과 같은 짜임.
JC s10_images.fig6 를 그대로 부르고(only_gt 경로 = 유형마다 하나 더함 없음), 고를 표만 바꿔 준다. JC 결과는 /out 에 읽기 전용으로, 그림은 /docs/figures(스테이지)에."""
import sys, json, glob
JCS = '/repo/scripts/phd/main_judgecheck_v2'; sys.path.insert(0, JCS + '/inherited'); sys.path.insert(0, JCS)
import pandas as pd
import s10_images as S
orig = pd.read_csv
def main():
    prev = []
    for f in sorted(glob.glob('/repo/docs/experiments/phd/main_judgecheck_v2/figures/fig6_outside_clusters_*.json')): prev += [c['cluster_id'] for c in json.load(open(f))['clusters']]
    def rc(path, *a, **k):
        C = orig(path, *a, **k)
        if str(path).endswith('analysis/clusters.csv'):
            C = C[(C.geometry_type == '윤곽 밖의 새 면') & ~C.cluster_id.isin(prev)]
            print('candidates', len(C), 'by source', C.cluster_source.value_counts().to_dict(), flush=True)
        return C
    S.pd.read_csv = rc
    S.fig6(only_gt=True)
if __name__ == '__main__': main()
