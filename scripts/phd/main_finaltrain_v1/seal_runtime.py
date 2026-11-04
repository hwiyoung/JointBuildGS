"""Bind the exact new source and passed global preflight before any training."""
import difflib
from common import *
cfg();lockpath=C/'runtime.lock.json'
if lockpath.exists():
    assert not list((O/'runs').glob('*/ft_*/attempt*/launch.json')),'Runtime cannot be revised after training starts'
    previous=sha(lockpath);dest=C/'revisions'/('runtime_'+previous+'.json');dest.parent.mkdir(exist_ok=True)
    assert not dest.exists();lockpath.rename(dest)
for name,digest in json.loads((C/'parent_source.lock.json').read_text()).items():assert sha(R/name)==digest,('Parent changed',name)
for name in ['unit_math.json','unit_default.json']:assert json.loads((O/'verification'/name).read_text())['status']=='PASS'
fork=R/cfg()['fork'];parent=R/cfg()['parent_fork'];files={};changes=[]
for p in sorted(fork.rglob('*')):
    if not p.is_file() or '__pycache__' in p.parts:continue
    files[str(p)]=sha(p);old=parent/p.relative_to(fork)
    if not old.exists() or sha(old)!=sha(p):
        a=old.read_text().splitlines(True) if old.exists() else [];b=p.read_text().splitlines(True)
        changes.append(dict(file=str(p.relative_to(R)),lines=len(b),diff=''.join(difflib.unified_diff(a,b,fromfile=str(old.relative_to(R)),tofile=str(p.relative_to(R))))))
for name in ['train_entry.py','renderer.py','targets.py','prepare_inputs.py','verify_inputs.py','unit_math.py','probe_default.py','verify_default.py','initialize_check.py']:
    p=Path(__file__).with_name(name);files[str(p)]=sha(p)
dump(lockpath,dict(at=now(),config_sha256=sha(C/'finaltrain_v1.json'),files=files,scientific_verdict=None))
dump(D/'changes.json',dict(changes=changes,scientific_verdict=None))
(D/'구현변경.md').write_text('# r23 구현 변경\n\nr22 원본 파일 해시를 첫 잠금과 대조했다. 기본 스위치 off의 100회 동일 씨앗 비교는 모델·Adam·목표 결정·카메라 순서가 같았다.\n\n'+ '\n'.join('```diff\n'+v['diff']+'```\n' for v in changes))
print('RUNTIME_SEALED',sha(lockpath),len(files))
