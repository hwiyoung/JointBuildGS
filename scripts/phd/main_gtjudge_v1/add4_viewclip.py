"""Explicit local cutaway for display only. Source vertices are never moved."""
from add4_common import np,xyuv

def point_mask(P,cam):
 clip=cam.get('display_clip')
 if clip is None:return np.ones(len(P),bool)
 uv=xyuv(P);lo,hi=np.asarray(clip['bounds_uv']);zlo,zhi=clip['z_bounds_local_m']
 return ((uv>=lo)&(uv<=hi)).all(1)&(P[:,2]>=zlo)&(P[:,2]<=zhi)

def faces(V,F,cam):
 if cam.get('display_clip') is None:return F
 inside=point_mask(V,cam)
 # Retain only complete original triangles; do not create intersections or new triangles.
 return F[inside[F].all(1)]
