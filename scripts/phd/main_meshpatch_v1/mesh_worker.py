"""One frozen whole-mesh cleanup and unchanged pre/post measurements, CPU only."""
import argparse,ast,gc,sys,time,traceback,copy
import open3d as o3d
from scipy.spatial import cKDTree
from mesh_common import *

def original_cleanup(cfg):
    p=Path(cfg['source_function']['path']);assert sha(p)==cfg['source_function']['sha256']
    tree=ast.parse(p.read_text());node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='post_process_mesh')
    ns=dict(np=np,o3d=o3d,copy=copy)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(p),'exec'),ns)
    return ns['post_process_mesh']

def first_hit(mesh,e,v):
    # Exact mesh_score.py arithmetic, batching and float conversions.
    sc=o3d.t.geometry.RaycastingScene(nthreads=8)
    if len(mesh.triangles):sc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    dm=np.nan_to_num(e['p_mvs'],nan=0.);dg=np.nan_to_num(e['p_gt'],nan=0.)
    start=np.maximum(6.,np.maximum(dm+.5,dg+.5));end=np.minimum(-6.,np.minimum(dm-.5,dg-.5))
    c=e['centre'];n=e['normal'];z=np.full(len(c),np.nan);ids=np.flatnonzero(e['in_eval']&e['scoring_allowed'])
    for st in range(0,len(ids),50000):
        q=ids[st:st+50000];rays=np.c_[c[q]+start[q,None]*n[q],-n[q]].astype(np.float32)
        hit=sc.cast_rays(o3d.core.Tensor(rays))['t_hit'].numpy().astype(np.float64)
        valid=np.isfinite(hit)&(hit<=start[q]-end[q]);z[q[valid]]=start[q[valid]]-hit[valid]
    dp=np.abs(z)/v['sigma_prior'].astype(np.float64);dd=np.abs(z-e['p_mvs'])/v['sigma_mvs'].astype(np.float64)
    side=np.where(~np.isfinite(z),3,np.where((dp<=3)&((dd>3)|~np.isfinite(dd)|(dp<=dd)),0,np.where(dd<=3,1,2))).astype(np.int8)
    return dict(z=z,no_surface=~np.isfinite(z),side=side,in_eval=e['in_eval'],scoring_allowed=e['scoring_allowed'])

def stage1_metrics(mesh,site,prior):
    # Imports read source definitions only; no old workstream outputs are written.
    sys.path.insert(0,'/repo/scripts/phd/main_stage1_v1');sys.path.insert(0,'/repo')
    import metrics_s1 as m
    from src.phd.metrics_v3.surface import MeshScene
    m.OUT=S1;inputs=m.Inputs(site,prior);res={};rows={}
    sc=MeshScene(np.asarray(mesh.vertices),np.asarray(mesh.triangles))
    m.spread(inputs,sc,None,res,rows);m.completeness(inputs,sc,res,rows)
    del sc,inputs,rows;gc.collect()
    # Compile the unchanged F1 prefix of the existing summary, stopping before M3C2.
    path=R/'scripts/phd/main_stage1_v1/metrics_s1.py';tree=ast.parse(path.read_text())
    node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='summary')
    body=[]
    for x in node.body:
        if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='cmp_' for t in x.targets):break
        body.append(x)
    # Avoid reading the same file twice: replace only its read_triangle_mesh call.
    class ReadMesh(ast.NodeTransformer):
        def visit_Call(self,x):
            if isinstance(x.func,ast.Attribute) and x.func.attr=='read_triangle_mesh':return ast.Name(id='_mesh',ctx=ast.Load())
            return self.generic_visit(x)
    body=[ReadMesh().visit(x) for x in body]
    body+=ast.parse('return dict(result_points=int(len(smp)),gt_points=int(len(Gb)),**cp_)').body
    node.body=body;ns=dict(m.__dict__,_mesh=mesh);mod=ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[]))
    exec(compile(mod,str(path),'exec'),ns)
    res['summary']=ns['summary'](site,'mesh',{'mesh':'already_loaded'},{});return res

