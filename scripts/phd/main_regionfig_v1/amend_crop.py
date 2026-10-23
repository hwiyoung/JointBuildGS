"""Append-only correction after first render: enforce the requested full 4 m crop."""
import shutil
from common import *
assert not (CFG/'amendment_01.json').exists()
previous=PAY/'revision_01';previous.mkdir()
for p in [PAY/'prepared.json',PAY/'candidates_a.json',PAY/'candidates_b.json',PAY/'render_receipt.json',DOC/'figures/영역예시_보정.png',DOC/'figures/영역예시_보정.pdf']:
    shutil.copy2(p,previous/p.name)
for p in (DOC/'figures/crops').glob('*.png'):shutil.copy2(p,previous/p.name)
rec=dict(recorded_at=now(),config_sha256=sha(CFG/'regionfig_v1.json'),
         previous_render_sha256=sha(previous/'영역예시_보정.png'),
         reason='첫 그림의 B173 사진 오른쪽에서 발주 2.3의 주변 4 m 범위가 잘림. 학습 영상과 원본의 시야, 주변 4 m 범위를 모두 만족하는 후보에 같은 사진 순위를 적용한다.',
         old='entire projected line inside original photograph; then corrected to also require training image field',
         new='entire projected line inside the training image AND original; projected 4 m XYZ crop prism fully inside original',
         drawing_fix='가려진 짧은 선 조각들을 이어서 점선 간격이 실제로 보이게 함.',
         unchanged=['section coordinates','bin width','patch population rule','height formula','visibility tolerance','photo ranking among feasible candidates','colours'],
         previous_files=str(previous),scientific_verdict=None)
dump(CFG/'amendment_01.json',rec)
dump(CFG/'amendment_01.lock.json',dict(recorded_at=now(),sha256=sha(CFG/'amendment_01.json')))
print(rec['reason'])
