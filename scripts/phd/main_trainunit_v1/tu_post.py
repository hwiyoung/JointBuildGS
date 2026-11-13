"""Host side post-processing of TRAINUNIT runs with the unchanged GTJUDGE mesh rule and scorer.

GTJUDGE scripts run unchanged with /gtjudge = PH/main_trainunit_v1/.../gt, a mirror holding read-only links
(container paths) to the GTJUDGE inputs they read (reference, views, rows, cells, baseline distances).

  python3 tu_post.py mirror
  python3 tu_post.py run <run_key>            # crop -> render (GPU when free memory allows) -> mesh -> score, per site
  python3 tu_post.py watch                    # loop over control/post_requests
run_key: seed1_<site>_<prior> | campus30k_<prior>_s0 | cells_<prior>_s0 | ef_B0_b10_ALS (addendum 12, family ef_s0)
"""
import concurrent.futures
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from tu_host import ART, C, D, FT, IMAGE, KST, PH, R, S0, SITES, TU, dump, issue, now, progress

G = PH / 'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
GC = PH / 'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
RS = PH / 'main_rescore_v1/PHD-MAIN-RESCORE-v1'
RL = PH / 'main_release_v1/PHD-MAIN-RELEASE-v1'
M = TU / 'gt'
CG = '/art/phase-payloads/phd/main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
EXP = Path('/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp')
# GTJUDGE -> RESCORE geometry imports scripts/phd/main_dist71_v1 and main_fill_v1, which exist only untracked in the exp
# checkout. GTJUDGE containers therefore see the exp checkout's scripts/phd (read-only; same commit 40e57e60 + those folders).
EXTRA = ['-v', f'{EXP}/scripts/phd:/repo/scripts/phd:ro']
BASE_METHODS = ['prior', 'mvs', 'fusion', 'baseline_30000', 'GeoGS_30000', '2DGS_30000', 'CDGS_30000', 'FINALTRAIN_30000']
PRIORS = ['ALS', 'LoD2']


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


def gt_cpu(tag, script, *args, cpus='6', mem='32g'):
    cmd = ['nice', '-n', '15', 'docker', 'run', '--rm', '--read-only', '--network', 'none', '--runtime', 'runc',
           '--name', f'jbgs-trainunit-gt-{tag}', '--user', f'{os.getuid()}:{os.getgid()}', '--cpus', cpus, '--memory', mem, '--memory-swap', mem,
           '-e', 'CUDA_VISIBLE_DEVICES=', '-e', 'NVIDIA_VISIBLE_DEVICES=void', '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'PYTHONUNBUFFERED=1',
           '-e', 'OMP_NUM_THREADS=2', '-e', 'OPENBLAS_NUM_THREADS=1', '-e', 'MKL_NUM_THREADS=1',
           '-e', 'TMPDIR=/gtjudge/tmp', '-e', 'MPLCONFIGDIR=/gtjudge/tmp/mpl', '-e', 'XDG_CACHE_HOME=/gtjudge/tmp/cache', '-e', 'TZ=Asia/Seoul',
           '-e', f'GTJUDGE_COMMIT={subprocess.run(["git", "-C", str(R), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()}',
           '-e', 'GTJUDGE_IMAGE=jointbuildgs:dev',
           '-v', f'{R}:/repo:ro', '-v', f'{ART}:/art:ro', '-v', f'{ART}:/artifacts/JointBuildGS:ro', '-v', f'{PH}:/ph:ro',
           '-v', f'{RS}:/out:ro', '-v', f'{RL}:/release:ro', '-v', f'{M}:/gtjudge:rw', '-v', f'{TU}:/tu:ro',
           '-v', f'{R}/configs/phd/main_gtjudge_v1:/cfg:ro', '-v', f'{M}/docs:/docs:rw', *EXTRA,
           '-v', '/usr/share/fonts/opentype/noto:/fonts:ro', '-w', '/gtjudge', '--entrypoint', 'nice', 'jointbuildgs:dev', '-n', '19', 'python', '-B', '-u',
           f'/repo/scripts/phd/main_gtjudge_v1/{script}', *map(str, args)]
    return cmd


