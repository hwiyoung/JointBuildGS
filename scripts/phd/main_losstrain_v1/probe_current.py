"""Record initialization, then reuse the existing no-optimizer checkpoint probe."""
import hashlib
import json
import runpy
import sys
from pathlib import Path
sys.path.insert(0,'/source')
import jbgs_judgment as JJ

original=JJ.Judgment.__init__

def wrapped(self,args,opt,scene,gaussians,*a,**kw):
    original(self,args,opt,scene,gaussians,*a,**kw)
    # No randomness, mutation, or extra GPU operations: the maps are already on host.
    arrays={}
    for label,collection in [('A',self.A),('M',self.M),('P',self.P),('TAU',self.TAU),('GW',self.GW)]:
        for name,value in collection._h.items():
            x=value.numpy()
            arrays[f'{label}/{name}']=dict(shape=list(x.shape),dtype=str(x.dtype),sha256=hashlib.sha256(x.tobytes()).hexdigest())
    (self.mon/'initial_map_hashes.json').write_text(json.dumps(arrays,sort_keys=True,indent=1)+'\n')

JJ.Judgment.__init__=wrapped
runpy.run_path('/repo/scripts/phd/main_fixtest_v1/probe_ckpt_ft.py',run_name='__main__')
