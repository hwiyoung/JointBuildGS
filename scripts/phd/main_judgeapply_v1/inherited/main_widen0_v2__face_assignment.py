"""View-v1.1 triangle rules, without the viewer's unmatched 2 m fallback grid."""
import numpy as np

def inside_triangle(p,t):
    a,b,c=t[:,:2];v0=b-a;v1=c-a;v=p-a
    det=v0[0]*v1[1]-v0[1]*v1[0]
    if abs(det)<1e-12:return np.zeros(len(p),bool),np.zeros(len(p)),np.zeros(len(p))
    u=(v[:,0]*v1[1]-v[:,1]*v1[0])/det
    w=(v0[0]*v[:,1]-v0[1]*v[:,0])/det
    return (u>=-1e-9)&(w>=-1e-9)&(u+w<=1+1e-9),u,w

def triangle_distance(p,t):
    a,b,c=t;ab=b-a;ac=c-a;n=np.cross(ab,ac);norm=np.linalg.norm(n)
    if norm<1e-12:return np.full(len(p),np.inf)
    n/=norm;signed=(p-a)@n;projected=p-signed[:,None]*n
    v=projected-a;d00=ab@ab;d01=ab@ac;d11=ac@ac;den=d00*d11-d01*d01
    u=(d11*(v@ab)-d01*(v@ac))/den;w=(d00*(v@ac)-d01*(v@ab))/den
    inside=(u>=-1e-9)&(w>=-1e-9)&(u+w<=1+1e-9)
    dist=np.full(len(p),np.inf)
    for start,end in [(a,b),(b,c),(c,a)]:
        edge=end-start;length=edge@edge
        q=np.clip(((p-start)@edge)/max(length,1e-30),0,1)
        dist=np.minimum(dist,np.linalg.norm(p-start-q[:,None]*edge,axis=1))
    return np.where(inside,np.abs(signed),dist)

def attach(centres,roof_like,records,mesh):
    assignment=np.full(len(centres),-1,np.int32);best=np.full(len(centres),np.inf)
    records=sorted(records,key=lambda r:r['ext'])
    tris=mesh['V'][mesh['F']];exts=mesh['tri_surface']
    for fi,f in enumerate(records):
        for tri in tris[exts==f['ext']]:
            if f['type']=='roof':
                lo,hi=tri[:,:2].min(0)-1e-9,tri[:,:2].max(0)+1e-9
                ids=np.flatnonzero(roof_like&np.all(centres[:,:2]>=lo,axis=1)&np.all(centres[:,:2]<=hi,axis=1))
                if not len(ids):continue
                ok,u,w=inside_triangle(centres[ids,:2],tri)
                zz=tri[0,2]+u*(tri[1,2]-tri[0,2])+w*(tri[2,2]-tri[0,2])
                distance=np.abs(centres[ids,2]-zz);good=ok&(distance<best[ids]-1e-12)
            else:
                lo,hi=tri.min(0)-1,tri.max(0)+1
                ids=np.flatnonzero(~roof_like&np.all(centres>=lo,axis=1)&np.all(centres<=hi,axis=1))
                if not len(ids):continue
                distance=triangle_distance(centres[ids],tri);good=(distance<=1)&(distance<best[ids]-1e-12)
            assignment[ids[good]]=fi;best[ids[good]]=distance[good]
    return assignment,records
