"""Host launcher for addendum 5: the addendum 4 launcher (same images, mounts, fork r31) with logs under addendum5/logs and container names jbgs-te-a5-*.
  cpu|cpubig <script> [args] / gpu <gpu> <script> [args]   (script path relative to scripts/phd/main_trainerr_v1)"""
import sys, re, json, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'addendum4'))
import a4_launch as A
A5O = A.O/'addendum5'; A.LOGS = A5O/'logs'; A.LOGS.mkdir(parents=True, exist_ok=True)
_cmd = A.command
def _command5(*a, **k):   # temporaries inside addendum5/ (order 1.1), not addendum4/
    (A5O/'tmp').mkdir(parents=True, exist_ok=True); return [x.replace('=/te/addendum4/tmp', '=/te/addendum5/tmp') for x in _cmd(*a, **k)]
A.command = _command5
def job(script, *args, gpu=None, cpus=8, memory='40g'):
    name = re.sub(r'[^a-zA-Z0-9_.-]', 'x', f'jbgs-te-a5-{Path(script).stem}-{"-".join(args)}')[:120]
    return A.job(script, *args, gpu=gpu, name=name, cpus=cpus, memory=memory)
if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'cpu': sys.exit(job(a[1], *a[2:]))
    if a[0] == 'cpubig': sys.exit(job(a[1], *a[2:], cpus=16, memory='60g'))
    if a[0] == 'gpu': sys.exit(job(a[2], *a[3:], gpu=int(a[1])))
    raise SystemExit(f'unknown {a}')
