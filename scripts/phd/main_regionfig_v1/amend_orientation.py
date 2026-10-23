"""Presentation-only revision following the first blind visual review."""
import shutil
from common import *
assert not (CFG/'amendment_02.json').exists()
prev=PAY/'revision_02';prev.mkdir()
for p in [DOC/'figures/영역예시_보정.png',DOC/'figures/영역예시_보정.pdf',DOC/'figures/검토용_제목숨김.png',PAY/'render_receipt.json',DOC/'검토_1차.md']:
    shutil.copy2(p,prev/p.name)
for p in (DOC/'figures/crops').glob('*_표시.png'):shutil.copy2(p,prev/p.name)
rec=dict(recorded_at=now(),original_config_sha256=sha(CFG/'regionfig_v1.json'),
         previous_render_sha256=sha(prev/'영역예시_보정.png'),
         reason='독립 1차 점검에서 B173 사진과 지도 시작점 연결이 불명확함. 사진의 방향을 지도와 일치시킴.',
         old='camera-native photo display orientation',new='north-up rotation at section midpoint; all marks use the same rigid display transform',
         photo_display_north_up=True,original_crop_pixels_unchanged=True,
         unchanged=['selected photos','native crop boxes','section coordinates','values','visibility','patch geometry'],scientific_verdict=None)
dump(CFG/'amendment_02.json',rec)
dump(CFG/'amendment_02.lock.json',dict(recorded_at=now(),sha256=sha(CFG/'amendment_02.json')))
print(rec['reason'])
