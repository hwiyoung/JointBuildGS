"""Read the unchanged forward return buffers at recording iterations only."""
import numpy as np
import torch
observer=None
class Observer:
    def __init__(self,module):self.module=module;self.last_tiles=None
    def __getattr__(self,key):return getattr(self.module,key)
    def rasterize_gaussians(self,*args):
        out=self.module.rasterize_gaussians(*args)
        import r8_record_hooks as H
        if H.PHASE=='training_forward_before_optimizer' and H.BEGIN and (H.BEGIN['iteration']+1)%100==0:
            n=args[1].shape[0];offset=0
            for size in [4,3,4,8,36,16,12]:offset=(offset+127)//128*128+n*size
            offset=(offset+127)//128*128;self.last_tiles=out[4][offset:offset+4*n].view(torch.int32).cpu().numpy().copy()
            assert int(self.last_tiles.astype('i8').sum())==int(out[0])
        return out
