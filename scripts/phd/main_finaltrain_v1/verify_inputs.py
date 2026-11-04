"""Check what the training loader reads, independently against target files."""
import sys
from common import *
site,prior=sys.argv[1:];stem=f'{site}__{prior}';root=O/'stage1'/stem;t=loadz(O/'targets'/f'{stem}.npz');s=loadz(root/'seeds.npz')
patch=s['origin']==1;ids=s['patch'][patch]
for key,target in [('target','target'),('normal','normal'),('sigma','sigma'),('region','region')]:
    assert np.array_equal(s[key][patch],t[target][ids].astype(s[key].dtype)),key
index=json.loads((root/'maps/index.json').read_text());ref=float(t['sigma_ref']);assert index['sigma_ref']==ref
count=0;pixel=0;max_h_error=0
for name,rec in index['views'].items():
    p=root/'maps'/rec['file'];assert sha(p)==rec['sha256'];m=loadz(p);mask=m['owner']>=0;pid=m['owner'][mask]
    assert np.array_equal(m['sigma'][mask],t['sigma'][pid].astype('f4'))
    assert np.array_equal(m['weight'][mask],np.clip(ref/m['sigma'][mask],.1,10))
    bg=(~mask)&(m['weight']>0);assert (m['weight'][bg]==1).all();assert rec['sigma_ref']==ref
    v,u=np.where(mask);ix=np.arange(0,len(v),max(1,len(v)//2000));v,u=v[ix],u[ix];pids=m['owner'][v,u]
    K=np.asarray(rec['K']);M=np.asarray(rec['W2C']);cam=np.c_[(u-K[0,2])/K[0,0],(v-K[1,2])/K[1,1],np.ones(len(v))]*m['depth'][v,u,None]
    world=(cam-M[:3,3])@M[:3,:3];h=((world-t['centre'][pids])*t['normal'][pids]).sum(1)
    err=np.abs(h-t['h'][pids]);median=float(np.median(err)) if len(err) else 0;assert median<=.01,(name,median)
    max_h_error=max(max_h_error,median);count+=1;pixel+=len(pid)
rec=dict(at=now(),site=site,prior=prior,status='PASS',seed_target_and_sigma_exact=True,all_map_sigmas_exact=True,all_patch_weights_exact=True,
    background_weights_one=True,scene_sigma_ref=ref,views=count,checked_patch_pixels=pixel,max_view_median_height_error_m=max_h_error,
    target_sha256=sha(O/'targets'/f'{stem}.npz'),seeds_sha256=sha(root/'seeds.npz'),index_sha256=sha(root/'maps/index.json'),scientific_verdict=None)
dump(O/'verification'/f'inputs_{stem}.json',rec);print('PASS_INPUTS',stem,count,pixel,flush=True)
