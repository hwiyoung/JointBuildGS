"""PHD-MAIN-TRAINLOG-v1 concept video v2 (first cut, 2026-11-12): meshes of the comparison runs at their saved intermediate iterations. Host orchestration, no training.
The unchanged mesh+score code with a shadow root inside concept_v2 (writes only PH/.../concept_v2):
  render         RESCORE render_model.py (frozen 203 views of gtj/views/B173nb_b10.json, building box, SH degree 0, surf_depth) -> concept_v2/gtj/renders/<key>/
  prepare|plan|tile:k|merge|finish   GTJUDGE mesh_job (TSDF voxel 0.05 m, trunc 0.25 m, the inherited cleanup) via tl_mesh.py, shadow /gtjudge = concept_v2/gtj
  score          tl_mesh.score (GTJUDGE score_new + addendum11 normal_cylinder_1m), /tl = concept_v2 (score.json -> concept_v2/meshes/<family>/)
Families (each comparison run's saved states: nojudge_ALS_s0 point_cloud 15000/30000; imgonly_2dgs_s0 point_cloud 7000/30000):
  cmp_nojudge_15000  stage3 nojudge_ALS_s0 iteration_15000, renderer = its own r15 fork in jointbuildgs:geogs-conf-guided-v1 (as RESCORE baseline_30000)
  cmp_2dgs_7000      baselines imgonly_2dgs_s0 iteration_7000; its own image jointbuildgs:2dgs-official-f3e3b9f-v1 is not on this host, so the r27 fork renderer
                     is used only if chk_2dgs_30000 (the 30,000 state through the r27 renderer) reproduces RESCORE's own 2DGS_30000 renders (check step)
  cmp_nojudge_30000, cmp_2dgs_30000: the RESCORE final.ply linked into the shadow, score only (kept as record: RESCORE made them from 219 views = 203 real + 16 virtual)
  cmp_nojudge_30000_v203, cmp_2dgs_30000_v203: the same 30,000 states meshed here with the 203 real views, as every other mesh in the video
scientific_verdict: null"""
import json, os, subprocess, sys, time
from pathlib import Path
from launch import R, ART, PH, O, GPU_IMAGE, CPU_IMAGE, now, dump, run, SITE, PRIOR
V2 = O/'concept_v2'; SH = V2/'gtj'; RS = PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1'; STEM = f'{SITE}__{PRIOR}'
A_ = '/art/phase-payloads/phd'
FAM = {'chk_2dgs_30000': dict(ply=f'{A_}/main_baselines_v1/PHD-MAIN-BASELINES-v1/runs/{SITE}/imgonly_2dgs_s0/model/point_cloud/iteration_30000/point_cloud.ply', source='GeoGS-conf-guided-v1-r27'),
       'cmp_nojudge_15000': dict(ply=f'{A_}/main_stage3_v1/PHD-MAIN-STAGE3-v1/runs/{SITE}/nojudge_ALS_s0/model/point_cloud/iteration_15000/point_cloud.ply', source='GeoGS-conf-guided-v1-r15'),
       'cmp_2dgs_7000': dict(ply=f'{A_}/main_baselines_v1/PHD-MAIN-BASELINES-v1/runs/{SITE}/imgonly_2dgs_s0/model/point_cloud/iteration_7000/point_cloud.ply', source='GeoGS-conf-guided-v1-r27'),
       # RESCORE's 30,000 meshes used 219 views (203 real + 16 virtual); these two follow the 203-real-view rule of every other mesh in the video
       'cmp_nojudge_30000_v203': dict(ply=f'{A_}/main_stage3_v1/PHD-MAIN-STAGE3-v1/runs/{SITE}/nojudge_ALS_s0/model/point_cloud/iteration_30000/point_cloud.ply', source='GeoGS-conf-guided-v1-r15'),
       'cmp_2dgs_30000_v203': dict(ply=f'{A_}/main_baselines_v1/PHD-MAIN-BASELINES-v1/runs/{SITE}/imgonly_2dgs_s0/model/point_cloud/iteration_30000/point_cloud.ply', source='GeoGS-conf-guided-v1-r27')}
LINKED = {'cmp_nojudge_30000': f'{A_}/main_rescore_v1/PHD-MAIN-RESCORE-v1/meshes/B173nb_b10__ALS__baseline_30000/final.ply',
          'cmp_2dgs_30000': f'{A_}/main_rescore_v1/PHD-MAIN-RESCORE-v1/meshes/B173nb_b10__LoD2__2DGS_30000/final.ply'}
