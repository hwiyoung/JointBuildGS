"""r8 seed rules and disc rasterization, with FINALTRAIN target and pixel weights."""
import ast,ctypes,os,subprocess,sys,time
from common import *
from plyfile import PlyData

def named_functions(path,names,env):
    tree=ast.parse(path.read_text());nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names]
    assert len(nodes)==len(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),env)

def cameras(site):
    own=sys.modules.pop('common');oldpath=sys.path[:]
    os.environ['FINALTRAIN_SITE']=site;sys.path.insert(0,str(Path(__file__).parent/'inherited_judgeapply'))
    try:
        from cameras import Cameras
        c=Cameras(site)
    finally:sys.modules['common']=own;sys.path[:]=oldpath
    return [dict(name=n,H=741,W=1024,W2C=c.M[i],fx=c.K[0,0],fy=c.K[1,1],cx=c.K[0,2],cy=c.K[1,2]) for i,n in enumerate(c.names)]

def seeds(site,prior,t,root):
    sys.path.insert(0,str(R))
    from src.phd.prior_propagation_v6.locations import locate
    from src.phd.prior_propagation_v6.orientation import quat_from_normal
    f=S0/'fork_inputs/s61'/site;source=f/f'scene_{prior}/sparse/0';ply=source/'points3D.ply'
    v=PlyData.read(str(ply))['vertex'];xyz=np.c_[v['x'],v['y'],v['z']].astype('f4');rgb=np.c_[v['red'],v['green'],v['blue']].astype('f4')/255
    origin=np.load(source/'origin.npy');seat=np.load(f/f'seat_{prior}.npy');store=loadz(f/f'store_{prior}.npz')
    loc=np.full(len(xyz),-1,np.int64);has=(origin==1)&(seat>=0);loc[has]=locate(store,seat[has],xyz[has].astype(float))
    keep=np.flatnonzero(has&(loc>=0)&t['surface_exists'][np.maximum(loc,0)]);pid=loc[keep]
    raw=loadz(TG/'stage0_r1/inputs'/f'{site}_{prior}.npz')
    c2=json.loads((R/'configs/phd/main_target_v1/revisions/r2/target_v1.json').read_text())
    radius=np.array([c2['inherited_radius'][prior][str(int(k))]['radius_m'] or np.nan for k in raw['kind']])
    fallback=json.loads((O/'outside'/site/'budget_receipt.json').read_text())['status']=='TIME_LIMIT_BACKGROUND_FALLBACK'
    exclude_mask=raw['in_eval'] if fallback else np.ones(len(radius),bool)
    cores=root/'cylinders.bin';np.c_[raw['centre'][exclude_mask],raw['normal'][exclude_mask],np.where(raw['kind'][exclude_mask]==1,10.,5.),radius[exclude_mask]].astype('<f8').tofile(cores)
    ids=np.flatnonzero(origin==0);np.save(root/'sfm_original_xyz.npy',xyz[ids]);cpp=R/'scripts/phd/main_target_v1/exclude_cylinders_r2.cpp';binary=root/'exclude_cylinders'
    subprocess.run(['g++','-O3','-std=c++17',str(cpp),'-o',str(binary)],check=True)
    with (root/'sfm_original_xyz.npy').open('rb') as f:
        version=np.lib.format.read_magic(f);np.lib.format._read_array_header(f,version);offset=f.tell()
    subprocess.run([str(binary),str(root/'sfm_original_xyz.npy'),str(offset),str(len(ids)),str(cores),str(int(exclude_mask.sum())),str(root/'excluded.bin')],check=True)
    excluded=np.fromfile(root/'excluded.bin',dtype=np.uint8).astype(bool);bg=ids[~excluded];nb=len(bg)
    raw_u=raw['mvs_a_u'];donors=raw_u[(raw['kind']==1)&np.isfinite(raw_u)]
    assert len(donors) and np.median(donors)>0;bg_sigma=float(np.hypot(np.median(donors),.0275))
    normal=np.r_[t['normal'][pid],np.tile([0.,0.,1.],(nb,1))];pos=np.r_[t['target'][pid],xyz[bg]]
    sigma=np.r_[t['sigma'][pid],np.full(nb,bg_sigma)]
    assert np.isfinite(pos).all() and np.isfinite(sigma).all() and (sigma>0).all()
    savez(root/'seeds.npz',original_xyz=xyz,keep_original=keep,xyz=pos.astype('f4'),target=pos.astype('f4'),normal=normal.astype('f4'),sigma=sigma.astype('f4'),
        quaternion=quat_from_normal(normal).astype('f4'),origin=np.r_[np.ones(len(pid),'i1'),np.zeros(nb,'i1')],region=np.r_[t['region'][pid],np.full(nb,4,'i1')],
        patch=np.r_[pid,np.full(nb,-1,'i8')],background_rgb=rgb[bg],background_original=bg,uncertainty_replaced=np.r_[t['sigma_replaced'][pid],np.ones(nb,bool)])
    rec=dict(at=now(),prior_kept=len(pid),background_kept=nb,source_ply_sha256=sha(ply),source_origin_sha256=sha(source/'origin.npy'),
        source_seat_sha256=sha(S0/'fork_inputs/s61'/site/f'seat_{prior}.npy'),source_store_sha256=sha(S0/'fork_inputs/s61'/site/f'store_{prior}.npz'),
        seeds_sha256=sha(root/'seeds.npz'),exclusion_code_sha256=sha(cpp),cylinders_sha256=sha(cores),fallback_outside_background=fallback,
        background_sigma=bg_sigma,background_bound=False,initialization='r8 baseline prior count/scale/colour; SfM exclusion and random rotation; no additional thinning',scientific_verdict=None)
    dump(root/'seed_receipt.json',rec);return bg_sigma

