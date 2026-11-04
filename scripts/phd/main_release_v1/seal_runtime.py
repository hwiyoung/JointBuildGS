from common import *
cfg()
assert json.loads((O/'verification/unit_default.json').read_text())['status']=='PASS'
files={str(p):sha(p) for folder in [R/'src/phd/forks/GeoGS-conf-guided-v1-r24'] for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
files[str(O/'bin/release_search.so')]=sha(O/'bin/release_search.so')
dump(C/'runtime.lock.json',dict(at=now(),config_sha256=sha(C/'release_v1.json'),files=files,scientific_verdict=None))
progress('r23 / r24 기본값 / 기록 켬: 실제 GaussianModel·Adam 100회와 복제·분할·정리의 모델·결정·카메라 순서 동일. 당김·지움·섞음 단위 점검 통과. r24 실행 소스 잠금.')
