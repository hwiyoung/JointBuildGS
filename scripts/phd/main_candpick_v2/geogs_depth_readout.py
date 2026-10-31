"""Corrected GeoGS depth readout, separate from all frozen training code."""
from pathlib import Path
import torch
from torch.utils.cpp_extension import load

_extension=None

def extension():
    global _extension
    if _extension is None:
        _extension=load(name='candpick_v2_geogs_depth_r1',sources=[str(Path(__file__).with_suffix('.cu'))],
            extra_cflags=['-O3'],extra_cuda_cflags=['-O3'],verbose=False)
    return _extension

@torch.no_grad()
def expected_depth(meta,pixels):
    pixels=pixels.contiguous().long()
    if not len(pixels):return torch.full((meta['width']*meta['height'],),torch.nan,device=pixels.device),dict(contributors=0)
    result,counts=extension().forward(*[meta[k].contiguous() for k in
        ['means2d','ray_transforms','opacities','depths','isect_offsets','flatten_ids']],pixels,meta['width'])
    out=torch.full((meta['width']*meta['height'],),torch.nan,device=pixels.device)
    out[pixels]=result[:,0]
    valid=torch.isfinite(result[:,0])
    # Undefined arithmetic is explicitly unavailable, even if other discs exist.
    out[pixels[counts[:,2]>0]]=torch.nan
    return out,dict(contributors=int(counts[:,0].sum()),below_geogs_near_count=int(counts[:,1].sum()),
        nonfinite_ray_depth=int(counts[:,2].sum()),pixels=len(pixels),pixel_ids=pixels[valid],
        alpha=result[valid,1],center_expected=result[valid,2])
