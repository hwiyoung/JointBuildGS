"""Host launcher for addendum 6: the addendum 4 launcher (same images, mounts, fork r31) with logs under addendum6/logs and container names jbgs-te-a6-*.
  cpu|cpubig <script> [args] / gpu <gpu> <script> [args]   (script path relative to scripts/phd/main_trainerr_v1)"""
import sys, re, json, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'addendum4'))
import a4_launch as A
A6O = A.O/'addendum6'; A.LOGS = A6O/'logs'; A.LOGS.mkdir(parents=True, exist_ok=True)
_cmd = A.command
def _command6(*a, **k):   # temporaries inside addendum6/ (order 1.1), not addendum4/
    (A6O/'tmp').mkdir(parents=True, exist_ok=True); return [x.replace('=/te/addendum4/tmp', '=/te/addendum6/tmp') for x in _cmd(*a, **k)]
A.command = _command6
def job(script, *args, gpu=None, cpus=8, memory='40g'):
    name = re.sub(r'[^a-zA-Z0-9_.-]', 'x', f'jbgs-te-a6-{Path(script).stem}-{"-".join(args)}')[:120]
    return A.job(script, *args, gpu=gpu, name=name, cpus=cpus, memory=memory)
if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'cpu': sys.exit(job(a[1], *a[2:]))
    if a[0] == 'cpubig': sys.exit(job(a[1], *a[2:], cpus=16, memory='60g'))
    if a[0] == 'gpu': sys.exit(job(a[2], *a[3:], gpu=int(a[1])))
    raise SystemExit(f'unknown {a}')
