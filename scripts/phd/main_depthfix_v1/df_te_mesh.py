"""issues 33: runs the unchanged TRAINERR te_mesh.py with one patch. RESCORE meshes/B173nb_b10__ALS__r8_30000/final_work/inputs/meta.json (the source of the
B173 scene box read by GTJUDGE inherited.ensure_views) was removed by another session's cleanup on 11-24. This task's shadow /gtjudge/views/<site>.json already
holds the same box (written earlier by the same ensure_views), so ensure_views reads that file first. Values unchanged. argv = te_mesh.py argv."""
import sys, json, runpy
sys.path.insert(0, '/repo/scripts/phd/main_gtjudge_v1')
import inherited
_orig = inherited.ensure_views
def ensure_views(site):
    own = inherited.O/'views'/f'{site}.json'
    if own.exists():
        z = json.loads(own.read_text())
        if 'box' in z and 'views' in z: return z
    return _orig(site)
inherited.ensure_views = ensure_views
sys.argv = ['/repo/scripts/phd/main_trainerr_v1/te_mesh.py'] + sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
