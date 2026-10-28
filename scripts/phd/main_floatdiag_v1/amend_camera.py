"""Preserve draft camera policy; use identical perspective projection in both renderers."""
import json
from common import *
cfg=config()
assert cfg['cameras']['projection'].startswith('orthographic')
for name in ['floatdiag_v1.json','floatdiag_v1.lock.json']:
    src=CFG/name;dst=CFG/'history'/('pre_perspective_'+name)
    dst.parent.mkdir(parents=True,exist_ok=True);assert not dst.exists();dst.write_bytes(src.read_bytes())
prior=sha(CFG/'floatdiag_v1.json')
cfg['cameras']['projection']='perspective, identical intrinsics and extrinsics for mesh and Gaussian renders'
cfg['amendments']=[dict(at=now(),reason='Use the exact same camera in mesh and Gaussian captures; preserve all cases, results, angles and colour ranges. No captures were produced before this amendment.',prior_sha256=prior)]
(CFG/'floatdiag_v1.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
(CFG/'floatdiag_v1.lock.json').write_text(json.dumps(dict(frozen_at=now(),sha256=sha(CFG/'floatdiag_v1.json'),stage='before first rendered result',scientific_verdict=None),indent=2)+'\n')
assert not any((DOC/'3d').glob('**/*.png'))
for p in list(CFG.glob('geometry_*.json')):
    dest=CFG/'history'/('pre_perspective_'+p.name)
    p.rename(dest)
for p in (OUT/'3d').glob('*/coordinate.json'):
    p.rename(p.with_name('coordinate_pre_perspective.json'))
with (DOC/'issues.md').open('a') as f:
    f.write('\nFD-003: 최초 카메라 초안은 메시 직교투영과 가우시안 원근투영이 달랐다. 첫 캡처 전에 이 작업의 준비 프로세스만 종료하고, 둘 모두 같은 원근 카메라를 쓰도록 수정했다. 기존 설정·잠금과 준비 좌표는 history/와 coordinate_pre_perspective.json에 보존했다. LOSSTRAIN과 다른 서비스는 변경하지 않았다.\n')
print('perspective camera policy frozen',sha(CFG/'floatdiag_v1.json'))
