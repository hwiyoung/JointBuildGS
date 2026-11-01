"""Operational worker-count override; the locked background algorithm is unchanged."""
import sys
import background_r2 as B
from common import *
sys.path.insert(0,str(REPO/'scripts/phd/main_uncert_v1'))
import u2_run
original=u2_run.run


def parallel(site,pset,data,radii,workers,limit=None):
    return original(site,pset,data,radii,16,limit)


if __name__=='__main__':
    proof=json.loads((OUT/'r2/verification/worker_invariance.json').read_text())
    assert proof['status']=='PASS_IDENTICAL_4_AND_16_WORKERS'
    u2_run.run=parallel
    B.main()
