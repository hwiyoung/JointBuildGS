"""Config + code lock before the first result training (order 9). usage (cpulock container): df0_lock.py
writes /cfg/depthfix_v1.lock.json: config sha256, every scripts/phd/main_depthfix_v1/*.py sha256, fork r23 top-level *.py sha256,
input sha256 (나5 csv, target files, seeds, map indices of every arm folder). An existing lock is kept as .lock.revN.json."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
p = C/'depthfix_v1.lock.json'
if p.exists():
    n = 1
    while (C/f'depthfix_v1.lock.rev{n}.json').exists(): n += 1
    p.rename(C/f'depthfix_v1.lock.rev{n}.json')
c = cfg(False); arms = {}
for arm in c['arms']:
    for stem in c['stems']:
        rd = O/'arms'/arm/'stage1'/stem/'ready.json'
        if rd.exists(): arms[f'{arm}/{stem}'] = json.loads(rd.read_text())
dump(p, dict(at=now(), config=str(C/'depthfix_v1.json'), config_sha256=sha(C/'depthfix_v1.json'),
             code={x.name: sha(x) for x in sorted((R/'scripts/phd/main_depthfix_v1').glob('*.py'))},
             fork='src/phd/forks/GeoGS-conf-guided-v1-r23', fork_files={x.name: sha(x) for x in sorted(Path('/source').glob('*.py'))} if Path('/source').exists() else None,
             inputs={x.name: sha(x) for x in sorted(NA5.glob('*'))}, arms=arms,
             note='잠근 뒤 규칙·값을 바꾸지 않는다. 결과 학습은 이 잠금의 config sha와 같을 때만 시작한다(df_entry).', scientific_verdict=None))
print('LOCKED', sha(C/'depthfix_v1.json'), len(arms))