def removed_areas(mesh,removed,e,before):
    V=np.asarray(mesh.vertices);F=np.asarray(mesh.triangles);elig=e['in_eval']&e['scoring_allowed']&(np.abs(e['normal'][:,2])>=np.cos(np.pi/4))
    ids=np.flatnonzero(elig);tree=cKDTree(e['centre'][ids,:2]);cat=classes(e,before)
    sums=np.zeros(6);counts=np.zeros(6,np.int64);removed_idx=np.flatnonzero(removed)
    for st in range(0,len(removed_idx),250000):
        T=V[F[removed_idx[st:st+250000]]];area=.5*np.linalg.norm(np.cross(T[:,1]-T[:,0],T[:,2]-T[:,0]),axis=1)
        dist,ix=tree.query(T.mean(1)[:,:2]);group=np.where(dist<=2**.5*.25,cat[ids[ix]],5)
        sums+=np.bincount(group,weights=area,minlength=6);counts+=np.bincount(group,minlength=6)
    return dict(categories=[dict(category=k,triangles=int(counts[i]),area_m2=float(sums[i])) for i,k in enumerate(CATEGORIES+['unavailable_spatial_join'])],
        triangles=int(counts.sum()),area_m2=float(sums.sum()),note='3D triangle area. Existing before-cleanup patch class is assigned by the frozen XY rule; not a new visibility or region calculation.')

def case_crops(mesh,row,stage,removed=None):
    if row['prior']!='ALS' or row['result'] not in ['nojudge_ALS_s0','lt_dynnow_ALS_s0']:return []
    cfg=json.loads((R/'configs/phd/main_floatdiag_v1'/f"geometry_{row['site']}_ALS.json").read_text());outputs=[]
    V=np.asarray(mesh.vertices);F=np.asarray(mesh.triangles)
    for case in cfg['cases']:
        path=O/'case_meshes'/case['id']/row['result']/f'{stage}.ply';path.parent.mkdir(parents=True,exist_ok=True)
        if removed is None:m=mesh.crop(o3d.geometry.AxisAlignedBoundingBox(np.array(case['crop_min']),np.array(case['crop_max'])))
        else:
            vertex_ok=((V>=case['crop_min'])&(V<=case['crop_max'])).all(1)
            use=removed&vertex_ok[F].all(1)
            # Build only the selected crop, not another whole-unit deep copy.
            inds,inv=np.unique(F[use],return_inverse=True);m=o3d.geometry.TriangleMesh()
            m.vertices=o3d.utility.Vector3dVector(V[inds]);m.triangles=o3d.utility.Vector3iVector(inv.reshape(-1,3))
            if mesh.has_vertex_colors():m.vertex_colors=o3d.utility.Vector3dVector(np.asarray(mesh.vertex_colors)[inds])
        if len(m.triangles):assert o3d.io.write_triangle_mesh(str(path),m,write_ascii=False)
        outputs.append(dict(case=case['id'],stage=stage,path=str(path),triangles=len(m.triangles),empty=len(m.triangles)==0))
    return outputs

