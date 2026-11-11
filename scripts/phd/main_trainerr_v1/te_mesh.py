"""Mesh + score with the unchanged GTJUDGE/RESCORE code, redirected to the task-local shadow root /gtjudge (TRAINLOG tl_mesh.py generalised).
Container (launch.py gtjcmd): /gtjudge = PH/main_trainerr_v1/.../gtj (rw shadow; inputs are read-only symlinks), /cfg = configs/phd/main_gtjudge_v1 (ro),
/te = TRAINERR payload. Steps: shadow <stem> | render <stem> <family> <ply> (GPU) | prepare|plan|tile:k|merge|finish <stem> <family> (CPU)
| score <stem> <family> (CPU) | clean <stem> <family>.
Score = GTJUDGE score_new.py distances + addendum11 process() rule for direct samples (wall from sample tau for LoD2, steep |nz|<0.5 for ALS,
normal_cylinder_1m accuracy) via add2_scores.metric_rows; per-point arrays in the addendum11/12 layout."""
import sys, os, time, json, gc, shutil
from pathlib import Path
sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
import numpy as np
G = Path('/art/phase-payloads/phd/main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1')
SH = Path('/gtjudge')

def shadow(stem):
    site = stem.split('__')[0]
    for rel in [f'reference/{site}/dense.npz', f'reference/{site}/normal_points.npz', f'scenes/{stem}/rows.npz', f'scenes/{stem}/stage1_cells.npz']:
        dst = SH/rel; dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists(): os.symlink(G/rel, dst)
    for d in ['jobs', 'meshes', 'renders', f'scenes/{stem}/distances', 'timing', 'bin', 'tmp', 'views']: (SH/d).mkdir(parents=True, exist_ok=True)
    print('SHADOW_READY', stem, flush=True)

def score(stem, family):
    from common import loadz, savez, dump, now, sha, O
    import score_new
    from cylinder import Cylinder
    from add2_scores import metric_rows
    import csv
    site, prior = stem.split('__'); t0 = time.monotonic(); score_new.main(site, prior, family); t1 = time.monotonic()
    root = O/'scenes'/stem; row = loadz(root/'rows.npz'); cell = loadz(root/'stage1_cells.npz')
    z = loadz(root/'distances'/f'{family}.npz'); q = loadz(root/'distances'/f'{family}_samples.npz', ['xyz', 'normal']); P, normal = q['xyz'], q['normal']
    ref = loadz(O/'reference'/site/'dense.npz', ['xyz']); tree = Cylinder(ref['xyz']); del ref
    N = len(z['sample_s']); steep = (abs(normal[:, 2]) < .5) if prior == 'ALS' else np.zeros(N, bool)
    if prior == 'ALS': wall = np.zeros(N, bool)
    else:
        with open('/repo/docs/experiments/phd/main_release_v1/tables/stage0/tau_values.csv') as f: tau = next(t for t in csv.DictReader(f) if t['site'] == site and t['prior'] == prior)
        wall = np.isclose(z['sample_tau'], float(tau['wall_tau_m']), rtol=0, atol=1e-6); assert np.all(wall | np.isclose(z['sample_tau'], float(tau['roof_tau_m']), rtol=0, atol=1e-6))
    oldeligible = z['sample_eligible'].astype(bool); oldfinite = np.isfinite(z['sample_s']); observed = oldeligible.copy(); missing = np.flatnonzero(~oldeligible)
    nu = normal.astype(float); nu /= np.linalg.norm(nu, axis=1)[:, None]
    for s0 in range(0, len(missing), 100000):  # identical to add11.process observation/eligibility loop
        ids = missing[s0:s0+100000]; lim = np.where(wall[ids], 5., 10.); _, found = tree.query(P[ids], nu[ids], lim, 1.); hit = found >= 0; observed[ids] = hit
        need = ids[hit & ~steep[ids] & ~oldfinite[ids]]
        if len(need): s, _ = tree.query(P[need], nu[need], np.where(wall[need], 5., 10.), .05); z['sample_s'][need] = s
    tree.close(); z['sample_observed_cylinder_1m'] = observed
    rows = metric_rows(site, prior, [family], True, prepared=dict(row=row, cells=cell, scores={family: z}, steep={family: steep}), accuracy_rule='normal_cylinder_1m', extended=True)
    lab = cell['case_id']; ix = z['sample_reference_row']; ok = ix >= 0; qc = np.full(N, -1, 'i1'); qc[ok] = lab[ix[ok]]
    eligible = observed & ~steep; hitm = np.isfinite(z['sample_s']); state = np.zeros(N, 'u1'); state[~oldeligible & eligible] = 1; state[eligible & ~hitm] = 4; state[~observed] = 2; state[steep] = 3
    s_res = -z['sample_s']; within = hitm & (np.abs(z['sample_s']) <= z['sample_tau'])  # addendum11/12 bit: distance only (accuracy = eligible_new & within)
    rs = z['row_s']; rwithin = np.isfinite(rs) & (np.abs(rs) <= row['row_tau_m'])
    out = Path('/te/meshes')/f'{stem}__{family}'; out.mkdir(parents=True, exist_ok=True)
    savez(out/'points.npz', reference__s_m=rs.astype('f4'), reference__state=(~np.isfinite(rs)).astype('u1'), reference__within_tau1=rwithin.astype('u1'), reference__offset=z['row_offset'],
          result__xyz=P.astype('f4'), result__normal=normal.astype('f4'), result__case_id=qc, result__wall=wall.astype('u1'), result__reference_row_id=ix.astype('i4'),
          result__tau_m=z['sample_tau'].astype('f4'), result__s_m=s_res.astype('f4'), result__state=state, result__eligible_new=eligible.astype('u1'),
          result__eligible_old=(oldeligible & ~steep).astype('u1'), result__within_tau1=within.astype('u1'), result__owner=loadz(root/'distances'/f'{family}_samples.npz', ['owner'])['owner'])
    dump(out/'score.json', dict(at=now(), stem=stem, family=family, rows=rows, seconds_distance=t1-t0, seconds_total=time.monotonic()-t0,
        rule='GTJUDGE score_new + addendum11 process() direct-sample rule (normal_cylinder_1m) via add2_scores.metric_rows', scientific_verdict=None))
    print('SCORED', stem, family, [(r['surface'], r['case_id'], r['completeness_pct'], r.get('accuracy_pct')) for r in rows if r['surface'] == 'all'], flush=True)

def clean(stem, family):
    wd = SH/'meshes'/f'{stem}__{family}'/'final_work'; freed = 0
    for sub in ['tiles', 'bounded_merge', 'inputs', 'order', 'bin']:
        p = wd/sub
        if p.exists():
            freed += sum(f.stat().st_size for f in p.rglob('*') if f.is_file()); shutil.rmtree(p)
    print('CLEANED', stem, family, freed, flush=True)

def main(step, stem, family=None, ply=None):
    if step == 'shadow': return shadow(stem)
    site, prior = stem.split('__')
    if step == 'score': return score(stem, family)
    if step == 'clean': return clean(stem, family)
    if step == 'recover':
        import importlib.util
        spec = importlib.util.spec_from_file_location('te_recover', '/repo/scripts/phd/main_trainerr_v1/te_recover.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m.main(stem, family)
    import mesh_job
    mesh_job.main(site, prior, family, step, ply)

if __name__ == '__main__': main(*sys.argv[1:])
