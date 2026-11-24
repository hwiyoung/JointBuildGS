"""Host driver: surface extraction + scoring of DEPTHFIX runs with the unchanged GTTARGET-v1 mesh chain (g_mesh.py -> render -> TRAINERR te_mesh.py
prepare/plan/tiles/merge/finish/score), redirected as PRESCRIBE-v1 p3_mesh.py does: O (/te) = this payload, shadow O/gtj, work folder O/fastwork.
Render GPU = env DF_MESH_GPU (default 0). Only change: the render step runs df_render.py (= GTTARGET g3_render_model.py with variants base | occl10 | occlga).
usage: python3 df_mesh.py <workers> <stem>:<run>:<variant> ...     writes O/meshes/<stem>__df_<run>_<variant>/{points.npz,score.json}"""
import importlib.util, os, shutil, sys
from pathlib import Path
R = Path(__file__).resolve().parents[3]; PH = R.parent/'JointBuildGS-artifacts/phase-payloads/phd'
PO = PH/'main_depthfix_v1/PHD-MAIN-DEPTHFIX-v1'; FAST = PO/'fastwork'
FAST.mkdir(parents=True, exist_ok=True); os.environ['GT_FASTWORK'] = str(FAST)

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def main(workers, *specs):
    gm = load('gtt_g_mesh', R/'scripts/phd/main_gttarget_v1/g_mesh.py')
    A = gm.A; TL = sys.modules['launch']
    assert Path(TL.__file__).parent.name == 'main_trainerr_v1'
    for m in (A, TL): m.O = PO; m.FAST = FAST
    gm.FAST = FAST; gm.SH = PO/'gtj'; (PO/'logs').mkdir(exist_ok=True)
    orig = A.gtjscript
    A.gtjscript = lambda script, args, gpu=None: orig('../main_depthfix_v1/df_render.py' if script == 'g3_render_model.py' else script, args, gpu)
    jobs = []
    for s in specs:
        stem, run, variant = s.split(':')
        dst = PO/'stage1'/stem/'maps'
        if not (dst/'index.json').exists(): dst.mkdir(parents=True, exist_ok=True); shutil.copy2(PO/'maps/base/base'/stem/'index.json', dst/'index.json')
        assert (PO/'runs'/stem/run/'model/point_cloud/iteration_30000/point_cloud.ply').is_file(), s
        jobs.append(f'{stem}:df_{run}_{variant}:model:{os.environ.get("DF_MESH_GPU", "0")}:/te/runs/{stem}/{run}/model/point_cloud/iteration_30000/point_cloud.ply:{variant}')
    gm.main(workers, *jobs)

if __name__ == '__main__': main(*sys.argv[1:])
