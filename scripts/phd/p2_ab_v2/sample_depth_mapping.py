"""Map saved COLMAP camera-Z depth to original-focal P2 crop rays.

Geometry-only coordinate adapter. Does not decide source usability or fit reference.
COLMAP channel-planar storage follows its 3.9.1 read_write_dense.py contract.
"""
from pathlib import Path
import numpy as np


def read_colmap_array(path):
    with Path(path).open('rb') as f:
        header=b''
        while header.count(b'&')<3:
            char=f.read(1)
            if not char: raise ValueError('Truncated COLMAP header')
            header+=char
        width,height,channels=map(int,header.decode().strip('&').split('&'))
        a=np.fromfile(f,dtype='<f4')
    if a.size!=width*height*channels: raise ValueError('COLMAP payload length mismatch')
    # Storage is one row-major image plane per channel, not interleaved RGB.
    image=a.reshape(channels,height,width).transpose(1,2,0)
    return image[:,:,0] if channels==1 else image


def depth_intrinsics(view):
    width,height,channels=view['geometric_depth']['dimensions']
    if channels!=1: raise ValueError('Expected camera-Z depth map')
    original=view['low_resolution_derivative']
    scale=np.diag([width/original['width'],height/original['height'],1.])
    return scale@np.asarray(original['K'],dtype=np.float64)


def sample_depth_rays(view, uv, current_K=None, depth=None):
    """Return nearest depth, conservative 2x2 min/max and explicit unknown masks.

    uv may be Nx2 or HxWx2 in any crop/resize with supplied current_K.
    Camera poses are identical; K_depth inv(K_current) is the complete ray map.
    A caller may mark foreground only if all-four-valid and max_Z+margin<source_Z.
    Missing/unknown depth is not a rejection or approval of the prior.
    """
    if depth is None: depth=read_colmap_array(view['geometric_depth']['path'])
    K=np.asarray(view['K'] if current_K is None else current_K,dtype=np.float64)
    transform=depth_intrinsics(view)@np.linalg.inv(K)
    uv=np.asarray(uv,dtype=np.float64)
    p=np.concatenate([uv,np.ones((*uv.shape[:-1],1))],axis=-1)@transform.T
    mapped=p[...,:2]/p[...,2:3]
    finite=np.isfinite(mapped).all(-1)
    safe=np.where(finite[...,None],mapped,0)
    nearest=np.floor(safe+.5).astype(np.int64)
    h,w=depth.shape
    inframe=finite&(nearest[...,0]>=0)&(nearest[...,0]<w)&(nearest[...,1]>=0)&(nearest[...,1]<h)
    nn=depth[np.clip(nearest[...,1],0,h-1),np.clip(nearest[...,0],0,w-1)]
    known=inframe&np.isfinite(nn)&(nn>0)
    lo=np.floor(safe).astype(np.int64)
    four_inside=finite&(lo[...,0]>=0)&(lo[...,0]+1<w)&(lo[...,1]>=0)&(lo[...,1]+1<h)
    four=np.stack([depth[np.clip(lo[...,1]+dy,0,h-1),np.clip(lo[...,0]+dx,0,w-1)]
                   for dy,dx in [(0,0),(0,1),(1,0),(1,1)]],axis=-1)
    four_known=four_inside&np.isfinite(four).all(-1)&(four>0).all(-1)
    return {'depth_uv':mapped,'nearest_z':np.where(known,nn,0),'nearest_known':known,
            'all_four_known':four_known,'footprint_min_z':np.where(four_known,four.min(-1),0),
            'footprint_max_z':np.where(four_known,four.max(-1),0),'ray_transform':transform}
