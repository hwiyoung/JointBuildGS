"""Input-side supervision support; no reconstruction or source accuracy decisions."""
import hashlib
from pathlib import Path
import numpy as np


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def object_basis(angle_degrees):
    a = np.deg2rad(angle_degrees)
    # v points down on the approved display; determinant -1 is intentional.
    return np.array([[np.cos(a), np.sin(a)], [np.sin(a), -np.cos(a)]])


def region_mask(xyz, region, basis, z_bounds):
    uv = xyz[:, :2] @ basis.T
    return ((uv[:, 0] >= region['u_m'][0]) & (uv[:, 0] < region['u_m'][1]) &
            (uv[:, 1] >= region['v_m'][0]) & (uv[:, 1] < region['v_m'][1]) &
            (xyz[:, 2] >= z_bounds[0]) & (xyz[:, 2] < z_bounds[1]))


def prism_mask(xyz, prism):
    return np.logical_and.reduce([(xyz[:, j] >= prism[k][0]) & (xyz[:, j] < prism[k][1])
                                  for j, k in enumerate(('x', 'y', 'z'))])


def corners_xy(region, basis):
    u0,u1=region['u_m']; v0,v1=region['v_m']
    return np.array([[u0,v0],[u1,v0],[u1,v1],[u0,v1],[u0,v0]]) @ basis


def read_depth(path):
    data = Path(path).read_bytes()
    offset = 0
    for _ in range(3):
        offset = data.find(b'&', offset, 100) + 1
        if not offset:
            raise ValueError('Malformed native depth header')
    w,h,c=map(int,data[:offset].decode('ascii').split('&')[:3])
    if c != 1 or w <= 0 or h <= 0 or len(data) != offset+w*h*4:
        raise ValueError('Malformed native depth payload')
    depth=np.frombuffer(data,dtype='<f4',offset=offset).reshape((w,h),order='F').T.copy()
    return depth, {'width':w,'height':h,'channels':c,'header_bytes':offset,
                   'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}


def ray_grid(K,w,h):
    yy,xx=np.indices((h,w),dtype=np.float32)
    return (np.stack((xx,yy,np.ones_like(xx)),axis=-1).reshape(-1,3) @
            np.linalg.inv(K).astype(np.float32).T)


def rgb_native_indices(K_rgb,K_native,w,h,nw,nh):
    rays=ray_grid(K_rgb,w,h)
    yy,xx=np.indices((h,w),dtype=np.float64)
    pixels=np.stack((xx,yy,np.ones_like(xx)),axis=-1).reshape(-1,3)
    mapped=pixels@(np.asarray(K_native)@np.linalg.inv(K_rgb)).T
    xy=np.floor(mapped[:,:2]/mapped[:,2:3]+.5).astype(np.int64)
    inside=(xy[:,0]>=0)&(xy[:,0]<nw)&(xy[:,1]>=0)&(xy[:,1]<nh)
    return rays, np.clip(xy[:,1],0,nh-1)*nw+np.clip(xy[:,0],0,nw-1), inside


def backproject(depth_flat,rays,R,t):
    return (rays*depth_flat[:,None]-np.asarray(t,dtype=np.float32))@np.asarray(R,dtype=np.float32)


def query_points(points,R,t,K,depth,tolerances):
    cam=points.astype(np.float64)@np.asarray(R).T+np.asarray(t)
    z=cam[:,2]
    positive=z>1e-6
    uv=cam@np.asarray(K).T
    xy=np.floor(uv[:,:2]/np.where(positive,z,1.)[:,None]+.5).astype(np.int64)
    frame=positive&(xy[:,0]>=0)&(xy[:,0]<depth.shape[1])&(xy[:,1]>=0)&(xy[:,1]<depth.shape[0])
    observed=depth[np.clip(xy[:,1],0,depth.shape[0]-1),np.clip(xy[:,0],0,depth.shape[1]-1)]
    has=frame&np.isfinite(observed)&(observed>0)
    residual=observed-z
    support=np.stack([has&(np.abs(residual)<=tol) for tol in tolerances])
    return frame,has,residual,support


def concentration(values, fractions=(.5,.8,.9)):
    values=np.asarray(values,dtype=np.float64)
    if np.any(values<0) or not np.isfinite(values).all():
        raise ValueError('Finite nonnegative supervision coefficients required')
    total=float(values.sum())
    if total==0:
        return dict(total=0.,positive_views=0,top1_fraction=None,top5_fraction=None,
                    effective_count=None,n_cumulative={str(q):0 for q in fractions},ranking=[])
    rank=np.argsort(-values,kind='stable'); rank=rank[values[rank]>0]
    weights=values[rank]/total
    cs=np.cumsum(weights)
    return dict(total=total,positive_views=len(rank),top1_fraction=float(weights[0]),
                top5_fraction=float(weights[:5].sum()),effective_count=float(1/np.square(weights).sum()),
                n_cumulative={str(q):int(min(len(rank),np.searchsorted(cs,q,side='left')+1)) for q in fractions},
                ranking=rank.tolist())
