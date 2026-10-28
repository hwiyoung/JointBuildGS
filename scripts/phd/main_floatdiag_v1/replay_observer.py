"""Run unchanged r17 with CPU-only birth receipts at exactly the saved PLY state.

All wrapped methods receive unchanged arguments and return their original return
values. No tensor, optimizer, RNG, density or health decision is modified.
"""
import runpy
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,'/source')
import jbgs_judgment as J

original_track=J.lt_track_birth
original_step=J.lt_monitor_step

def track(j,g):
    original_track(j,g)
    j.fd_iteration=0;j.fd_birth_iteration=np.zeros(len(g.get_xyz),np.int32)
    postfix,prune,save_ply=g.densification_postfix,g.prune_points,g.save_ply
    def post(*args,**kw):
        before=len(g.get_xyz);ret=postfix(*args,**kw)
        added=len(g.get_xyz)-before
        j.fd_birth_iteration=np.concatenate((j.fd_birth_iteration,np.full(added,j.fd_iteration,np.int32)))
        assert len(j.fd_birth_iteration)==len(g.get_xyz)
        return ret
    def cut(*args,**kw):
        mask=args[0] if args else kw['mask'];keep=~mask.detach().cpu().numpy().astype(bool)
        ret=prune(*args,**kw);j.fd_birth_iteration=j.fd_birth_iteration[keep];return ret
    def saved(path,*args,**kw):
        ret=save_ply(path,*args,**kw)
        out=Path(path).with_name('floatdiag_birth.npz');assert not out.exists()
        assert len(j.fd_birth_iteration)==len(j.lt_initial_survivor)==len(g.get_xyz)
        np.savez_compressed(out,birth_iteration=j.fd_birth_iteration,initial_survivor=j.lt_initial_survivor,
            origin=g.origin.detach().cpu().numpy(),iteration=np.int32(j.fd_iteration))
        return ret
    g.densification_postfix,g.prune_points,g.save_ply=post,cut,saved

def step(j,iteration,*args,**kw):
    j.fd_iteration=iteration;return original_step(j,iteration,*args,**kw)

J.lt_track_birth=track;J.lt_monitor_step=step
sys.argv[0]='/source/train.py'
runpy.run_path('/source/train.py',run_name='__main__')
