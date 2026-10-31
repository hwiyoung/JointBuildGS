"""GeoGS expected ray/splat depth using the unchanged v1 gsplat contributors.

gsplat 1.4 RGB+ED interpolates Gaussian center Z. GeoGS mesh extraction instead
uses ray-plane intersection Z before alpha normalization. Reconstruct the latter
at requested pixels, retaining the v1 renderer's alpha and visibility weights.
"""
import torch
from gsplat.cuda._wrapper import rasterize_to_indices_in_range_2dgs

@torch.no_grad()
def expected_depth(meta,pixels):
    w,h=meta['width'],meta['height']
    trans=torch.zeros((1,h,w),device='cuda');trans.reshape(-1)[pixels]=1
    gi,px,_=rasterize_to_indices_in_range_2dgs(0,100000,trans,meta['means2d'],meta['ray_transforms'],
        meta['opacities'],w,h,16,meta['isect_offsets'],meta['flatten_ids'])
    if not len(px):return torch.full((h*w,),torch.nan,device='cuda'),dict(contributors=0)
    assert bool(torch.all(px[1:]>=px[:-1]))
    xy=torch.stack([px%w+.5,px//w+.5],1)
    ray=meta['ray_transforms'][0,gi]
    cross=torch.cross(xy[:,0,None]*ray[:,2]-ray[:,0],xy[:,1,None]*ray[:,2]-ray[:,1],dim=1)
    s=cross[:,:2]/cross[:,2:]
    rho3=s.square().sum(1);rho2=2.*(meta['means2d'][0,gi]-xy).square().sum(1)
    alpha=(meta['opacities'][0,gi]*torch.exp(-.5*torch.minimum(rho3,rho2))).clamp_max(.999)
    depth=(s*ray[:,2,:2]).sum(1)+ray[:,2,2]
    starts=torch.cat([torch.tensor([0],device='cuda'),torch.nonzero(px[1:]!=px[:-1]).flatten()+1])
    group=torch.cumsum(torch.cat([torch.ones(1,device='cuda',dtype=torch.long),(px[1:]!=px[:-1]).long()]),0)-1
    # Float64 prefix sums prevent cancellation across unrelated pixels.
    log=torch.log1p(-alpha.double());prefix=torch.cumsum(log,0)-log
    weight=(alpha.double()*torch.exp(prefix-prefix[starts][group]))
    total=torch.zeros(len(starts),dtype=torch.float64,device='cuda').scatter_add_(0,group,weight)
    moment=torch.zeros_like(total).scatter_add_(0,group,weight*depth.double())
    center=torch.zeros_like(total).scatter_add_(0,group,weight*meta['depths'][0,gi].double())
    out=torch.full((h*w,),torch.nan,device='cuda');out[px[starts]]=(moment/total).float()
    diagnostic=dict(contributors=len(px),nonfinite_ray_depth=int((~torch.isfinite(depth)).sum()),
        below_geogs_near_count=int((depth<.2).sum()),pixels=len(starts),
        center_expected=center/total,alpha=total,pixel_ids=px[starts])
    # Near-plane invalids are not silently assigned a height.
    invalid=torch.zeros(len(starts),dtype=torch.long,device='cuda').scatter_add_(0,group,((depth<.2)|~torch.isfinite(depth)).long())
    out[px[starts][invalid>0]]=torch.nan
    return out,diagnostic
