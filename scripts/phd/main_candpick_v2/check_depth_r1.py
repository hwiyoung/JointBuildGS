"""Analytic and independent CPU checks of the GeoGS depth correction."""
import gc
import torch
from engine import Scene
from geogs_depth_readout import expected_depth
from cp2_common import *

def synthetic(depths,opacity):
    n=len(depths);r=np.zeros((1,n,3,3),np.float32)
    r[0,:,0,0]=1;r[0,:,1,1]=1
    r[0,:,0,2]=np.array(depths)*.5;r[0,:,1,2]=np.array(depths)*.5;r[0,:,2,2]=depths
    t=lambda a:torch.as_tensor(a,device='cuda')
    return dict(width=16,height=16,means2d=t(np.full((1,n,2),.5,np.float32)),ray_transforms=t(r),
        opacities=t(np.array([opacity],np.float32)),depths=t(np.array([depths],np.float32)),
        isect_offsets=t(np.array([[[0]]],np.int32)),flatten_ids=t(np.arange(n,dtype=np.int32)))

def reference(meta,pixels):
    r=meta['ray_transforms'].cpu().numpy()[0];means=meta['means2d'].cpu().numpy()[0]
    opa=meta['opacities'].cpu().numpy()[0];off=meta['isect_offsets'].cpu().numpy().ravel()
    ids=meta['flatten_ids'].cpu().numpy();tx=meta['isect_offsets'].shape[-1];w=meta['width'];out=[]
    for pixel in pixels:
        x=int(pixel)%w;y=int(pixel)//w;tile=(y//16)*tx+x//16
        g=ids[off[tile]:off[tile+1] if tile+1<len(off) else len(ids)];a=r[g]
        px=np.float32(x+.5);py=np.float32(y+.5)
        cross=np.cross(px*a[:,2]-a[:,0],py*a[:,2]-a[:,1]);nonzero=cross[:,2]!=0
        g=g[nonzero];a=a[nonzero];cross=cross[nonzero]
        s=cross[:,:2]/cross[:,2,None]
        depth=s[:,0]*a[:,2,0]+s[:,1]*a[:,2,1]+a[:,2,2]
        if not np.isfinite(depth).all():out.append(np.nan);continue
        rho=np.minimum((s*s).sum(1),2*((means[g]-np.array([px,py],np.float32))**2).sum(1))
        alpha=np.minimum(.99,opa[g]*np.exp(-.5*rho))
        keep=(depth>=.2)&np.isfinite(alpha)&(alpha>=1/255)
        depth=depth[keep].astype(float);alpha=alpha[keep].astype(float)
        after=np.cumprod(1-alpha);n=int(np.flatnonzero(after<.0001)[0]) if (after<.0001).any() else len(alpha)
        alpha=alpha[:n];depth=depth[:n];before=np.r_[1.,after[:max(n-1,0)]] if n else np.empty(0)
        weight=alpha*before
        out.append(float(np.sum(weight*depth)/weight.sum()) if weight.sum()>0 else np.nan)
    return np.array(out)

def main():
    rows=[]
    examples=[('near_then_valid',[.1,2.,4.],[.999,.5,.5],8/3,2),
              ('alpha_cap',[2.,4.],[1.,.5],2/.995,2),
              ('exclusive_stop',[2.]*20,[.5]*20,2.,13),
              ('all_near',[.1,.15],[.9,.9],None,0)]
    for name,depths,alpha,expected,count in examples:
        meta=synthetic(depths,alpha);value,diag=expected_depth(meta,torch.tensor([0],device='cuda'))
        actual=float(value[0]);assert diag['contributors']==count,(name,diag)
        assert np.isnan(actual) if expected is None else abs(actual-expected)<1e-5,(name,actual,expected)
        rows.append(dict(test=name,actual_m=actual,expected_m=expected,contributors=count))
    actual_checks=[]
    for unit in UNITS:
        scene=Scene(unit,'v1','right');scene.load_snapshot(CP1/'runs'/f'cp_right_sh3_{unit}/candidate_3000.npz',baseline=True)
        v=arrays(OUT/'depth_views'/unit/'selected_pixels.npz')
        for j in sorted(set(v['view_index']))[:2]:
            pixels=np.unique(v['pixel_index'][v['view_index']==j]);pixels=pixels[np.linspace(0,len(pixels)-1,min(64,len(pixels)),dtype=int)]
            with torch.no_grad():
                render=scene.render(scene.cams[j],depth=True);meta=render[-1]
                values,diag=expected_depth(meta,torch.tensor(pixels,device='cuda'))
                gpu=values[pixels].cpu().numpy();cpu=reference(meta,pixels)
                assert np.array_equal(np.isfinite(gpu),np.isfinite(cpu)),(unit,j,'finite status')
                err=np.abs(gpu[np.isfinite(gpu)]-cpu[np.isfinite(cpu)])
                maximum=float(err.max()) if len(err) else 0.
                assert maximum<=.005,(unit,j,maximum)
                actual_checks.append(dict(unit=unit,view=scene.cams[j]['name'],pixels=len(pixels),finite=int(np.isfinite(gpu).sum()),max_abs_error_m=maximum))
                del render,meta,values,diag
        del scene;gc.collect();torch.cuda.empty_cache()
    report=dict(status='PASS',at=now(),analytic=rows,independent_cpu=actual_checks,real_pixel_tolerance_m=.005,
        source=SOURCE,scientific_verdict=None,implementation=[bind(Path(__file__).with_name(n)) for n in
            ['check_depth_r1.py','geogs_depth_readout.py','geogs_depth_readout.cu']])
    save(OUT/'preflight/depth_r1.json',report);print(clean(report),flush=True)

if __name__=='__main__':main()
