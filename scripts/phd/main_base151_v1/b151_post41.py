#!/usr/bin/env python3
"""PHD-MAIN-BASE151-v1 4.1: the three evaluation scenes with the TRAINUNIT-v2 mesh rule and scorer (host side, stdlib + docker).

  python3 b151_post41.py mirror            # OUT/gt = GTJUDGE mirror (read-only links) + this task's job/render/mesh folders
  python3 b151_post41.py run <run>         # every site: crop -> render -> mesh -> score (both priors; 2DGS meshes once)
  nohup python3 b151_post41.py watch > OUT/logs/post41.log 2>&1 &   # runs whose merged model exists, one after another

Steps per (run, site) (config scoring 4.1):
  crop    b151_post.py crop: Gaussians of the merged model inside the GTJUDGE views/<site>.json box (render_model's inclusive float32 test)
  render  RESCORE render_model.py with the method's own renderer (/source) in the method's image (depth = surf_depth for 2D methods, depth for
          CDGS through the job's family 'CDGS'), at the GTJUDGE views/<site>.json list; GPU 1 when >= 10 GiB free (training has priority)
  mesh    GTJUDGE mesh_job.py prepare / plan / tile:k / merge / finish (streamed TSDF 0.05 / 0.25, bounded cleanup) in jointbuildgs:dev
  score   GTJUDGE score_new.py (normal-line distance of the reference rows, cylinder accuracy samples)
2DGS uses no prior: its ALS mesh is the mesh of both priors (hard link + receipt), scored with each prior's rows and cases.
scientific_verdict: null
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from b151_host import ART, C, D, OUT, PH, SCRIPTS, W, avail_gb, dump, gpu_free_mib, issue, now, progress, sha

G = PH / 'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
RS = PH / 'main_rescore_v1/PHD-MAIN-RESCORE-v1'
RL = PH / 'main_release_v1/PHD-MAIN-RELEASE-v1'
M = OUT / 'gt'
CG = '/art/phase-payloads/phd/main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
EXP = (W.parent / 'JointBuildGS-exp').resolve()
SITES = ['B0_b10', 'R1rep_b10', 'B173nb_b10']
PRIORS = ['ALS', 'LoD2']
BASE_METHODS = ['prior', 'mvs', 'fusion', 'baseline_30000', 'GeoGS_30000', '2DGS_30000', 'CDGS_30000', 'FINALTRAIN_30000']
METHOD = {'2DGS': dict(family='2DGS', image='jointbuildgs:2dgs-official-f3e3b9f-v1-b151', source=PH / 'main_baselines_v1/PHD-MAIN-BASELINES-v1/sources/2d-gaussian-splatting-adapters-v1'),
          'GeoGS': dict(family='GeoGS', image='jointbuildgs:geogs-official-db40c95-compat-v1', source=PH / 'main_fix_v1/PHD-MAIN-FIX-v1/geogs/source/GeoGS-official-adapters-v1-fix1'),
          'CDGS': dict(family='CDGS', image='jointbuildgs:cdgs-official-db853c1-v1-b151', source=PH / 'main_fill_v1/PHD-MAIN-FILL-v1/sources/cdgs-release-adapters-v3')}


def link(target, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.exists():
        return
    os.symlink(target, path)


def mirror():
    for site in SITES:
        link(f'{CG}/reference/{site}', M / 'reference' / site)
        link(f'{CG}/views/{site}.json', M / 'views' / f'{site}.json')
        for prior in PRIORS:
            stem = f'{site}__{prior}'
            for f in ['rows.npz', 'stage1_cells.npz']:
                link(f'{CG}/scenes/{stem}/{f}', M / 'scenes' / stem / f)
            for m in BASE_METHODS:
                for suf in ['.npz', '_samples.npz', '.json']:
                    if (G / 'scenes' / stem / 'distances' / f'{m}{suf}').exists():
                        link(f'{CG}/scenes/{stem}/distances/{m}{suf}', M / 'scenes' / stem / 'distances' / f'{m}{suf}')
    link(f'{CG}/shared', M / 'shared')
    for d in ['tmp', 'logs', 'docs', 'jobs', 'meshes', 'renders', 'timing']:
        (M / d).mkdir(parents=True, exist_ok=True)
    print('MIRROR_READY', flush=True)


def sh(cmd, log, tries=2):
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, tries + 1):
        with open(log, 'a') as f:
            f.write(f'\n### {now().isoformat()} attempt {attempt}\n')
            f.flush()
            rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
        if rc == 0:
            return True
    issue(f'4.1 후처리 명령 {tries}회 실패: {" ".join(map(str, cmd[-6:]))} (기록 {log})')
    return False


def gt_cpu(tag, script, *args, cpus='6', mem='32g'):
    commit = subprocess.run(['git', '-C', str(W), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    return ['nice', '-n', '15', 'docker', 'run', '--rm', '--read-only', '--network', 'none', '--runtime', 'runc', '--oom-score-adj', '800',
            '--name', f'jbgs-b151-post-{tag}', '--user', f'{os.getuid()}:{os.getgid()}', '--cpus', cpus, '--memory', mem, '--memory-swap', mem,
            '-e', 'CUDA_VISIBLE_DEVICES=', '-e', 'NVIDIA_VISIBLE_DEVICES=void', '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'PYTHONUNBUFFERED=1',
            '-e', 'OMP_NUM_THREADS=2', '-e', 'OPENBLAS_NUM_THREADS=1', '-e', 'MKL_NUM_THREADS=1',
            '-e', 'TMPDIR=/gtjudge/tmp', '-e', 'MPLCONFIGDIR=/gtjudge/tmp/mpl', '-e', 'XDG_CACHE_HOME=/gtjudge/tmp/cache', '-e', 'TZ=Asia/Seoul',
            '-e', f'GTJUDGE_COMMIT={commit}', '-e', 'GTJUDGE_IMAGE=jointbuildgs:dev',
            '-v', f'{W}:/repo:ro', '-v', f'{ART}:/art:ro', '-v', f'{ART}:/artifacts/JointBuildGS:ro', '-v', f'{PH}:/ph:ro',
            '-v', f'{RS}:/out:ro', '-v', f'{RL}:/release:ro', '-v', f'{M}:/gtjudge:rw', '-v', f'{OUT}:/b151:ro',
            '-v', f'{W}/configs/phd/main_gtjudge_v1:/cfg:ro', '-v', f'{M}/docs:/docs:rw', '-v', f'{EXP}/scripts/phd:/repo/scripts/phd:ro',
            '-v', f'{W}/scripts/phd/main_base151_v1:/b151s:ro', '-v', f'{W}/scripts/phd/main_trainunit_v1:/tus:ro',
            '-v', '/usr/share/fonts/opentype/noto:/fonts:ro', '-w', '/gtjudge', '--entrypoint', 'nice', 'jointbuildgs:dev', '-n', '19', 'python', '-B', '-u',
            script if script.startswith('/') else f'/repo/scripts/phd/main_gtjudge_v1/{script}', *map(str, args)]


def render_cmd(method, key, gpu=1, fraction='.25'):
    m = METHOD[method]
    return ['docker', 'run', '--rm', '--read-only', '--network', 'none', '--gpus', f'device={gpu}', '--oom-score-adj', '800',
            '--name', f'jbgs-b151-post-render-{key}'.replace('_', '-').lower(), '--user', f'{os.getuid()}:{os.getgid()}', '--cpus', '4', '--memory', '32g',
            '--memory-swap', '32g', '--shm-size', '4g',
            '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'PYTHONUNBUFFERED=1', '-e', 'OMP_NUM_THREADS=1', '-e', 'TZ=Asia/Seoul', '-e', 'HOME=/tmp',
            '-e', f'RESCORE_RENDER_GPU_FRACTION={fraction}', '-e', 'RESCORE_OUTPUT_ROOT=/gtjudge', '-e', 'RESCORE_DOC_ROOT=/gtjudge/docs',
            '-e', 'TMPDIR=/gtjudge/tmp', '-e', 'MPLCONFIGDIR=/gtjudge/tmp/mpl',
            '-v', f'{W}:/repo:ro', '-v', f'{EXP}/scripts/phd:/repo/scripts/phd:ro', '-v', f'{ART}:/art:ro', '-v', f'{m["source"]}:/source:ro',
            '-v', f'{M}:/gtjudge:rw', '-v', f'{OUT}:/b151:ro', '-v', f'{W}/configs/phd/main_rescore_v1:/cfg:ro',
            '-w', '/source', '--entrypoint', '/bin/bash', m['image'], '-c',
            'if [ -f /opt/geogs/lib/libstdc++.so.6 ]; then export LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6; fi; '
            f'exec python -B -u /repo/scripts/phd/main_rescore_v1/render_model.py /gtjudge/jobs/{key}.json']


def method_of(run):
    return run.split('_')[1]


def one(run, site):
    t0 = time.monotonic()
    method = method_of(run)
    fam = run
    crop = OUT / 'post' / run / f'{site}.ply'
    if method == 'LGDM':
        pass
    elif not crop.exists():
        if not sh(['bash', str(SCRIPTS / 'run_cpu.sh'), f'crop-{run}-{site}'.replace('_', '-').lower(), '8', '48g', 'b151_post.py', 'crop',
                   f'/b151/runs/{run}/merged/point_cloud.ply', f'/b151/gt/views/{site}.json', f'/b151/post/{run}/{site}.ply'],
                  OUT / 'logs' / f'post41_crop_{run}_{site}.log'):
            return False
    t1 = time.monotonic()
    priors = ['ALS', 'LoD2'] if method == '2DGS' else [run.split('_')[2]]
    first = priors[0]
    box = json.loads((G / 'views' / f'{site}.json').read_text())['box']   # host side: the mirror link points to a container path
    key = f'{site}__{first}__{fam}'
    job = M / 'jobs' / f'{key}.json'
    if method == 'LGDM':   # depth composite in place of the render (user decision 2026-11-19)
        if not (M / 'renders' / key / 'receipt.json').exists():
            if not sh(gt_cpu(f'{key}-lgdm'.replace('_', '-').lower(), '/b151s/b151_lgdm_renders.py', 'site', run, site, cpus='4', mem='16g'),
                      OUT / 'logs' / f'post41_render_{key}.log'):
                return False
    elif not job.exists():
        dump(job, dict(site=site, prior=first, family=METHOD[method]['family'], key=key, ply=f'/b151/post/{run}/{site}.ply', box=box,
                       run=run, renderer=str(METHOD[method]['source']), image=METHOD[method]['image'], scientific_verdict=None))
    if not (M / 'renders' / key / 'receipt.json').exists():
        while gpu_free_mib() < 10 * 1024:
            time.sleep(120)
        if not sh(render_cmd(method, key), OUT / 'logs' / f'post41_render_{key}.log'):
            return False
    t2 = time.monotonic()
    tag = key.replace('_', '-').lower()
    root = M / 'meshes' / key
    wd = root / 'final_work'
    if not (root / 'final.json').exists():
        for step in ['prepare', 'plan']:
            if step == 'prepare' and (wd / 'inputs/meta.json').exists():
                continue
            if not sh(gt_cpu(f'{tag}-{step}', 'mesh_job.py', site, first, fam, step), OUT / 'logs' / f'post41_mesh_{key}.log'):
                return False
        plan = json.loads((wd / 'plan/layout.json').read_text())
        for tile in plan['tiles']:
            k = tile['k']
            if (wd / 'tiles' / f'tile{k}.json').exists():
                continue
            while avail_gb() < 40:
                time.sleep(120)
            if not sh(gt_cpu(f'{tag}-tile{k}', 'mesh_job.py', site, first, fam, f'tile:{k}'), OUT / 'logs' / f'post41_mesh_{key}.log'):
                return False
        for step in ['merge', 'finish']:
            if not sh(gt_cpu(f'{tag}-{step}', 'mesh_job.py', site, first, fam, step), OUT / 'logs' / f'post41_mesh_{key}.log'):
                return False
    t3 = time.monotonic()
    for prior in priors[1:]:       # 2DGS: the same mesh for the LoD2 rows
        k2 = f'{site}__{prior}__{fam}'
        r2 = M / 'meshes' / k2
        if not (r2 / 'final.json').exists():
            r2.mkdir(parents=True, exist_ok=True)
            if not (r2 / 'final.ply').exists():
                os.link(root / 'final.ply', r2 / 'final.ply')
            rec = json.loads((root / 'final.json').read_text())
            rec.update(shared_with=key, note='2DGS uses no prior: the mesh of the ALS key (hard link), scored with the LoD2 rows')
            dump(r2 / 'final.json', rec)
    for prior in priors:
        stem = f'{site}__{prior}'
        if not (M / 'scenes' / stem / 'distances' / f'{fam}.npz').exists():
            if not sh(gt_cpu(f'{stem}-{fam}-score'.replace('_', '-').lower(), 'score_new.py', site, prior, fam), OUT / 'logs' / f'post41_score_{stem}_{fam}.log'):
                return False
    t4 = time.monotonic()
    dump(OUT / 'post' / run / f'{site}_timing.json', dict(at=now().isoformat(), run=run, site=site, priors=priors, crop_seconds=t1 - t0, render_seconds=t2 - t1,
                                                        mesh_seconds=t3 - t2, score_seconds=t4 - t3, scientific_verdict=None))
    progress(f'4.1 {run} {site}: 끝 (자르기 {t1 - t0:.0f}s, 렌더 {t2 - t1:.0f}s, 메시 {t3 - t2:.0f}s, 채점 {t4 - t3:.0f}s)')
    return True


def run(name):
    res = [one(name, s) for s in SITES]
    dump(OUT / 'post' / name / 'done41.json', dict(at=now().isoformat(), run=name, sites=SITES, ok=res, scientific_verdict=None))
    return all(res)


def watch():
    c = json.loads((C / 'base151_v1.json').read_text())
    while True:
        pending = 0
        for r in c['training_order'] + ['b151_LGDM_ALS', 'b151_LGDM_LoD2']:
            if (OUT / 'post' / r / 'done41.json').exists():
                continue
            pending += 1
            if r.startswith('b151_LGDM') or (OUT / 'runs' / r / 'merged/point_cloud.ply').exists():
                run(r)
        if pending == 0 or (OUT / 'control/POST_STOP').exists():
            return
        time.sleep(600)


if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'mirror':
        mirror()
    elif mode == 'run':
        run(sys.argv[2])
    elif mode == 'watch':
        watch()
