"""Host orchestration for PHD-MAIN-TRAINERR-v1 addendum 4 (docker). Same images and mounts as launch.py, but every log, job record and
mesh shadow is written under the addendum4 folders (order 1.1: only addendum4/ and the new fork folder).
  cpu <script> [args]                 : CPU container (script path relative to scripts/phd/main_trainerr_v1)
  cpubig <script> [args]              : CPU container, 16 CPUs / 60 GB
  gpu <gpu> <script> [args]           : GPU container with fork r31 at /source
  gpufork <gpu> <fork> <script> [args]: GPU container with another fork at /source
  gtj <step> <stem> <family> [ply|-] [gpu]: GTJUDGE/RESCORE mesh + score code (te_mesh.py) with the addendum4 shadow /gtjudge and /te = addendum4 payload
  train <name> <gpu>                  : one order-7 training run (see RUNS)"""
import datetime as dt, json, os, re, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import launch as L
R, ART, PH, O, C, D = L.R, L.ART, L.PH, L.O, L.C, L.D
A4O = O/'addendum4'; A4D = D/'addendum4'; LOGS = A4O/'logs'
FORK = 'GeoGS-conf-guided-v1-r31'
FAST = Path(os.environ['TE_FASTWORK']) if os.environ.get('TE_FASTWORK') else None
now, dump = L.now, L.dump

def command(name, script, args=(), gpu=None, fork=FORK, env=(), cpus=8, memory='40g', split_site=None, cfg_rw=False):
    cmd = L.command(name, script, list(args), gpu=gpu, fork=fork, env=env, cpus=cpus, memory=memory, split_site=split_site, cfg_rw=cfg_rw)
    (A4O/'tmp').mkdir(parents=True, exist_ok=True)
    return [x.replace('=/te/tmp', '=/te/addendum4/tmp') if x.startswith(('TMPDIR=', 'MPLCONFIGDIR=', 'XDG_CACHE_HOME=')) else x for x in cmd]  # temporaries inside addendum4/

def run(cmd, log):
    log.parent.mkdir(parents=True, exist_ok=True); t = time.monotonic()
    with log.open('x') as f: rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
    return rc, time.monotonic()-t

def job(script, *args, gpu=None, fork=FORK, name=None, cpus=8, memory='40g', env=(), split_site=None):
    stem = Path(script).stem; name = name or f'jbgs-te-a4-{stem}-{"-".join(args)}'[:120]
    name = re.sub(r'[^a-zA-Z0-9_.-]', 'x', name.replace(':', '').replace('/', '_'))  # docker names are ASCII only
    log = LOGS/f'{dt.datetime.now().strftime("%Y%m%dT%H%M%S")}_{stem}_{"_".join(args)[:60].replace("/", "_")}.log'
    cmd = command(name, script, list(args), gpu=gpu, fork=fork, cpus=cpus, memory=memory, env=env, split_site=split_site)
    rc, s = run(cmd, log); print(script, args, rc, round(s), log, flush=True)
    with (LOGS/'jobs.jsonl').open('a') as f: f.write(json.dumps(dict(at=now(), script=script, args=list(args), gpu=gpu, fork=fork, exit_code=rc, seconds=s, log=str(log)))+'\n')
    return rc

def gtjcmd(step, stem, family, ply='', gpu=None, name=None):
    """launch.gtjcmd with the addendum4 shadow at /gtjudge and the addendum4 payload at /te (te_mesh.py writes /te/meshes)."""
    sh = A4O/'gtj'; sh.mkdir(parents=True, exist_ok=True); (A4O/'gtj_docs').mkdir(exist_ok=True)
    cmd = L.gtjcmd(step, stem, family, ply, gpu, name=name or re.sub(r'[^a-zA-Z0-9_.-]', 'x', f'jbgs-te-a4-gtj-{step.replace(":", "")}-{stem}-{family}')[:120])
    out = []; i = 0
    while i < len(cmd):
        if cmd[i] == '-v':
            s, d, m = cmd[i+1].rsplit(':', 2)
            if d == '/gtjudge': s = str(sh)
            elif d == '/docs': s = str(A4O/'gtj_docs')
            elif d == '/te': s = str(A4O)
            elif d == '/source': s = str(R/'src/phd/forks'/FORK)
            out += ['-v', f'{s}:{d}:{m}']; i += 2
        else: out.append(cmd[i]); i += 1
    if FAST and not any(x.startswith(f'{FAST}:') for x in out):
        j = out.index('--entrypoint'); out[j:j] = ['-v', f'{FAST}:{FAST}:rw']
    return out

def gtj(step, stem, family, ply='', gpu=None):
    log = LOGS/f'{dt.datetime.now().strftime("%Y%m%dT%H%M%S")}_gtj_{step.replace(":", "")}_{stem}_{family}.log'
    rc, s = run(gtjcmd(step, stem, family, ply, gpu), log); print('gtj', step, stem, family, rc, round(s), flush=True)
    with (LOGS/'mesh_timing.jsonl').open('a') as f: f.write(json.dumps(dict(at=now(), step=step, stem=stem, family=family, exit_code=rc, seconds=s, log=str(log)))+'\n')
    return rc

def gtjscript(script, args, gpu=None, name=None):
    """another script (path relative to scripts/phd/main_trainerr_v1) with the gtj container mounts (/gtjudge = addendum4 shadow, /source = r30)."""
    cmd = gtjcmd('x', 'x', 'x', '', gpu, name=name or re.sub(r'[^a-zA-Z0-9_.-]', 'x', f'jbgs-te-a4-gtjs-{Path(script).stem}-{"-".join(args)}')[:120])
    i = cmd.index('-c'); pre = cmd[i+1].split('exec python')[0]
    log = LOGS/f'{dt.datetime.now().strftime("%Y%m%dT%H%M%S")}_gtjs_{Path(script).stem}_{"_".join(args)[:60]}.log'
    full = cmd[:i+1]+[pre+f'exec python -B -u /repo/scripts/phd/main_trainerr_v1/{script} "$@"', Path(script).stem, *args]
    rc, s = run(full, log); print('gtjscript', script, args, rc, round(s), log, flush=True)
    with (LOGS/'jobs.jsonl').open('a') as f: f.write(json.dumps(dict(at=now(), script=script, args=list(args), gpu=gpu, container='gtj', exit_code=rc, seconds=s, log=str(log)))+'\n')
    return rc

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'cpu': sys.exit(job(a[1], *a[2:]))
    if a[0] == 'cpubig': sys.exit(job(a[1], *a[2:], cpus=16, memory='60g'))
    if a[0] == 'gpu': sys.exit(job(a[2], *a[3:], gpu=int(a[1])))
    if a[0] == 'gpufork': sys.exit(job(a[3], *a[4:], gpu=int(a[1]), fork=a[2], name=f'jbgs-te-a4-gpufork-{a[2][-3:]}-{Path(a[3]).stem}-{"-".join(a[4:])}'[:120]))
    if a[0] == 'gtjscript': sys.exit(gtjscript(a[2], a[3:], int(a[1]) if a[1] != '-' else None))
    if a[0] == 'gtj': sys.exit(gtj(a[1], a[2], a[3], a[4] if len(a) > 4 and a[4] != '-' else '', int(a[5]) if len(a) > 5 else None))
    raise SystemExit(f'unknown {a}')
