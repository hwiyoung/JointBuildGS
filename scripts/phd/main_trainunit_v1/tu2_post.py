"""PHD-MAIN-TRAINUNIT-v2 post-processing on the host: the v1 tu_post functions (unchanged GTJUDGE render -> mesh -> score)
with the v2 payload as /tu and its own GTJUDGE mirror PH2/gt. Render runs only on GPU 1 and only when nvidia-smi -i 1 shows no
other compute process. Mesh/score are CPU containers, run when no training of this task runs (the queue calls them in order).

  python3 tu2_post.py mirror                   # GTJUDGE links + links to the v1 scores (ef_s0, ef_s1, cellsef_ALS_s0) for ALS
  python3 tu2_post.py render <key> [sites]     # crop + render (GPU 1)
  python3 tu2_post.py finish <key> [sites]     # mesh + score (CPU; tolerance merge only where the unchanged merge stops on roundoff)
keys: campusef30k_ALS_s0 (v1 run) | cells9ef_ALS_s0 (merged nine cells) | ef_<site>_LoD2 | efs1_<site>_LoD2
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import tu_host as H
import tu2_host as Q   # sets H.D to the v2 docs

import tu_post as P
P.TU = Q.TU
P.M = Q.TU / 'gt'
import tu_post_fix as PF   # noqa: E402  (binds the patched M / TU)
assert PF.M == P.M and PF.TU == P.TU

TU, TU1, M = Q.TU, Q.TU1, P.M
R = H.R
SITES = H.SITES


def tu2_cpu(tag, *args, cpus='8', mem='32g'):
    return ['bash', str(R / 'scripts/phd/main_trainunit_v1/run2_cpu.sh'), tag, cpus, mem, *map(str, args)]


def mirror():
    P.mirror()
    v1 = '/art/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1/gt/scenes'
    n = 0
    for site in SITES:
        stem = f'{site}__ALS'
        for fam in ['ef_s0', 'ef_s1', 'cellsef_ALS_s0', 'cellsef1fix_ALS_s0']:
            for suf in ['.npz', '_samples.npz', '.json']:
                if (TU1 / 'gt/scenes' / stem / 'distances' / f'{fam}{suf}').exists():
                    P.link(f'{v1}/{stem}/distances/{fam}{suf}', M / 'scenes' / stem / 'distances' / f'{fam}{suf}')
                    n += 1
    print('MIRROR2', n, flush=True)


def ply_of(key):
    """(prior, sites, host ply, container ply)."""
    if key == 'campusef30k_ALS_s0':
        r = json.loads((TU1 / 'runs/ef' / key / 'receipt.json').read_text())
        assert r['status'] == 'TRAINING_COMPLETE'
        rel = f'runs/ef/{key}/attempt{r["attempts"][-1]["attempt"]}/model/point_cloud/iteration_30000/point_cloud.ply'
        return 'ALS', SITES, TU1 / rel, '/tu1/' + rel
    if key == 'cells9ef_ALS_s0':
        rel = 'runs/cells9ef_ALS_s0/merged/point_cloud.ply'
        return 'ALS', SITES, TU / rel, '/tu/' + rel
    tag, a, b, prior = key.split('_')
    run = TU / 'runs' / f'{a}ef_{prior}_{"s1" if tag == "efs1" else "s0"}'
    r = json.loads((run / 'receipt.json').read_text())
    assert r['status'] == 'TRAINING_COMPLETE', (run, r['status'])
    rel = str((run / f'attempt{r["attempts"][-1]["attempt"]}' / 'model/point_cloud/iteration_30000/point_cloud.ply').relative_to(TU))
    return prior, [f'{a}_{b}'], TU / rel, '/tu/' + rel


def wait_gpu():
    while Q.gpu_busy(Q.GPU):
        time.sleep(120)


def render(key, only=None):
    prior, sites, ply, cply = ply_of(key)
    sites = [s for s in sites if not only or s in only.split(',')]
    fam = P.family_of(key)
    ok = []
    for site in sites:
        crop = TU / 'post' / key / f'{site}.ply'
        t0 = time.monotonic()
        if not crop.exists():
            P.sh(tu2_cpu(f'crop-{key}-{site}'.replace('_', '-').lower(), 'tu_postcpu.py', 'crop', cply, site, '/tu/' + str(crop.relative_to(TU))),
                 TU / 'logs' / f'crop-{key}-{site}.log')
        t1 = time.monotonic()
        stemkey = f'{site}__{prior}__{fam}'
        if not (M / 'renders' / stemkey / 'receipt.json').exists():
            wait_gpu()
            cmd = P.gt_gpu(Q.GPU, f'{stemkey.replace("_", "-").lower()}', 'mesh_job.py', site, prior, fam, 'render', '/tu/' + str(crop.relative_to(TU)), site=site)
            P.sh(cmd, M / 'logs' / f'render-{stemkey}.log')
        t2 = time.monotonic()
        good = (M / 'renders' / stemkey / 'receipt.json').exists()
        ok.append(good)
        H.dump(TU / 'post' / key / f'{site}_render_timing.json', dict(at=H.now().isoformat(), key=key, site=site, prior=prior, family=fam, ok=good,
               crop_seconds=t1 - t0, render_seconds=t2 - t1, gpu=Q.GPU, scientific_verdict=None))
        Q.progress(f'후처리 {key} {site}: 자르기·렌더 {"완료" if good else "실패"} ({t1 - t0:.0f}s, {t2 - t1:.0f}s)')
    return all(ok)


def finish(key, only=None):
    prior, sites, _, _ = ply_of(key)
    sites = [s for s in sites if not only or s in only.split(',')]
    fam = P.family_of(key)
    ok = []
    for site in sites:
        t0 = time.monotonic()
        good = P.mesh(key, site, prior)
        t1 = time.monotonic()
        tol = False
        if not good:
            mlog = (M / 'logs' / f'mesh-{site}__{prior}-{fam}'.replace('_', '-').lower()).with_suffix('.log')
            wd = M / 'meshes' / f'{site}__{prior}__{fam}' / 'final_work'
            tiles_done = (wd / 'plan/layout.json').exists() and all((wd / 'tiles' / f'tile{t["k"]}.json').exists()
                                                                   for t in json.loads((wd / 'plan/layout.json').read_text())['tiles'])
            if tiles_done and not (wd / 'merged.json').exists():
                PF.main(key, site, prior)     # tolerance merge (v1 issue: roundoff stop of the unchanged merge), then finish + score
                tol = True
        good = (M / 'scenes' / f'{site}__{prior}' / 'distances' / f'{fam}.npz').exists() or P.score(key, site, prior)
        t2 = time.monotonic()
        ok.append(bool(good))
        H.dump(TU / 'post' / key / f'{site}_timing.json', dict(at=H.now().isoformat(), key=key, site=site, prior=prior, family=fam, ok=bool(good),
               mesh_seconds=t1 - t0, score_seconds=t2 - t1, tolerance_merge=tol, scientific_verdict=None))
        Q.progress(f'후처리 {key} {site}: 메시·채점 {"완료" if good else "실패"} (메시 {t1 - t0:.0f}s, 채점 {t2 - t1:.0f}s' + (', 허용 합치기' if tol else '') + ')')
    H.dump(TU / 'post' / key / 'done.json', dict(at=H.now().isoformat(), key=key, sites=sites, ok=ok, scientific_verdict=None))
    return all(ok)


if __name__ == '__main__':
    mode = sys.argv[1]
    dict(mirror=mirror, render=render, finish=finish)[mode](*sys.argv[2:])