def process(key):
    cfg=mesh_config()
    row=next(x for x in cfg['targets'] if x['key']==key);dest=D/'tables/meshes'/f'{key}.json'
    if dest.exists():return json.loads(dest.read_text())
    t=time.monotonic();status(key,'starting')
    result=dict(target=row,scientific_verdict=None,provenance='[이 발주에서 냄]',status=row['status'])
    if row['status']!='READY':dump(dest,result);return result
    mcfg=C/'mesh_metric_inputs_v1.json';assert sha(mcfg)==json.loads((C/'mesh_metric_inputs_v1.lock.json').read_text())['sha256']
    for x in json.loads(mcfg.read_text())['inputs']:
        if x['site'] in [None,row['site']]:assert sha(x['path'])==x['sha256'],x['path']
    epath=Path(row['evaluation']);vpath=Path(row['values']);source=Path(row['mesh'])
    assert sha(source)==row['sha256'];assert sha(epath)==row['evaluation_sha256'];assert sha(vpath)==row['values_sha256']
    e=dict(np.load(epath));v=dict(np.load(vpath));mesh=o3d.io.read_triangle_mesh(str(source));assert len(mesh.triangles)
    status(key,'before_measurement',triangles=len(mesh.triangles))
    before=first_hit(mesh,e,v);before_rows=summarize(e,before)
    rec=LT/'patch_z'/f'{key}.npz'
    if rec.exists():
        old=dict(np.load(rec));old_rows=summarize(e,old);errors=[]
        for aa,bb in zip(before_rows,old_rows):
            for field in ['within_tau_pct','floating_pct','no_surface_pct']:
                if aa[field] is not None:errors.append(abs(aa[field]-bb[field]))
        gate=dict(reference=str(rec),max_area_difference_pp=max(errors,default=0),status='PASS' if max(errors,default=0)<=.5 else 'STOP')
        result['before_reference_check']=gate
        if gate['status']=='STOP':
            result.update(status='STOP_BEFORE_BASELINE_MISMATCH',seconds=time.monotonic()-t);dump(dest,result);return result
    result['before']=before_rows
    zz=O/'patch_z';zz.mkdir(exist_ok=True);np.savez_compressed(zz/f'{key}__before.npz',**before)
    result['case_crops']=case_crops(mesh,row,'before')
    if 'stage1' in row['groups']:
        status(key,'stage1_before_metrics');result['stage1_before']=stage1_metrics(mesh,row['site'],row['prior']);gc.collect()
    status(key,'component_cleanup')
    # The returned mesh comes from the original function, unmodified.
    clean=original_cleanup(cfg)(mesh,cluster_to_keep=50)
    labels,counts,areas=mesh.cluster_connected_triangles();labels=np.asarray(labels);counts=np.asarray(counts);areas=np.asarray(areas)
    threshold=max(int(np.sort(counts)[-50]),50)
    F=np.asarray(mesh.triangles);deg=(F[:,0]==F[:,1])|(F[:,0]==F[:,2])|(F[:,1]==F[:,2])
    removed=(counts[labels]<threshold)|deg
    assert int((~removed).sum())==len(clean.triangles),'original-function triangle accounting changed'
    result['removed']=removed_areas(mesh,removed,e,before)
    result['case_crops']+=case_crops(mesh,row,'removed',removed)
    result['case_crops']+=case_crops(clean,row,'after')
    outdir=O/'mesh_post'/key;outdir.mkdir(parents=True,exist_ok=True);post=outdir/'fuse_post.ply'
    assert not post.exists();assert o3d.io.write_triangle_mesh(str(post),clean,write_ascii=False)
    np.savez_compressed(outdir/'removed_source_triangles.npz',removed=np.flatnonzero(removed),source_triangle_count=len(F))
    after_clusters,after_counts,after_areas=clean.cluster_connected_triangles();after_counts=np.asarray(after_counts)
    result['cleanup']=dict(before_triangles=len(F),after_triangles=len(clean.triangles),before_components=len(counts),
        after_components=len(after_counts),min_remaining_component_triangles=int(after_counts.min()) if len(after_counts) else None,
        count_threshold=threshold,cluster_to_keep=50,ties_retained=True,removed_degenerate_triangles=int((deg&(counts[labels]>=threshold)).sum()),
        output=str(post),output_sha256=sha(post),source_sha256=row['sha256'],original_function_sha256=cfg['source_function']['sha256'])
    del mesh,F,labels,counts,areas,removed,deg,after_clusters,after_counts,after_areas;gc.collect()
    status(key,'after_measurement');after=first_hit(clean,e,v);np.savez_compressed(zz/f'{key}__after.npz',**after);result['after']=summarize(e,after)
    if 'stage1' in row['groups']:
        status(key,'stage1_after_metrics');result['stage1_after']=stage1_metrics(clean,row['site'],row['prior'])
    result.update(status='PASS',seconds=time.monotonic()-t,finished_at=now());dump(dest,result)
    status(key,'complete',seconds=result['seconds'],after_triangles=result['cleanup']['after_triangles']);return result

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('key');x=a.parse_args()
    try:process(x.key)
    except Exception as ex:
        status(x.key,'FAILED',error=str(ex),traceback=traceback.format_exc())
        with (D/'issues.md').open('a') as f:f.write(f'\n- {now()}: {x.key} 메시 처리 실패: {type(ex).__name__}: {ex}. 해당 대상은 완료하지 않았으며 입력은 보존했다.\n')
        raise