def main(site,prior):
    start=time.monotonic();cfg();stem=f'{site}__{prior}';tp=O/'targets'/f'{stem}.npz';t=loadz(tp);root=O/'stage1'/stem;root.mkdir(parents=True,exist_ok=False)
    bg_sigma=seeds(site,prior,t,root)
    src=R/'scripts/phd/main_target_v1/prepare_maps_r7.py';env=dict(np=np,ctypes=ctypes,subprocess=subprocess,Path=Path,__file__=str(src),OUT=O)
    named_functions(src,['rasterizer','draw'],env);fn=env['rasterizer']();ids=np.flatnonzero(t['surface_exists'])
    points=np.c_[t['target'][ids],t['normal'][ids],np.sqrt(t['area'][ids]/np.pi),ids].astype(float);ref=float(t['sigma_ref']);dest=root/'maps';dest.mkdir()
    camera_root=S0/'fork_inputs/s61'/site
    index=dict(at=now(),site=site,prior=prior,sigma_ref=ref,weight_power=1,background_weight=1,target_sha256=sha(tp),
        input_files={str(p):sha(p) for p in [camera_root/'split.json',camera_root/'scene_LoD2/jbgs_calibration.json',camera_root/'scene_LoD2/sparse/0/images.bin',src,src.with_name('target_discs.cpp')]},
        views={},scientific_verdict=None)
    weight_samples=[];total=low=high=0
    for j,cam in enumerate(cameras(site)):
        depth,owner,K,M=env['draw'](fn,points,cam);has=owner>=0;name=cam['name'];sigma=np.full(depth.shape,np.nan,'f4');sigma[has]=t['sigma'][owner[has]]
        old=S0/'fork_inputs/s61'/site/'maps';mvs=np.load(old/'mvs'/f'{name}.npy');conf=np.load(old/'conf'/f'{name}.npy')
        bg=(~has)&np.isfinite(mvs)&(mvs>0)&(conf>0);depth[bg]=mvs[bg];sigma[bg]=bg_sigma
        weight=np.zeros(depth.shape,'f4');weight[has]=np.clip(ref/sigma[has],.1,10);weight[bg]=1
        w=weight[has];total+=len(w);low+=int((w<=np.float32(.1)).sum());high+=int((w>=10).sum())
        # Exact distribution over all patch pixels is reduced after concatenation.
        weight_samples.append(w)
        p=dest/f'{name}.npz';savez(p,depth=depth,sigma=sigma,weight=weight,owner=owner)
        index['views'][name]=dict(file=p.name,sha256=sha(p),sigma_ref=ref,prior_pixels=int(has.sum()),background_pixels=int(bg.sum()),K=K.tolist(),W2C=M.tolist(),
            mvs_input_sha256=sha(old/'mvs'/f'{name}.npy'),confidence_input_sha256=sha(old/'conf'/f'{name}.npy'))
        if (j+1)%40==0:print('MAPS',stem,j+1,flush=True)
    w=np.concatenate(weight_samples);dump(dest/'index.json',index)
    rec=dict(at=now(),site=site,prior=prior,seconds=time.monotonic()-start,sigma_ref=ref,
        patch_pixels=total,weight_q01_q10_q50_q90_q99=np.quantile(w,[.01,.1,.5,.9,.99]).tolist(),clip_low_fraction=low/total,clip_high_fraction=high/total,
        map_index_sha256=sha(dest/'index.json'),seeds_sha256=sha(root/'seeds.npz'),target_sha256=sha(tp),scientific_verdict=None)
    dump(root/'ready.json',rec);dump(D/'tables'/f'pixel_weights_{stem}.json',rec);print('INPUTS_READY',stem,rec['seconds'],flush=True)
if __name__=='__main__':main(*sys.argv[1:])
