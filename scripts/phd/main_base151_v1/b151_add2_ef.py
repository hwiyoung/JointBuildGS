#!/usr/bin/env python3
"""PHD-MAIN-BASE151-v1 addendum 2 item 1-7 (host): the TRAINUNIT-v2 model cellsef_ALS_s0 cell 3 (no new training) meshed and scored on the
cell-3 units with the 4.2 rule (render -> b151_units mesh -> b151_score151). Run name a2_JBGSef_ALS (prior ALS: the model was trained with the
ALS targets). The model is not the final one and its targets were not made from the 151-building judgement.

  python3 b151_add2_ef.py units            # list the cell-3 units
  python3 b151_add2_ef.py one <unit>       # job -> render (GPU 1, fork image) -> mesh -> score ALS
  nohup python3 b151_add2_ef.py all > OUT/logs/add2_ef.log 2>&1 &
scientific_verdict: null
"""
import json
import sys
import time

from b151_host import OUT, dump, now
from b151_post41 import ART, EXP, M, PH, W, gpu_ready, sh
import b151_post42 as P42

RUN = 'a2_JBGSef_ALS'
TU1 = PH / 'main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1'
PLY = '/art/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1/runs/ef/cellsef_ALS_s0_cell3/attempt2/model/point_cloud/iteration_30000/point_cloud.ply'
IMAGE = 'sha256:ff4eba02c450573e3258ec4946b9c536f32c213dde9abc83ee2969aaf18384be'   # jointbuildgs:geogs-conf-guided-v1 (TRAINUNIT tu_host.IMAGE)
SRC = W / 'src/phd/forks/GeoGS-conf-guided-v1-r23'                                     # TRAINUNIT tu_post.gt_gpu /source


def units():
    return [u for u in json.loads((M / 'units/layout.json').read_text())['units'] if u['cell'] == 3]


def job(u):
    key = f'{u["unit"]}__ALS__{RUN}'
    p = M / 'jobs' / f'{key}.json'
    if not p.exists():
        dump(p, dict(site=u['unit'], prior='ALS', family='ef_s0', key=key, ply=PLY, box=u['box'], run=RUN, cell=3,
                     model='TRAINUNIT-v2 cellsef_ALS_s0 cell 3 attempt2 iteration 30000', note='render_model keeps the Gaussians inside the unit box',
                     scientific_verdict=None))
    return key


def render_cmd(key, fraction='.25'):
    return ['docker', 'run', '--rm', '--read-only', '--network', 'none', '--gpus', 'device=1', '--oom-score-adj', '800',
            '--name', f'jbgs-b151-post-render-{key}'.replace('_', '-').lower(), '--user', '1000:1000', '--cpus', '4', '--memory', '32g',
            '--memory-swap', '32g', '--shm-size', '4g',
            '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'PYTHONUNBUFFERED=1', '-e', 'OMP_NUM_THREADS=1', '-e', 'TZ=Asia/Seoul', '-e', 'HOME=/tmp',
            '-e', 'PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True',
            '-e', f'RESCORE_RENDER_GPU_FRACTION={fraction}', '-e', 'RESCORE_OUTPUT_ROOT=/gtjudge', '-e', 'RESCORE_DOC_ROOT=/gtjudge/docs',
            '-e', 'TMPDIR=/gtjudge/tmp', '-e', 'MPLCONFIGDIR=/gtjudge/tmp/mpl',
            '-v', f'{W}:/repo:ro', '-v', f'{EXP}/scripts/phd:/repo/scripts/phd:ro', '-v', f'{ART}:/art:ro', '-v', f'{ART}:/artifacts/JointBuildGS:ro',
            '-v', f'{SRC}:/source:ro', '-v', f'{M}:/gtjudge:rw', '-v', f'{OUT}:/b151:ro', '-v', f'{W}/configs/phd/main_gtjudge_v1:/cfg:ro',
            '-v', f'{W}/scripts/phd/main_base151_v1:/b151s:ro',
            '-w', '/source', '--entrypoint', 'python', IMAGE, '-B', '-u', '/b151s/b151_add2_render.py', f'/gtjudge/jobs/{key}.json']


def one(uname):
    u = [x for x in units() if x['unit'] == uname][0]
    key = job(u)
    log = OUT / 'logs' / 'add2' / f'{key}.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    if not (M / 'renders' / key / 'receipt.json').exists():
        while not gpu_ready():
            time.sleep(120)
        ok = sh(render_cmd(key), log)
        if not ok:   # the 4.2 rule allowed a second try at a larger GPU share (addendum 1: cell 3 OOM at 25 %)
            ok = sh(render_cmd(key, '.6'), log)
        if not ok:
            return False
    t1 = time.monotonic()
    ok = P42.unit(RUN, uname)   # job and render exist -> mesh (prepare / plan / tiles / merge / finish) -> score ALS
    dump(OUT / 'add2' / f'{uname}_timing.json', dict(at=now().isoformat(), run=RUN, unit=uname, render_seconds=t1 - t0, rest_seconds=time.monotonic() - t1,
                                                    ok=bool(ok), scientific_verdict=None))
    return ok


def main(cmd, *a):
    if cmd == 'units':
        for u in units():
            print(u['unit'], u.get('views'))
    elif cmd == 'one':
        print('OK' if one(a[0]) else 'FAIL', flush=True)
    elif cmd == 'all':
        res = {u['unit']: one(u['unit']) for u in units()}
        dump(OUT / 'add2' / 'done.json', dict(at=now().isoformat(), run=RUN, units=res, scientific_verdict=None))
        print('DONE', res, flush=True)


if __name__ == '__main__':
    main(*sys.argv[1:])