def gt_gpu(gpu, tag, script, *args, site='R1rep_b10'):
    cmd = ['docker', 'run', '--rm', '--read-only', '--network', 'none', '--name', f'jbgs-trainunit-gtgpu-{tag}', '--gpus', f'device={gpu}',
           '--user', f'{os.getuid()}:{os.getgid()}', '--cpus', '8', '--memory', '40g', '--memory-swap', '40g', '--shm-size', '4g']
    for e in ['PYTHONDONTWRITEBYTECODE=1', 'PYTHONUNBUFFERED=1', 'OMP_NUM_THREADS=4', 'OPENBLAS_NUM_THREADS=1',
              'PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True', f'JBGS_SPLIT_JSON=/p/fork_inputs/s61/{site}/split.json',
              'TMPDIR=/gtjudge/tmp', 'MPLCONFIGDIR=/gtjudge/tmp/mpl', 'XDG_CACHE_HOME=/gtjudge/tmp/cache', 'TORCH_HOME=/weights/torch', 'TZ=Asia/Seoul']:
        cmd += ['-e', e]
    mounts = [(R, '/repo', 'ro'), (ART, '/art', 'ro'), (ART, '/artifacts/JointBuildGS', 'ro'), (PH, '/ph', 'ro'), (RS, '/out', 'ro'),
              (M, '/gtjudge', 'rw'), (R / 'configs/phd/main_gtjudge_v1', '/cfg', 'ro'), (M / 'docs', '/docs', 'rw'), (S0, '/p', 'ro'), (S0, '/s0', 'ro'),
              (TU, '/tu', 'ro'), (R / 'src/phd/forks/GeoGS-conf-guided-v1-r23', '/source', 'ro'),
              (PH / 'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights', '/weights', 'ro')]
    for s, d, m in mounts:
        cmd += ['-v', f'{s}:{d}:{m}']
    cmd += EXTRA
    return cmd + ['-w', '/source', '--entrypoint', 'python', IMAGE, '-B', '-u', f'/repo/scripts/phd/main_gtjudge_v1/{script}', *map(str, args)]


def tu_cpu(tag, *args, cpus='8', mem='32g'):
    return ['bash', str(R / 'scripts/phd/main_trainunit_v1/run_cpu.sh'), tag, cpus, mem, *map(str, args)]


def sh(cmd, log):
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    for attempt in [1, 2]:
        with open(log, 'a') as f:
            f.write(f'\n### {now()} attempt {attempt}\n')
            f.flush()
            rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
        if rc == 0:
            return True
    issue(f'후처리 명령 2회 실패: {" ".join(cmd[-6:])} (기록 {log})')
    return False


def family_of(key):
    if key.startswith('seed1_'):
        return 'seed1_s1'
    if key.startswith('ef_'):
        return 'ef_s0'   # addendum 12: elongation-filter repeat of the FINALTRAIN seed-0 run
    return key  # campus30k_<prior>_s0 / cells_<prior>_s0


def runs_of(key):
    """(prior, sites, model ply path on host) of a run key; None if not complete."""
    if key.startswith('seed1_'):
        _, a, b, prior = key.split('_')
        site = f'{a}_{b}'
        rec = TU / 'runs' / site / f'seed1_{prior}' / 'receipt.json'
        sites = [site]
    elif key.startswith('ef_'):
        _, a, b, prior = key.split('_')
        site = f'{a}_{b}'
        rec = TU / 'runs/ef' / f'{a}ef_{prior}_s0' / 'receipt.json'
        sites = [site]
    elif key.startswith('campus'):
        prior = key.split('_')[1]
        rec = TU / 'runs/campus' / key / 'receipt.json'
        sites = SITES
    else:
        prior = key.split('_')[1]
        merged = TU / 'runs/cells' / key / 'merged/point_cloud.ply'
        return prior, SITES, merged if merged.exists() else None
    if not rec.exists():
        return prior, sites, None
    r = json.loads(rec.read_text())
    if r['status'] != 'TRAINING_COMPLETE':
        return prior, sites, None
    att = r['attempts'][-1]['attempt']
    ply = rec.parent / f'attempt{att}' / 'model/point_cloud/iteration_30000/point_cloud.ply'
    return prior, sites, ply


def gpu_free_mb(gpu):
    out = subprocess.run(['nvidia-smi', '-i', str(gpu), '--query-gpu=memory.free', '--format=csv,noheader,nounits'], capture_output=True, text=True).stdout
    return int(out.strip().splitlines()[0])


def big_run_gpus():
    """GPUs running a campus training of this task: no render there (its memory peak is a result). Cell runs are site-sized."""
    out = set()
    for launch in list((TU / 'runs/campus').glob('*/attempt*/launch.json')):
        if not (launch.parent / 'receipt.json').exists():
            out.add(int(json.loads(launch.read_text())['gpu']))
    return out


def render(key, site, prior, ply_container):
    fam = family_of(key)
    stemkey = f'{site}__{prior}__{fam}'
    if (M / 'renders' / stemkey / 'receipt.json').exists():
        return True
    while True:
        big = big_run_gpus()
        frees = [(gpu_free_mb(g), g) for g in [0, 1] if g not in big]
        best = max(frees) if frees else (0, None)
        if best[0] >= 12000:
            break
        time.sleep(120)
    gpu = best[1]
    cmd = gt_gpu(gpu, f'{stemkey.replace("_", "-").lower()}', 'mesh_job.py', site, prior, fam, 'render', ply_container, site=site)
    return sh(cmd, M / 'logs' / f'render-{stemkey}.log')


