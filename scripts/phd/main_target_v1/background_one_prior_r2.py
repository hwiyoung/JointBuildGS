"""Run one prior's unchanged background recipe while its site's other lane is paused."""
import sys
import background_r2 as B
import background_workers_r2 as W
from common import *


if __name__=='__main__':
    site,prior=sys.argv[1:3]
    assert prior in ['ALS','LoD2']
    cfg,lock=locked_r2()
    # Scope restriction only, analogous to running one site; no rule or value changes.
    cfg=dict(cfg,priors=[prior])
    B.locked_r2=lambda:(cfg,lock)
    W.u2_run.run=W.parallel
    sys.argv=[sys.argv[0],site]
    B.main()