LOG = V2/'logs'
if os.environ.get('TL_CASE'):   # another case (launch.py TL_CASE): image-only 2DGS at 7,000 and 30,000 only, all real views (no virtual -> no _v203), r27 renderer as for B173;
    FAM = {'cmp_2dgs_7000': FAM['cmp_2dgs_7000'], 'cmp_2dgs_30000': FAM['cmp_2dgs_30000_v203']}; LINKED = {}   # TL_CMP_SHADOW = NVMe shadow root for these meshes
    SH = Path(os.environ['TL_CMP_SHADOW']) if os.environ.get('TL_CMP_SHADOW') else SH

def base(name, gpu, cpus, memory):
    cmd = ['nice', '-n', '19', 'docker', 'run', '--rm', '--read-only', '--network', 'none', '--name', name, '--user', f'{os.getuid()}:{os.getgid()}',
           '--cpus', str(cpus), '--memory', memory, '--memory-swap', memory, '--shm-size', '4g']
    return cmd + (['--gpus', f'device={gpu}'] if gpu is not None else ['--runtime', 'runc', '-e', 'NVIDIA_VISIBLE_DEVICES=void', '-e', 'CUDA_VISIBLE_DEVICES='])

def render_cmd(family, gpu):
    f = FAM[family]; cmd = base(f'jbgs-trainlog-cv2-render-{family}', gpu, 4, '32g')
    for e in ['PYTHONDONTWRITEBYTECODE=1', 'PYTHONUNBUFFERED=1', 'OMP_NUM_THREADS=1', 'TZ=Asia/Seoul', 'RESCORE_OUTPUT_ROOT=/gtjudge', 'RESCORE_DOC_ROOT=/docs',
              'RESCORE_RENDER_GPU_FRACTION=.25', 'TMPDIR=/gtjudge/tmp', 'MPLCONFIGDIR=/gtjudge/tmp/mpl', 'XDG_CACHE_HOME=/gtjudge/tmp/cache', *([f"TL_CASE={os.environ['TL_CASE']}"] if os.environ.get('TL_CASE') else [])]: cmd += ['-e', e]
    for s, d, m in [(R, '/repo', 'ro'), (ART, '/art', 'ro'), (R/'src/phd/forks'/f['source'], '/source', 'ro'), (SH, '/gtjudge', 'rw'),
                    (R/'configs/phd/main_rescore_v1', '/cfg', 'ro'), (V2/'rescore_docs', '/docs', 'rw')]: cmd += ['-v', f'{s}:{d}:{m}']
    return cmd + ['-w', '/gtjudge', '--entrypoint', '/bin/bash', GPU_IMAGE, '-c',
                  'if [ -f /opt/geogs/lib/libstdc++.so.6 ]; then export LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6; fi; exec python -B -u /repo/scripts/phd/main_rescore_v1/render_model.py "$0"',
                  f'/gtjudge/jobs/{STEM}__{family}.json']

def mesh_cmd(step, family):
    cmd = base(f'jbgs-trainlog-cv2-mesh-{step.replace(":", "")}-{family}'[:120], None, 12, '40g')
    for e in ['PYTHONDONTWRITEBYTECODE=1', 'PYTHONUNBUFFERED=1', 'OMP_NUM_THREADS=8', 'OPENBLAS_NUM_THREADS=1', 'MKL_NUM_THREADS=1', 'TMPDIR=/gtjudge/tmp',
              'MPLCONFIGDIR=/gtjudge/tmp/mpl', 'XDG_CACHE_HOME=/gtjudge/tmp/cache', 'TZ=Asia/Seoul', *([f"TL_CASE={os.environ['TL_CASE']}"] if os.environ.get('TL_CASE') else [])]: cmd += ['-e', e]
    for s, d, m in [(R, '/repo', 'ro'), (ART, '/art', 'ro'), (ART, '/artifacts/JointBuildGS', 'ro'), (PH, '/ph', 'ro'), (PH/'main_rescore_v1/PHD-MAIN-RESCORE-v1', '/out', 'ro'),
                    (PH/'main_release_v1/PHD-MAIN-RELEASE-v1', '/release', 'ro'), (SH, '/gtjudge', 'rw'), (R/'configs/phd/main_gtjudge_v1', '/cfg', 'ro'),
                    (V2/'gtj_docs', '/docs', 'rw'), (V2, '/tl', 'rw'), (R/'src/phd/forks/GeoGS-conf-guided-v1-r27', '/source', 'ro'), (Path('/usr/share/fonts/opentype/noto'), '/fonts', 'ro')]:
        cmd += ['-v', f'{s}:{d}:{m}']
    return cmd + ['-w', '/gtjudge', '--entrypoint', '/bin/bash', CPU_IMAGE, '-c', 'exec python -B -u /repo/scripts/phd/main_trainlog_v1/tl_mesh.py "$@"', 'tl_mesh', step] + ([family] if family else [])