def mesh(key, site, prior):
    fam = family_of(key)
    stem = f'{site}__{prior}'
    root = M / 'meshes' / f'{stem}__{fam}'
    wd = root / 'final_work'
    if (root / 'final.json').exists():
        return True
    tag = f'{stem}-{fam}'.replace('_', '-').lower()
    for step in ['prepare', 'plan']:
        if step == 'prepare' and (wd / 'inputs/meta.json').exists():
            continue
        if not sh(gt_cpu(f'{tag}-{step}', 'mesh_job.py', site, prior, fam, step), M / 'logs' / f'mesh-{tag}.log'):
            return False
    plan = json.loads((wd / 'plan/layout.json').read_text())
    for tile in plan['tiles']:
        k = tile['k']
        if (wd / 'tiles' / f'tile{k}.json').exists():
            continue
        if not sh(gt_cpu(f'{tag}-tile{k}', 'mesh_job.py', site, prior, fam, f'tile:{k}'), M / 'logs' / f'mesh-{tag}.log'):
            return False
    for step in ['merge', 'finish']:
        if not sh(gt_cpu(f'{tag}-{step}', 'mesh_job.py', site, prior, fam, step), M / 'logs' / f'mesh-{tag}.log'):
            return False
    return True


def score(key, site, prior):
    fam = family_of(key)
    stem = f'{site}__{prior}'
    if (M / 'scenes' / stem / 'distances' / f'{fam}.npz').exists():
        return True
    tag = f'{stem}-{fam}'.replace('_', '-').lower()
    return sh(gt_cpu(f'{tag}-score', 'score_new.py', site, prior, fam), M / 'logs' / f'score-{tag}.log')


def one_site(key, site, prior, ply):
    start = time.monotonic()
    fam = family_of(key)
    crop = TU / 'post' / key / f'{site}.ply'
    if not crop.exists():
        if not sh(tu_cpu(f'crop-{key}-{site}'.replace('_', '-').lower(), 'tu_postcpu.py', 'crop', '/tu/' + str(ply.relative_to(TU)), site, '/tu/' + str(crop.relative_to(TU))),
                  TU / 'logs' / f'crop-{key}-{site}.log'):
            return False
    t1 = time.monotonic()
    ok = render(key, site, prior, '/tu/' + str(crop.relative_to(TU)))
    t2 = time.monotonic()
    ok = ok and mesh(key, site, prior)
    t3 = time.monotonic()
    ok = ok and score(key, site, prior)
    t4 = time.monotonic()
    dump(TU / 'post' / key / f'{site}_timing.json', dict(at=now().isoformat(), key=key, family=fam, site=site, prior=prior, ok=bool(ok),
         crop_seconds=t1 - start, render_seconds=t2 - t1, mesh_seconds=t3 - t2, score_seconds=t4 - t3, scientific_verdict=None))
    progress(f'후처리 {key} {site}: {"완료" if ok else "실패"} (자르기 {t1-start:.0f}s, 렌더 {t2-t1:.0f}s, 메시 {t3-t2:.0f}s, 채점 {t4-t3:.0f}s)')
    return ok


def run(key):
    prior, sites, ply = runs_of(key)
    if ply is None:
        print('NOT_READY', key, flush=True)
        return False
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        res = list(pool.map(lambda s: one_site(key, s, prior, ply), sites))
    dump(TU / 'post' / key / 'done.json', dict(at=now().isoformat(), key=key, sites=sites, ok=res, scientific_verdict=None))
    return all(res)


def watch():
    """Post-process finished runs; cells are merged when all four cells of a prior are complete."""
    done = set()
    while True:
        keys = []
        for site in SITES:
            for prior in PRIORS:
                keys.append(f'seed1_{site}_{prior}')
        for prior in PRIORS:
            keys.append(f'campus30k_{prior}_s0')
            ck = f'cells_{prior}_s0'
            cells = TU / 'runs/cells' / ck
            if not (cells / 'merged/point_cloud.ply').exists():
                recs = [cells / f'cell{k}/receipt.json' for k in range(4)]
                if all(r.exists() for r in recs) and all(json.loads(r.read_text())['status'] == 'TRAINING_COMPLETE' for r in recs):
                    sh(tu_cpu(f'merge-{ck}'.replace('_', '-').lower(), 'tu_postcpu.py', 'merge', prior, cpus='8', mem='48g'), TU / 'logs' / f'merge-{ck}.log')
            keys.append(ck)
        for key in keys:
            if key in done or (TU / 'post' / key / 'done.json').exists():
                done.add(key)
                continue
            if runs_of(key)[2] is not None:
                run(key)
                done.add(key)
        if (TU / 'control/POST_STOP').exists():
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
    else:
        raise ValueError(mode)
