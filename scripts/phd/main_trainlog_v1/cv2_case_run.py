"""Host driver for the concept video of another case (TL_CASE=<site>__<prior>, 2026-11-13 B0_b10 x LoD2, user '그 이야기로 만들어'). Run after the case training
(launch.py train) has finished; every step skips what already exists, so a rerun continues. No training here; rules of every step unchanged.
  GPU (one at a time, GPU given): render_states.py for the frame states (renders/<n>, cameras.json) -> lineage_key.py ply <n> -> mesh render tl_<n> (launch.mesh,
       shadow = TL_SHADOW) -> cv2_mesh render of the 2DGS comparison states 7,000 and 30,000 (shadow = TL_CMP_SHADOW) -> concept_prep.py 30000 (camera inputs)
  CPU (two workers): prepare, plan, tiles, merge(+recover), finish, score of every family (NVMe shadows, the B173 lesson: HDD made meshing 3-6x slower)
  sync: the NVMe shadows -> payload (case gtj/ and concept_v2/gtj/), without final_work and tmp
  CPU: cv2_prep (discs) -> cv2_meshcol -> cv2_frames setup -> cv2_sec3 -> cv2_frames frames, contact, table -> cv2_video
Logs: <case payload>/logs/case_run.jsonl (step, seconds, exit code). scientific_verdict: null"""
import json, os, subprocess, sys, threading, time
from pathlib import Path
assert os.environ.get('TL_CASE') and os.environ.get('TL_SHADOW') and os.environ.get('TL_CMP_SHADOW'), 'set TL_CASE, TL_SHADOW, TL_CMP_SHADOW'
import launch as LA
import cv2_mesh as CM
STATES = ['0', '100', '300', '1000', '2000', '3000', '5000', '7000', '10000', '15000', '30000']
O = LA.O; RUNM = O/'runs'/LA.SITE/f'tl_{LA.SITE}_{LA.PRIOR}_s0'/os.environ.get('TL_ATTEMPT', 'attempt1')/'model'; SH = LA.SHADOW; CSH = CM.SH; LOG = O/'logs/case_run.jsonl'

def note(**kw):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a') as f: f.write(json.dumps(dict(at=LA.now(), **kw), ensure_ascii=False)+'\n')
    print(json.dumps(kw, ensure_ascii=False), flush=True)
def step(label, fn, *a, **kw):
    t = time.monotonic(); rc = fn(*a, **kw); note(step=label, seconds=round(time.monotonic()-t, 1), rc=rc)
    if rc: raise SystemExit(f'{label} failed ({rc})')

def gpu_phase(gpu):
    need = [n for n in STATES if not (O/'renders'/n/'render.json').exists()]
    if need: step('render_states', LA.job, 'gpu', 'render_states.py', *need, gpu=gpu, name='jbgs-trainlog-case-render-states')
    for n in STATES:
        if not (O/'ply'/f'{n}.ply').exists(): step(f'ply_{n}', LA.job, 'gpu', 'lineage_key.py', 'ply', n, gpu=gpu, name=f'jbgs-trainlog-case-ply-{n}')
    (SH/'views').mkdir(parents=True, exist_ok=True); v = SH/'views'/f'{LA.SITE}.json'; src = LA.PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1/views'/f'{LA.SITE}.json'
    if not v.exists(): v.write_bytes(src.read_bytes())   # the GTJUDGE view list of the site (all real views), as its FINALTRAIN_30000 / 2DGS_30000 meshes
    if not (SH/'scenes'/LA.STEM/'rows.npz').exists(): t = time.monotonic(); LA.mesh('shadow'); note(step='shadow', seconds=round(time.monotonic()-t, 1), rc=0)
    for n in STATES:
        if not (SH/'renders'/f'{LA.STEM}__tl_{n}'/'receipt.json').exists(): t = time.monotonic(); LA.mesh('render', f'tl_{n}', f'/tl/ply/{n}.ply', gpu=gpu); note(step=f'mesh_render_tl_{n}', seconds=round(time.monotonic()-t, 1), rc=0)
    if not (CSH/'views'/f'{LA.SITE}.json').exists(): step('cmp_setup', lambda: CM.setup() or 0)
    for fam in CM.FAM:
        if not (CSH/'renders'/f'{LA.STEM}__{fam}'/'receipt.json').exists(): step(f'cmp_render_{fam}', lambda f=fam: CM.go(CM.render_cmd(f, gpu), f'render_{f}'))
    if not (O/'concept/inputs.npz').exists(): step('concept_prep', LA.job, 'gpu', 'concept_prep.py', '30000', gpu=gpu, name='jbgs-trainlog-case-concept-prep')

