"""Mesh + score with the unchanged GTJUDGE/RESCORE code, redirected to a task-local shadow root.

Container mounts (launch.py meshjob): /gtjudge = PH/main_trainlog_v1/.../gtj (rw shadow; inputs are symlinks into /art),
/cfg = configs/phd/main_gtjudge_v1 (ro), /docs = TRAINLOG docs/gtj_scratch (rw), /tl = TRAINLOG payload.
Steps: shadow | render <family> <ply> (GPU) | prepare|plan|tile:k|merge|finish <family> (CPU) | score <family> (CPU).
Score = GTJUDGE score_new.py distances + addendum11 rule (normal lines; normal_cylinder_1m accuracy) via add2_scores.metric_rows."""
import sys, os, time, json, gc
from pathlib import Path
sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
import numpy as np
SITE, PRIOR = 'B173nb_b10', 'ALS'; STEM = SITE+'__'+PRIOR
G = Path('/art/phase-payloads/phd/main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1')
SH = Path('/gtjudge')

def shadow():
    for rel in ['reference/B173nb_b10/dense.npz', 'reference/B173nb_b10/normal_points.npz', 'scenes/B173nb_b10__ALS/rows.npz', 'scenes/B173nb_b10__ALS/stage1_cells.npz']:
        dst = SH/rel; dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists(): os.symlink(G/rel, dst)
    for d in ['jobs', 'meshes', 'renders', 'scenes/B173nb_b10__ALS/distances', 'timing', 'bin', 'tmp']: (SH/d).mkdir(parents=True, exist_ok=True)
    print('SHADOW_READY', flush=True)

def score(family):
    from common import loadz, savez, dump, now, sha, O
    import score_new
    from cylinder import Cylinder
    from add2_scores import metric_rows
    t0 = time.monotonic(); score_new.main(SITE, PRIOR, family); t1 = time.monotonic()
    root = O/'scenes'/STEM; row = loadz(root/'rows.npz'); cell = loadz(root/'stage1_cells.npz')
    z = loadz(root/'distances'/f'{family}.npz'); q = loadz(root/'distances'/f'{family}_samples.npz', ['xyz', 'normal']); P, normal = q['xyz'], q['normal']
    ref = loadz(O/'reference'/SITE/'dense.npz', ['xyz', 'radius']); tree = Cylinder(ref['xyz']); del ref
    N = len(z['sample_s']); steep = abs(normal[:, 2]) < .5; wall = np.zeros(N, bool)
    oldeligible = z['sample_eligible'].astype(bool); oldfinite = np.isfinite(z['sample_s']); observed = oldeligible.copy(); missing = np.flatnonzero(~oldeligible)
    nu = normal.astype(float); nu /= np.linalg.norm(nu, axis=1)[:, None]
    for s0 in range(0, len(missing), 100000):  # identical to add11.process observation/eligibility loop
        ids = missing[s0:s0+100000]; lim = np.where(wall[ids], 5., 10.); _, found = tree.query(P[ids], nu[ids], lim, 1.); hit = found >= 0; observed[ids] = hit
        need = ids[hit & ~steep[ids] & ~oldfinite[ids]]
        if len(need): s, _ = tree.query(P[need], nu[need], np.where(wall[need], 5., 10.), .05); z['sample_s'][need] = s
    tree.close(); z['sample_observed_cylinder_1m'] = observed
    rows = metric_rows(SITE, PRIOR, [family], True, prepared=dict(row=row, cells=cell, scores={family: z}, steep={family: steep}), accuracy_rule='normal_cylinder_1m', extended=True)
    savez(root/'distances'/f'{family}_observed.npz', observed=observed, sample_s=z['sample_s'], steep=steep)
    out = Path('/tl/meshes')/family; out.mkdir(parents=True, exist_ok=True)
    dump(out/'score.json', dict(at=now(), family=family, rows=rows, seconds_distance=t1-t0, seconds_total=time.monotonic()-t0,
        rule='GTJUDGE score_new + addendum11 normal_cylinder_1m via add2_scores.metric_rows', scientific_verdict=None))
    print('SCORED', family, [(r['case_id'], r['completeness_pct'], r['accuracy_pct']) for r in rows], flush=True)

def main(step, family=None, ply=None):
    if step == 'shadow': return shadow()
    if step == 'score': return score(family)
    import mesh_job
    mesh_job.main(SITE, PRIOR, family, step, ply)

if __name__ == '__main__': main(*sys.argv[1:])