def go(cmd, tag):
    LOG.mkdir(parents=True, exist_ok=True); log = LOG/f'{time.strftime("%Y%m%dT%H%M%S")}_{tag}.log'; rc, s = run(cmd, log)
    with (LOG/'timing.jsonl').open('a') as f: f.write(json.dumps(dict(at=now(), tag=tag, exit_code=rc, seconds=s, log=str(log)))+'\n')
    print(tag, rc, round(s), flush=True); return rc

def setup():
    for d in ['jobs', 'views', 'meshes', 'renders', 'tmp']: (SH/d).mkdir(parents=True, exist_ok=True)
    for d in [V2/'gtj_docs', V2/'rescore_docs']: d.mkdir(parents=True, exist_ok=True)
    src = (PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1/views' if os.environ.get('TL_CASE') else O/'gtj/views')/f'{SITE}.json'; dst = SH/'views'/f'{SITE}.json'
    if not dst.exists(): dst.write_bytes(src.read_bytes())
    view = json.loads(dst.read_text())
    for fam, f in FAM.items():
        p = SH/'jobs'/f'{STEM}__{fam}.json'
        if not p.exists(): dump(p, dict(key=f'{STEM}__{fam}', site=SITE, prior=PRIOR, family=fam, box=view['box'], ply=f['ply'], renderer_fork=f['source'], image=GPU_IMAGE, scientific_verdict=None))
    for fam, ply in LINKED.items():
        d = SH/'meshes'/f'{STEM}__{fam}'; d.mkdir(parents=True, exist_ok=True)
        if not (d/'final.ply').is_symlink(): os.symlink(ply, d/'final.ply')
    if go(mesh_cmd('shadow', ''), 'shadow'): raise SystemExit('shadow failed')

def mesh(fam):
    for st in ['prepare', 'plan']:
        if go(mesh_cmd(st, fam), f'{st}_{fam}'): raise SystemExit(f'{st} {fam} failed')
    n = len(json.loads((SH/'meshes'/f'{STEM}__{fam}'/'final_work/plan/plan.json').read_text())['tiles'])
    for k in range(n):
        if go(mesh_cmd(f'tile:{k}', fam), f'tile{k}_{fam}'): raise SystemExit(f'tile {k} {fam} failed')
    if go(mesh_cmd('merge', fam), f'merge_{fam}'):
        if go(mesh_cmd('recover', fam), f'recover_{fam}'): raise SystemExit(f'merge+recover {fam} failed')
    if go(mesh_cmd('finish', fam), f'finish_{fam}'): raise SystemExit(f'finish {fam} failed')

def job(kind, script, *args):
    """launch.command (same mounts and images) with the log in concept_v2/logs instead of the TRAINLOG logs folder."""
    from launch import command, VIDEO_IMAGE
    var = os.environ.get('CV2_VARIANT', ''); tag = f'{Path(script).stem}{"_"+var if var else ""}'   # CV2_VARIANT (cv2_frames test variant) passed into the container
    cmd = command(f'jbgs-trainlog-cv2-{tag.replace("_", "-")}-{"-".join(args)[:30]}'.rstrip('-').replace(',', '-'), script, list(args), image=VIDEO_IMAGE if kind == 'video' else None, cpus=12, memory='48g',
                  env=[f'CV2_VARIANT={var}'] if var else ())
    return go(cmd, f'{tag}_{"_".join(args)[:40]}')

if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] in ['cpu', 'video']: sys.exit(job(*a))
    if a[0] == 'setup': setup()
    elif a[0] == 'render': sys.exit(go(render_cmd(a[1], int(a[2])), f'render_{a[1]}'))
    elif a[0] == 'mesh': mesh(a[1])
    elif a[0] == 'score': sys.exit(go(mesh_cmd('score', a[1]), f'score_{a[1]}'))
    elif a[0] == 'resume_merge':   # the merge already failed once and its recover run was cut by a docker daemon restart: recover, finish, score
        fam = a[1]
        if go(mesh_cmd('recover', fam), f'recover_{fam}'): raise SystemExit(f'recover {fam} failed')
        if go(mesh_cmd('finish', fam), f'finish_{fam}'): raise SystemExit(f'finish {fam} failed')
        if go(mesh_cmd('score', fam), f'score_{fam}'): raise SystemExit(f'score {fam} failed')
        for fam in a[2:]:
            if fam in FAM: mesh(fam)
            if go(mesh_cmd('score', fam), f'score_{fam}'): raise SystemExit(f'score {fam} failed')
    elif a[0] == 'all':   # after the check: meshes then scores, one CPU job at a time
        for fam in a[1:]:
            if fam in FAM: mesh(fam)
            if go(mesh_cmd('score', fam), f'score_{fam}'): raise SystemExit(f'score {fam} failed')
