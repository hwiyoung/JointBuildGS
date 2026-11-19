"""Lock the config before a stage's first computation (order 1.3). usage: g0_lock.py <stage> [revision note]
A later revision writes gttarget_v1.stage<n>.lock.json again only with a note; the previous lock is kept as .rev<k>.json."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
stage = sys.argv[1]; note = ' '.join(sys.argv[2:]) or None; p = C/f'gttarget_v1.stage{stage}.lock.json'
if p.exists():
    assert note, 'already locked; a revision needs a note'
    k = len(list(C.glob(f'gttarget_v1.stage{stage}.lock.rev*.json')))+1; p.rename(p.with_name(f'gttarget_v1.stage{stage}.lock.rev{k}.json'))
dump(p, dict(at=now(), stage=int(stage), config_sha256=sha(C/'gttarget_v1.json'), revision_note=note, scientific_verdict=None))
print('LOCKED', stage, sha(C/'gttarget_v1.json'))
