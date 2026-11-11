"""Key-iteration meshes (order 5 curve): normal-line distance of the record-run lost and control points (sets_tl) to one key mesh.
c1/c2 reference points: GTJUDGE normal_line.measure (stage-1 rule); c3 result points: same measure from the result point (does a surface
exist within tau at the wrong-surface location). argv: <run> <name>"""
from common import *
sys.path.insert(0, '/repo')
from src.phd.metrics_v3.surface import MeshScene
from s0_sets import NL
from te_sets_tl import RUNS
def main(run, name):
    stem, arm = RUNS[run]; fam = f'tl_{arm}_{name}'; mesh = O/'gtj/meshes'/f'{stem}__{fam}'/'final.ply'; t = Timer(f'measure_{run}_{name}')
    sc = MeshScene.from_ply(str(mesh)); rows = []; out = {}
    for cell in sorted(k for k, v in STEMS.items() if v == stem):
        for setname in ['lost', 'control']:
            z = loadz(O/'sets_tl'/f'{cell}_{arm}_{setname}.npz', ['xyz', 'normal', 'wall', 'tau_m'])
            s, _ = NL.measure(sc, z['xyz'], z['normal'], z['wall'].astype(bool)); w = np.isfinite(s) & (np.abs(s) <= z['tau_m'])
            out[f'{cell}_{setname}_s'] = s.astype('f4'); rows.append(dict(run=run, name=name, cell=cell, set=setname, n=len(s), within_tau_pct=100*float(w.mean()) if len(s) else None, no_surface_pct=100*float((~np.isfinite(s)).mean()) if len(s) else None))
    savez(O/'curves'/f'{run}__{name}.npz', **out); dump(O/'curves'/f'{run}__{name}.json', dict(at=now(), run=run, name=name, mesh=str(mesh), mesh_sha256=sha(mesh), rows=rows, seconds=t.done(), scientific_verdict=None))
    print('MEASURED', run, name, rows, flush=True)
if __name__ == '__main__': main(*sys.argv[1:])
