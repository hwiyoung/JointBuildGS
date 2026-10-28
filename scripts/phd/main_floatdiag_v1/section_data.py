"""Original GT/MVS points, prior plane intersections, first-hit patch points."""
import argparse
import ast
import json
import numpy as np
import open3d as o3d
from plyfile import PlyData
from common import *
from recount import load_eval
from geometry import reference

source=Path('/repo/scripts/phd/main_stage2_v1/figs_s2.py')
nodes=[x for x in ast.parse(source.read_text()).body if isinstance(x,ast.FunctionDef) and x.name in ['plane_segments','crop_mesh']]
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'))

def near(x,centre,tangent,length,width):
    s=(x[:,:2]-centre[:2])@tangent[:2];d=(x[:,:2]-centre[:2])@np.array([-tangent[1],tangent[0]])
    return (np.abs(s)<=length/2)&(np.abs(d)<=width),s

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',required=True);ap.add_argument('--prior',default='ALS');a=ap.parse_args()
    cases=[x for x in json.loads((CFG/f'cases_{a.prior}.json').read_text())['cases'] if x['site']==a.site]
    e,_=load_eval(a.site,a.prior);gt,gtpath=reference(a.site)
    with np.load(S1/'defs'/a.site/f'prior_{a.prior}.npz') as f:pv,pf=f['V'].astype(float),f['F'].astype(int)
    mp=PH/'main_axes71_v2/PHD-MAIN-AXES71-v2/mvs'/a.site/'mesh_mvs_a.ply'
    mesh=o3d.io.read_triangle_mesh(str(mp));mvs=np.asarray(mesh.vertices)
    dyn=f'lt_dynnow_{a.prior}_s0';model=model_path(a.site,dyn)
    cloud=PlyData.read(str(model/'point_cloud/iteration_30000/point_cloud.ply'),mmap='r')['vertex'].data
    gx=np.column_stack([cloud[k] for k in ['x','y','z']]);mem=np.load(OUT/'gaussians'/a.site/dyn/'membership.npz')
    for c in cases:
        b=np.array(c['bbox']);centre=np.r_[c['centre_xy'],0.];direction=int(np.argmax(b[2:]-b[:2]));t=np.zeros(3);t[direction]=1
        length=float((b[2:]-b[:2])[direction]+8);width=.375
        if c['id']=='B173-날개':
            start=np.array([146.68,96.32]);end=np.array([136.63,99.34]);centre=np.r_[(start+end)/2,0.]
            length=float(np.linalg.norm(end-start));t=np.r_[(end-start)/length,0.];width=.6
        arrays={};m,s=near(gt,centre,t,length,width);arrays['gt']=np.c_[s[m],gt[m,2]]
        m,s=near(mvs,centre,t,length,width);arrays['mvs']=np.c_[s[m],mvs[m,2]]
        arrays['prior_segments']=np.array(plane_segments(*crop_mesh(pv,pf,centre,length/2+2),centre,t,length/2))
        for res in [f'{x}_{a.prior}_s0' for x in ['nojudge','lt_dyngt','lt_dynnow']]:
            with np.load(LT/'patch_z'/f'{a.site}__{a.prior}__{res}.npz') as f:z=f['z'];no=f['no_surface']
            x=e['centre']+z[:,None]*e['normal'];m,s=near(x,centre,t,length,width)
            m &= e['in_eval']&e['scoring_allowed']&~no&np.isfinite(x).all(1)
            arrays[res]=np.c_[s[m],x[m,2]]
        m,s=near(gx,centre,t,length,width);m&=mem['opacity']>=.1
        arrays['gaussian']=np.c_[s[m],gx[m,2]];arrays['lineage']=mem['lineage'][m]
        folder=OUT/'sections';folder.mkdir(exist_ok=True);np.savez_compressed(folder/(c['id']+'.npz'),**arrays)
        save(folder/(c['id']+'.json'),dict(case=c['id'],site=a.site,centre=centre.tolist(),tangent=t.tolist(),length_m=length,
            half_width_m=width,counts={k:len(v) for k,v in arrays.items()},gt_source=str(gtpath),mvs_source=str(mp),
            mvs_sha256=sha(mp),method='unreduced source points; exact prior triangle-plane intersections; original normal-ray first-hit patch points; dynnow Gaussian centres opacity>=0.1',scientific_verdict=None))
    print(a.site,'section data PASS',flush=True)

if __name__=='__main__':main()
