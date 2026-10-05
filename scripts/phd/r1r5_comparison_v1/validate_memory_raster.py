"""Compare native and striped CUDA outputs and all trainable gradients."""
import hashlib
import json
from pathlib import Path

import torch
from diff_surfel_rasterization import GaussianRasterizationSettings, GaussianRasterizer
from utils.graphics_utils import getProjectionMatrix
import memory_raster

torch.manual_seed(42)
torch.cuda.set_per_process_memory_fraction(.08)
device='cuda';count=12000;width=192;height=144
xyz=torch.randn(count,3,device=device)*.7;xyz[:,2]=torch.rand(count,device=device)*3+1
xy=torch.zeros_like(xyz);opacity=torch.rand(count,1,device=device)*.5+.05
scale=torch.rand(count,2,device=device)*.14+.01
rotation=torch.randn(count,4,device=device);rotation=rotation/rotation.norm(dim=1,keepdim=True)
color=torch.rand(count,3,device=device)
projection=getProjectionMatrix(.01,100.,1.2,1.0).T.contiguous().cuda()
projection[2,0]=.027;projection[2,1]=-.041
settings=GaussianRasterizationSettings(height,width,.684136808,.54630249,torch.zeros(3,device=device),1.,
                                      torch.eye(4,device=device),projection,0,torch.zeros(3,device=device),False,False)
weights=torch.linspace(.2,1.,height*width,device=device).reshape(height,width)
def run(strips):
    tensors=[v.detach().clone().requires_grad_(True) for v in [xyz,xy,opacity,color,scale,rotation]]
    a,b,c,d,e,f=tensors;r=GaussianRasterizer(settings)
    if strips:
        rgb,radii,maps=memory_raster.striped(r,a,b,c,colors_precomp=d,scales=e,rotations=f,rows=64)
    else:
        rgb,radii,maps=memory_raster._original(r,a,b,c,colors_precomp=d,scales=e,rotations=f)
    loss=(rgb*weights).sum()+(maps[[0,1,2,3,4,6]]*weights).sum()*.1
    loss.backward();torch.cuda.synchronize()
    return [rgb.detach(),radii,maps.detach()], [v.grad.detach() for v in tensors]

memory_raster.install()
native,ng=run(False);strip,sg=run(True)
checks={}
for name,a,b in list(zip(['rgb','radii','allmap'],native,strip))+list(zip(['xyz','screen_xy','opacity','color','scale','rotation'],ng,sg)):
    a,b=a.float(),b.float();diff=(a-b).abs();relative=(a-b).norm()/a.norm().clamp_min(1e-8)
    checks[name]=dict(max_abs=float(diff.max()),relative_l2=float(relative),finite=bool(torch.isfinite(b).all()))
    assert checks[name]['finite'],name
    if name=='radii':assert diff.max()<=1,name
    else:assert relative<.003,(name,checks[name])
receipt=dict(status='PASS_NATIVE_STRIP_OUTPUT_GRADIENT_PARITY',scientific_verdict=None,checks=checks,
             torch_version=torch.__version__,device=torch.cuda.get_device_name(),
             source_sha256=hashlib.sha256(Path(memory_raster.__file__).read_bytes()).hexdigest(),
             meaning='Numerical parity within stated tolerances; not bitwise identity or scene-quality validation')
Path('/output/receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt))
