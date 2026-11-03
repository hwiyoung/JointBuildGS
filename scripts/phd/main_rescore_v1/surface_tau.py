"""Use the wall tolerance for wall reference surfaces (order 4.3)."""
import numpy as np
RULE='reference_surface_kind_v1'
def by_wall(ctx,wall):
 core=ctx['core'];tau=ctx['v2']['tau_v2_m'];roof=np.unique(tau[core['kind']==1]);assert len(roof)==1
 if str(core['prior'][0])=='ALS':return np.full(np.shape(wall),roof[0])
 walls=np.unique(tau[core['kind']==2]);assert len(walls)==1
 return np.where(wall,walls[0],roof[0])
