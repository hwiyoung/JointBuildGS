"""The RESCORE final-mesh recipe, in the FINALTRAIN output tree."""
import ast,copy,sys,time
from common import *
sys.path.insert(0,'/repo')
from src.phd import streamed_tsdf as T

def prepare(site,prior):
    start=time.monotonic();stem=f'{site}__{prior}';wd=O/'meshes'/stem/'final_work';rr=wd.parent/'render';r=json.loads((rr/'receipt.json').read_text());assert r['status']=='PASS'
    dest=wd/'inputs';dest.mkdir(parents=True,exist_ok=True);views=r['views'];H,W=views[0]['height'],views[0]['width']
    depth=np.lib.format.open_memmap(dest/'depth_masked.npy','w+',dtype='f4',shape=(len(views),H,W));rgb=np.lib.format.open_memmap(dest/'rgb.npy','w+',dtype='u1',shape=(len(views),H,W,3));intr=[];extr=[]
    for i,v in enumerate(views):
        p=rr/v['file'];assert sha(p)==v['sha256'];z=loadz(p);depth[i]=z['depth'];rgb[i]=z['rgb'];k=np.asarray(v['K']);intr.append([k[0,0],k[1,1],k[0,2],k[1,2]]);extr.append(v['W2C'])
    depth.flush();rgb.flush();np.savez(dest/'cams.npz',names=[v['name'] for v in views],intr=intr,wh=[[W,H]]*len(views),extrinsic=extr)
    dump(dest/'meta.json',dict(site=site,result='ft_'+stem,prior_scene=prior,depth_dir=str(rr),box=r['box'],height=H,width=W,views=len(views),views_without_depth=[],
        mean_share_of_pixels_in_box=float(np.mean([v['mask_fraction'] for v in views])),mean_share_of_pixels_with_depth=float(np.mean([v['depth_fraction'] for v in views])),seconds=time.monotonic()-start,scientific_verdict=None))
    dump(wd/'binding.json',dict(at=now(),render_receipt_sha256=sha(rr/'receipt.json'),streamed_tsdf_sha256=sha(R/'src/phd/streamed_tsdf.py'),voxel_m=.05,trunc_m=.25,scientific_verdict=None))

def finish(site,prior):
    import open3d as o3d
    start=time.monotonic();stem=f'{site}__{prior}';wd=O/'meshes'/stem/'final_work';mesh=o3d.io.read_triangle_mesh(str(wd/'merged.ply'));raw=len(mesh.triangles)
    source=PH/'main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1/received/geogs_original/utils/mesh_utils.py'
    fn=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='post_process_mesh');ns=dict(np=np,o3d=o3d,copy=copy)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),ns);mesh=ns['post_process_mesh'](mesh,cluster_to_keep=50);clean=len(mesh.triangles)
    pcfg=json.loads((R/'configs/phd/main_prep_measure_v1/prep_v5.json').read_text());a=np.deg2rad(pcfg['frame']['u_axis_angle_degrees_ccw_from_easting']);basis=np.array([[np.cos(a),np.sin(a)],[np.sin(a),-np.cos(a)]])
    tr=loadz(PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1/defs'/site/'top_raster.npz',['eval_u','eval_v']);uv=np.asarray(mesh.vertices)[:,:2]@basis.T
    inside=(uv[:,0]>=tr['eval_u'][0])&(uv[:,0]<=tr['eval_u'][1])&(uv[:,1]>=tr['eval_v'][0])&(uv[:,1]<=tr['eval_v'][1]);mesh.remove_triangles_by_mask(~inside[np.asarray(mesh.triangles)].all(1));mesh.remove_unreferenced_vertices()
    path=wd.parent/'final.ply';assert len(mesh.triangles)>0;assert o3d.io.write_triangle_mesh(str(path),mesh)
    dump(wd.parent/'final.json',dict(at=now(),status='PASS',raw_triangles=raw,cleanup_triangles=clean,final_triangles=len(mesh.triangles),mesh_sha256=sha(path),cleanup_source=str(source),cleanup_sha256=sha(source),
        voxel_m=.05,trunc_m=.25,cluster_to_keep=50,training=False,seconds=time.monotonic()-start,scientific_verdict=None))

def main():
    mode,site,prior=sys.argv[1:4];cfg();wd=O/'meshes'/f'{site}__{prior}'/'final_work';start=time.monotonic()
    if mode=='prepare':prepare(site,prior)
    elif mode=='plan':T.plan(wd,'auto:18');T.order(wd)
    elif mode=='tile':T.tile(wd,int(sys.argv[4]))
    elif mode=='merge':T.merge(wd,wd/'merged.ply',wd/'merged.json')
    elif mode=='finish':finish(site,prior)
    else:raise ValueError(mode)
    dump(O/'timing'/f'{site}__{prior}_mesh_{mode}_{sys.argv[4] if len(sys.argv)>4 else "all"}.json',dict(at=now(),seconds=time.monotonic()-start,scientific_verdict=None))
    print('MESH_DONE',mode,site,prior,flush=True)
if __name__=='__main__':main()
