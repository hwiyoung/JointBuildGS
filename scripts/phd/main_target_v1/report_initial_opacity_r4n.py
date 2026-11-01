"""Record actual initialized opacity separately for target and MVS-background seeds."""
import numpy as np
from common import *

def main():
    rows=[]
    for prior in ['ALS','LoD2']:
        root=OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0/model/target_monitor'
        if not (root/'snapshot_0.npz').exists():continue
        with np.load(root/'snapshot_0.npz') as z:
            for label,origin in [('prior_target',1),('MVS_background',0)]:
                values=z['opacity'][z['origin']==origin]
                assert np.all(values==np.float32(.1))
                rows.append(dict(site='B173nb_b10',prior=prior,population=label,count=len(values),
                    min=float(values.min()),median=float(np.median(values)),max=float(values.max()),
                    baseline_nominal=.1,same_baseline_initial_value=True,snapshot_sha256=sha(root/'snapshot_0.npz')))
    dump(DOC/'tables/initial_opacity_r4n.json',dict(at=stamp(),rows=rows,
        baseline_source='r19 scene/gaussian_model.py create_from_pcd inverse_opacity_activation(0.1 * ones); unchanged from base',
        background_source='jbgs_target.py inverse_opacity_activation(torch.full(...,.1))',scientific_verdict=None))
    text=['# r4n 처음 불투명도','',
        '목표 자리 씨앗과 MVS 배경 씨앗은 모두 **0.1**에서 시작한다. 기준선과 같은 값이다. 실제 float32 활성화 값은 `0.10000000149011612`로 저장되며, 아래 최소·중앙·최대가 모두 같다.','',
        '| 조합 | 씨앗 종류 | 수 | 최소 | 중앙값 | 최대 | 기준선과 같음 |','|---|---|---:|---:|---:|---:|---|']
    for r in rows:text.append(f"| {r['prior']} | {'사전 목표' if r['population']=='prior_target' else 'MVS 배경'} | {r['count']:,} | {r['min']:.9f} | {r['median']:.9f} | {r['max']:.9f} | 예 |")
    text+=['','이 값은 실제 학습의 0회 저장 배열에서 별도로 읽었다. 기존 크기 규칙, 분할·제거·불투명도 재설정 일정은 바꾸지 않았다. 현재 추가 기록은 학습의 파라미터가 아니다.','',
        '[수치와 원본 해시](tables/initial_opacity_r4n.json) · `scientific_verdict: null`']
    (DOC/'처음불투명도_r4n.md').write_text('\n'.join(text)+'\n');print('INITIAL_OPACITY_R4N',rows,flush=True)

if __name__=='__main__':main()
