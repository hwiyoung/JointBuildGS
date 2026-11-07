"""Order 2.1 rays with addendum-authorized AXES71 PCA reference normals."""
import sys
import numpy as np
sys.path.insert(0, '/repo')
from src.phd.metrics_v3.surface import MeshScene

def unit_normals(normals):
    n = np.asarray(normals, dtype=np.float64)
    length = np.linalg.norm(n, axis=1)
    if n.ndim != 2 or n.shape[1] != 3 or not np.isfinite(n).all() or (length <= 0).any():
        raise ValueError('Missing or invalid locked measurement normals')
    return n / length[:,None]

def tangents(n):
    n = unit_normals(n)
    axis = np.eye(3)[np.argmin(abs(n),axis=1)]
    a = unit_normals(np.cross(n,axis))
    return a, np.cross(n,a)

def measure(scene, points, normals, wall, extra_diagonals=False):
    p = np.asarray(points,np.float64)
    n = unit_normals(normals)
    assert p.shape == n.shape and np.isfinite(p).all()
    limit = np.where(np.asarray(wall,bool),5.,10.)
    limit = np.broadcast_to(limit,(len(p),))
    a,b = tangents(n)
    best = np.full(len(p),np.inf)
    signed = np.full(len(p),np.nan)
    offset_id = np.full(len(p),-1,np.int8)
    shifts=[np.zeros_like(p),.05*a,-.05*a,.05*b,-.05*b]
    if extra_diagonals:shifts += [.05/np.sqrt(2)*(x*a+y*b) for x,y in [(1,1),(1,-1),(-1,1),(-1,-1)]]
    for k,shift in enumerate(shifts):
        for sign in [1,-1]:
            distance = scene.cast(p+shift,n*sign).astype(float)
            take = np.isfinite(distance)&(distance<=limit)&(distance<best)
            best[take] = distance[take]
            signed[take] = sign*distance[take]
            offset_id[take] = k
    return signed, offset_id

def align_result_normals(result_normals, reference_normals):
    n = unit_normals(result_normals)
    ref = unit_normals(reference_normals)
    dot = (n*ref).sum(1)
    if (abs(dot)<1e-12).any():
        raise ValueError('Perpendicular result/reference normals cannot have positive dot by sign flip')
    return n * np.where(dot<0,-1.,1.)[:,None]

def values(signed,tau,eligible=None,*,distance_statistics=True):
    s = np.asarray(signed,float)
    tau = np.broadcast_to(np.asarray(tau,float),s.shape)
    mask = np.ones(len(s),bool) if eligible is None else np.asarray(eligible,bool)
    hit = mask&np.isfinite(s)
    within = hit&(abs(s)<=tau)
    far = hit&~within
    absent = mask&~hit
    denominator = int(mask.sum())
    pct = lambda x:100*int(x.sum())/denominator if denominator else None
    median = float(np.median(s[hit])) if distance_statistics and hit.any() else None
    return dict(n=denominator,n_excluded=int((~mask).sum()),n_hit=int(hit.sum()),
        within_pct=pct(within),far_hit_pct=pct(far),no_surface_pct=pct(absent),
        median_signed_m=median,
        nmad_m=float(1.4826*np.median(abs(s[hit]-median))) if median is not None else None,
        abs_p50_p683_p95_m=np.quantile(abs(s[hit]),[.5,.683,.95]).tolist() if distance_statistics and hit.any() else None)

def cases(prior,mvs,tau):
    prior=np.asarray(prior);mvs=np.asarray(mvs)
    p=np.isfinite(prior)&(abs(prior)<=tau)
    m=np.isfinite(mvs)&(abs(mvs)<=tau)
    result=np.full(len(prior),3,np.int8)
    result[p&m]=0;result[~p&m]=1;result[p&~m]=2
    result[p&~np.isfinite(mvs)]=4
    # Prior-surface absence is a separate count, not a sixth mutually exclusive case.
    return result, ~np.isfinite(prior)
