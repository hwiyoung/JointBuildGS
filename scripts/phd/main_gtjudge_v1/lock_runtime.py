"""Freeze training sources, after the addendum-only units and before initialization."""
from common import *
def main():
    cfg();path=C/'runtime.add1.lock.json'
    if path.exists():return
    source=R/'src/phd/forks/GeoGS-conf-guided-v1-r25'
    paths=[p for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    paths += [R/'scripts/phd/main_gtjudge_v1'/name for name in ['common.py','train_entry.py','gpu_job.py','initialize_gt.py','prepare_gt.py','targets_gt.py','majority.py']]
    paths += [R/'scripts/phd/main_finaltrain_v1'/name for name in ['targets.py','prepare_inputs.py','verify_inputs.py','initialize_check.py','renderer.py']]
    dump(path,dict(at=now(),files={str(p):sha(p) for p in sorted(paths)},
        units_reused_from='1923967f',new_unit_sha256=sha(O/'verification/unit_fs_schedule.json'),scientific_verdict=None))
    print('RUNTIME_LOCKED',len(paths),sha(path),flush=True)
if __name__=='__main__':main()
