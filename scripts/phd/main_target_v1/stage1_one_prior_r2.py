"""Restrict input preparation/verification to one completed background prior."""
import sys
from common import *

if __name__ == '__main__':
    mode,site,prior=sys.argv[1:4]
    assert prior in ['ALS','LoD2'] and mode in ['prepare','verify']
    if mode=='prepare':
        import prepare_seeds_r2 as module
    else:
        import verify_stage1_r2 as module
    cfg,lock=locked_r2()
    module.locked_r2=lambda:(dict(cfg,priors=[prior]),lock)
    sys.argv=[sys.argv[0],site]
    module.main()