def mesh_family(fam, cmp=False):
    done = (CM.V2 if cmp else O)/'meshes'/fam/'score.json'
    if done.exists(): return
    t = time.monotonic()
    if cmp: CM.mesh(fam); rc = CM.go(CM.mesh_cmd('score', fam), f'score_{fam}')
    else:
        for st in ['prepare', 'plan']: LA.mesh(st, fam)
        n = len(json.loads((SH/'meshes'/f'{LA.STEM}__{fam}'/'final_work/plan/plan.json').read_text())['tiles'])
        for k in range(n): LA.mesh(f'tile:{k}', fam)
        try: LA.mesh('merge', fam)
        except SystemExit: LA.mesh('recover', fam)
        for st in ['finish', 'score']: LA.mesh(st, fam)
        rc = 0
    note(step=f'mesh_{fam}', seconds=round(time.monotonic()-t, 1), rc=rc)
    if rc: raise SystemExit(f'mesh {fam} failed')

def cpu_phase(workers=2):
    items = [(f'tl_{n}', False) for n in STATES[::-1]] + [(f, True) for f in CM.FAM]; errs = []
    def w(lst):
        for fam, cmp in lst:
            try: mesh_family(fam, cmp)
            except SystemExit as e: errs.append(str(e)); note(step=f'mesh_{fam}', error=str(e))
    th = [threading.Thread(target=w, args=(items[i::workers],)) for i in range(workers)]
    for t in th: t.start()
    for t in th: t.join()
    if errs: raise SystemExit('; '.join(errs))

def sync():
    for src, dst in ((SH, O/'gtj'), (CSH, CM.V2/'gtj')):
        dst.mkdir(parents=True, exist_ok=True); t = time.monotonic()
        rc = subprocess.run(['rsync', '-a', '--exclude', 'final_work/', '--exclude', 'tmp/', f'{src}/', f'{dst}/']).returncode; note(step=f'sync_{dst.name}_{dst.parent.name}', seconds=round(time.monotonic()-t, 1), rc=rc)
        if rc: raise SystemExit('sync failed')

def video_phase():
    for args in (('cv2_prep.py',), ('cv2_meshcol.py', ','.join([f'ours_{n}' for n in STATES]+['2dgs_7000', '2dgs_30000'])), ('cv2_frames.py', 'setup'), ('cv2_sec3.py',),
                 ('cv2_frames.py', 'frames'), ('cv2_frames.py', 'contact'), ('cv2_frames.py', 'table')):
        step('_'.join(a[:20] for a in args)[:60], LA.job, 'cpu', *args, cpus=12, memory='48g')
    step('video', LA.job, 'video', 'cv2_video.py')

if __name__ == '__main__':
    what = sys.argv[1:] or ['gpu', 'cpu', 'sync', 'video']; gpu = int(os.environ.get('TL_GPU', '1'))
    assert (RUNM.parent/'TRAINING_COMPLETE.json').exists(), f'training not complete: {RUNM.parent}'
    note(step='start', what=what, gpu=gpu, shadow=str(SH), cmp_shadow=str(CSH))
    if 'gpu' in what: gpu_phase(gpu)
    if 'cpu' in what: cpu_phase()
    if 'sync' in what: sync()
    if 'video' in what: video_phase()
    note(step='done', what=what)
