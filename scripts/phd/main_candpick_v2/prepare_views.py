"""Recover per-point contributions inside the exact frozen v1 render mask."""
import argparse
import gc
import torch
from gsplat import rasterization_2dgs
from gsplat.cuda._wrapper import rasterize_to_indices_in_range_2dgs
from frozen_engine import cameras, tensor
from cp2_common import *

@torch.no_grad()
def run(unit):
    root = OUT / 'depth_views' / unit; root.mkdir(parents=True, exist_ok=True)
    assert not (root / 'complete.json').exists()
    d = arrays(CP1 / 'places' / (unit + '.npz'))
    geo = arrays(CP1 / 'scenes' / unit / 'candidate_geometry.npz')
    g = {k:tensor(geo[k]) for k in ['means','quats','scales']}
    cams = cameras(unit); n = len(d['point_id']); count = np.zeros((n,len(cams)), np.int32)
    with np.load(CP1 / 'render_masks' / unit / 'masks.npz') as z: packed = z['packed_masks']
    pairs = []; validation = []
    for j,cam in enumerate(cams):
        h,w = cam['height'],cam['width']
        result = rasterization_2dgs(**g,opacities=torch.ones(len(g['means']),device='cuda'),
            colors=torch.zeros((len(g['means']),3),device='cuda'), viewmats=tensor(cam['E'])[None],
            Ks=tensor(cam['K'])[None],width=w,height=h,render_mode='RGB',packed=False,near_plane=.01)
        meta = result[-1]
        gi,px,_ = rasterize_to_indices_in_range_2dgs(0,100000,
            torch.ones((1,h,w),device='cuda'),meta['means2d'],meta['ray_transforms'],meta['opacities'],
            w,h,16,meta['isect_offsets'],meta['flatten_ids'])
        expected = np.unpackbits(packed[j],count=h*w).astype(bool)
        actual = (result[1][0,...,0]>0).cpu().numpy().ravel()
        contributed = np.zeros(h*w,bool); contributed[px.cpu().numpy()] = True
        assert np.array_equal(expected,actual), (unit,cam['name'],'v1 union changed')
        assert np.array_equal(actual,contributed), (unit,cam['name'],'contributor union mismatch')
        # One point-pixel observation even if several of its eight splats contribute.
        key = torch.unique((gi//8)*(h*w)+px,sorted=True).cpu().numpy()
        point = key//(h*w); pixels = key%(h*w)
        count[:,j] = np.bincount(point,minlength=n)
        pairs.append((point.astype(np.int32),pixels.astype(np.int32)))
        validation.append(dict(view=cam['name'],union_equal=True,pixels=int(actual.sum()),point_pixels=len(key)))
        if j%50==0: print(unit,'views',j+1,'/',len(cams),flush=True)
        del result,meta,gi,px
    # Stable sorting preserves lexical order of the already sorted camera names.
    chosen = np.argsort(-count,axis=1,kind='stable')[:,:3]
    chosen_count = np.take_along_axis(count,chosen,axis=1)
    chosen = np.where(chosen_count>0,chosen,-1)
    pp=[];vv=[];xx=[]
    for j,(point,pixels) in enumerate(pairs):
        keep = (chosen[point]==j).any(1)
        pp.append(point[keep]);xx.append(pixels[keep]);vv.append(np.full(int(keep.sum()),j,np.int16))
    np.savez_compressed(root/'selected_pixels.npz',point_id=d['point_id'],chosen_view_index=chosen,
        chosen_view_pixels=chosen_count,counts=count,view_names=np.array([c['name'] for c in cams]),
        point_index=np.concatenate(pp),view_index=np.concatenate(vv),pixel_index=np.concatenate(xx))
    save(root/'complete.json',dict(unit=unit,status='PASS_EXACT_V1_MASK_UNION',at=now(),points=n,
        three_views_points=int((chosen>=0).all(1).sum()),fewer_views_points=int((chosen<0).any(1).sum()),
        selected_pixels=bind(root/'selected_pixels.npz'),validation=validation,source=SOURCE,scientific_verdict=None))
    print(unit,'complete',n,'points; missing three views',int((chosen<0).any(1).sum()),flush=True)
    gc.collect();torch.cuda.empty_cache()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('units',nargs='+');args=p.parse_args()
    for u in args.units:run(u)
