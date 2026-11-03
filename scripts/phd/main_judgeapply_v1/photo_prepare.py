"""Reuse matched historical photo points; create missing 2x2 groups with the same grid rule.

Source-only adapters: regional mesh, regional cameras, and single r-shifted prior
height. Plane fitting, support masks, view selection and grouping equations are inherited.
"""
from common import *
from cameras import Cameras
from inherit import functions
from scipy.spatial import cKDTree
import ast,types,warnings,resource
DR=PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1'
UV=np.stack(np.meshgrid(np.arange(25)*.02-.24,np.arange(25)*.02-.24,indexing='xy'),-1).reshape(625,2)
defs=json.loads((R/'configs/phd/main_widen0_v2/widen0_v2.json').read_text())['definitions']
scope=dict(np=np,cKDTree=cKDTree,UV=UV,DEFINITIONS=defs,DEFS=defs)
functions('u_core.py',['find_face'],scope)
tangent,fit_mvs,in_triangles=functions('photo_planes.py',['tangent','fit_mvs','in_triangles'],scope)
functions('photo_planes.py',['column','plane'],scope)
PHOTO_HALF_LENGTH=10.
def regional_column(X,tree,c,n):
    H=PHOTO_HALF_LENGTH
    probes=c+np.arange(-H+.25,H,.5)[:,None]*n
    ids=np.unique(np.concatenate([np.asarray(a,int) for a in tree.query_ball_point(probes,np.hypot(.5,.25)+1e-6)]))
    v=X[ids]-c;t=v@n;rho2=np.maximum(0,np.sum(v*v,1)-t*t)
    keep=(rho2<=.25)&(abs(t)<=H);ids=ids[keep];t=t[keep]
    o,_,_=scope['find_face'](t,H,defs)
    if o is None:return np.empty((0,3))
    return X[ids[abs(t-o)<=1.]]
scope['column']=regional_column
fitted_normals,prior_height,als_mask,mvs_mask=functions('photo_prepare_reply2.py',['fitted_normals','prior_height','als_mask','mvs_mask'],scope)
choose_mvs_views,=functions('photo_cameras.py',['choose_mvs_views'],scope)
scope['mesh_scene']=lambda site,prior:mesh_scene(site,prior)
select_photos,=functions('main_photocheck_v1__cameras.py',['select_photos'],scope)
def mesh_data(site,prior):
    m=loadz(DR/'s02_box'/site/('lod2_mesh.npz' if prior=='LoD2' else 'als_mesh.npz'))
    shift=np.array(json.loads((S0/'s61/box'/site/prior/'summary.json').read_text())['registration']['shift_applied'])
    m['V']=m['V']+shift;return m
def mesh_scene(site,prior):
    import open3d as o3d
    m=mesh_data(site,prior);scene=o3d.t.geometry.RaycastingScene(nthreads=4)
    scene.add_triangles(o3d.core.Tensor(m['V'].astype('f4')),o3d.core.Tensor(m['F'].astype('u4')));return scene
def new_groups(d,prior,site,full):
    # Exact inherited group(); change only its source of complete surface origins.
    p=HERE/'inherited/main_photocheck_v1__prepare.py';tree=ast.parse(p.read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='group')
    class SourceAdapter(ast.NodeTransformer):
        def visit_With(self,n):
            if isinstance(n.items[0].optional_vars,ast.Name) and n.items[0].optional_vars.id=='source':
                return [ast.Assign(targets=[ast.Name(id='source',ctx=ast.Store())],value=ast.Name(id='regional_source',ctx=ast.Load()))]+n.body
            return n
    node=ast.fix_missing_locations(SourceAdapter().visit(node))
    env=dict(np=np,regional_source=full,sigmas=lambda d,p:(d['sigma_P_m'],d['u_mvs']))
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(p),'exec'),env)
    return env['group'](d,prior,site)
def group_points(d,site,prior):
    old=loadz(TG/'r7/targets'/f'{site}_{prior}.npz',['photo_point_id']);saved=old['photo_point_id'][d['source_index']]
    N=len(saved);rows=[];owner=np.full(N,-1,int)
    for kind in cfg()['priors'][prior]:
      pids=sorted(set(saved[d['kind']==kind])-{''})
      bytile={}
      for pid in pids:bytile.setdefault(pid.split(':')[-3],[]).append(pid)
      for tile,pids in bytile.items():
        root=PH/('main_photocheck_v1/PHD-MAIN-PHOTOCHECK-v1' if kind==1 else 'main_wallphoto_v1/PHD-MAIN-WALLPHOTO-v1')
        p=root/'points'/f'{tile}__{prior}.npz'
        with np.load(p) as z:
          lookup={x:i for i,x in enumerate(z['point_id'])}
          data={k:z[k] for k in ['centre','normal','tangent1','tangent2']}
        for pid in pids:
          ix=np.flatnonzero((saved==pid)&(d['kind']==kind));j=lookup.get(pid)
          if j is None:continue
          assert len(np.unique(d['surf'][ix]))==1,(site,prior,kind,pid,np.unique(d['surf'][ix]))
          row={k:v[j] for k,v in data.items()};row.update(point_id=pid,kind=kind,surf=int(d['surf'][ix[0]]),building=str(d['building'][ix[0]]),source='inherited exact TARGET photo_point_id')
          owner[ix]=len(rows);rows.append(row)
    missing=np.flatnonzero(owner<0)
    if len(missing):
        full=loadz(TG/'stage0_r1/inputs'/f'{site}_{prior}.npz',['centre','kind','surf'])
        full['source_extra']=loadz(S0/'s61/box'/site/prior/'units.npz',['loc_extra'])['loc_extra']
        inp={k:v[missing] for k,v in d.items()};inp['holdout']=np.zeros(len(missing),bool);inp['mvs_p']=inp['mvs_mean_m']
        group,own,audit=new_groups(inp,prior,site,full)
        offset=len(rows);owner[missing]=offset+own
        for i in range(len(group['point_id'])):
            row={k:group[k][i] for k in ['centre','normal','tangent1','tangent2','kind','surf','building']}
            row.update(point_id=f'{prior}:{site}:newpoint:{i}',source='[이 발주에서 냄] inherited 0.5m grouping');rows.append(row)
    assert (owner>=0).all()
    g={k:np.array([r[k] for r in rows]) for k in rows[0]};g['area']=np.bincount(owner,weights=d['area']);g['patch_count']=np.bincount(owner)
    g['target']=np.bincount(owner,weights=(d['n']>=4).astype(int))>0
    g['all_within']=np.bincount(owner,weights=(d['geometry']!=0).astype(int))==0
    g['dbar']=np.full(len(rows),np.nan);g['r_m']=np.full(len(rows),np.nan)
    for i in range(len(rows)):
        ii=np.flatnonzero(owner==i);v=d['d_m'][ii];v=v[(d['n'][ii]>=4)&np.isfinite(v)]
        if len(v):g['dbar'][i]=np.median(v)
        g['r_m'][i]=d['r_m'][ii[0]]
    return g,owner
def main(site):
    global PHOTO_HALF_LENGTH
    start=time.monotonic();X=np.load(UN/'points'/site/'mvs_a_xyz.npy').astype(float);tree=cKDTree(X,leafsize=32,balanced_tree=False,compact_nodes=False)
    A=np.load(UN/'points'/site/'als_xyz.npy');atree=cKDTree(A,leafsize=32,balanced_tree=False,compact_nodes=False);cam=Cameras(site)
    shared=time.monotonic()-start;rows=[];parts=[]
    for prior in cfg()['priors']:
      d=loadz(O/'geometry'/f'{site}__{prior}.npz');g,owner=group_points(d,site,prior)
      savez(O/'photo_mapping'/f'{site}__{prior}.npz',patch_id=d['patch_id'],point_index=owner,point_id=g['point_id'][owner])
      savez(O/'photo_geometry'/f'{site}__{prior}.npz',**g)
      active=np.flatnonzero(g['target']);N=len(active);h=g['centre'][active];normal=g['normal'][active].copy();hp=np.zeros(N);rule=np.ones(N,bool);priorn=np.full(N,-1,int)
      support=None
      if prior=='ALS':
          normal,rule=fitted_normals(A,atree,h)
          for i in range(N):hp[i],priorn[i]=prior_height(A,atree,h[i],normal[i])
          support={bid:cKDTree(d['centre'][d['building']==bid]) for bid in np.unique(d['building'])}
      else:
          mesh=mesh_data(site,'LoD2');tris={int(s):mesh['V'][mesh['F'][mesh['tri_surface']==s]] for s in np.unique(g['surf'])}
      centres=np.full((N,2,3),np.nan);normals=centres.copy();e1=centres.copy();e2=centres.copy();avail=np.zeros((N,2),bool);masks=np.zeros((N,2,625),bool)
      count=np.zeros(N,int);res=np.full(N,np.nan);angle=res.copy();fitreason=np.full(N,'prior_plane_unavailable',dtype='<U40')
      geomstart=time.monotonic()
      for i,gi in enumerate(active):
        c=h[i];n=normal[i]
        if not np.isfinite(n).all() or not np.isfinite(hp[i]) or not np.isfinite(g['r_m'][gi]):continue
        pc=c+(hp[i]+g['r_m'][gi])*n;centres[i,0]=pc;normals[i,0]=n;avail[i,0]=True
        e1[i,0],e2[i,0]=(g['tangent1'][gi],g['tangent2'][gi]) if prior=='LoD2' else tangent(n)
        PHOTO_HALF_LENGTH=5. if g['kind'][gi]==2 else 10.
        fitted,meta=fit_mvs(X,tree,c,n,hp[i],g['dbar'][gi]);count[i]=meta['point_count'];fitreason[i]=meta['reason']
        if fitted is not None:
            centres[i,1],normals[i,1]=fitted;avail[i,1]=True;e1[i,1],e2[i,1]=tangent(fitted[1]);res[i]=meta['residual_nmad_m'];angle[i]=meta['normal_angle_deg']
        for j in range(2):
            if not avail[i,j]:continue
            cc,nn,a,b=centres[i,j],normals[i,j],e1[i,j],e2[i,j]
            if j==1:masks[i,j]=mvs_mask(X,tree,cc,nn,a,b,np.array([0.]))[0]
            elif prior=='ALS':
                masks[i,j]=als_mask(support[str(g['building'][gi])],cc,nn,a,b,np.array([0.]))[0]
            else:masks[i,j]=in_triangles(cc+UV[:,0,None]*a+UV[:,1,None]*b,tris[int(g['surf'][gi])],cc,a,b)
        if i%2000==0:print('PHOTO_PREPARE',site,prior,i,N,'seconds',time.monotonic()-geomstart,flush=True)
      geometry_seconds=time.monotonic()-geomstart;vstart=time.monotonic()
      gg=dict(centre=centres[:,0],normal=normals[:,0],tangent1=e1[:,0],tangent2=e2[:,0],geometry_valid=avail[:,0])
      selected=np.full((N,2,10),-1,np.int32);selected[:,0]=select_photos(gg,cam,site,prior)['selected_images']
      selected[:,1]=choose_mvs_views(centres[:,1],normals[:,1],e1[:,1],e2[:,1],cam,avail[:,1]);visseconds=time.monotonic()-vstart
      part=dict(point_id=g['point_id'][active],source_index=active,prior=np.full(N,prior),kind=g['kind'][active],area=g['area'][active],all_within=g['all_within'][active],
           centres=centres,normals=normals,tangent1=e1,tangent2=e2,available=avail,selected_images=selected,masks=masks,prior_height_m=hp,prior_n=priorn,prior_normal_rule_met=rule,
           mvs_fit_count=count,mvs_fit_nmad_m=res,mvs_normal_angle_deg=angle,mvs_fit_reason=fitreason,photo_centre=h,photo_normal=normal)
      parts.append(part);rows.append(dict(prior=prior,all_points=len(g['point_id']),scored_points=N,created_points=int(sum(str(x).startswith('[이 발주에서 냄]') for x in g['source'])),geometry_seconds=geometry_seconds,visibility_seconds=visseconds))
    result={k:np.concatenate([p[k] for p in parts]) for k in parts[0]};N=len(result['point_id']);av=result['available'].ravel();planes=np.flatnonzero(av)
    result.update(row_plane=planes.astype('i4'),row_height=np.zeros(len(planes)),mask_bits=np.packbits(result.pop('masks').reshape(2*N,625)[planes],axis=1),plane_row_ptr=np.r_[0,np.cumsum(av)],mask_fraction_at_zero=np.zeros((N,2)))
    fractions=np.full(2*N,np.nan);fractions[planes]=np.unpackbits(result['mask_bits'],axis=1,count=625).mean(1);result['mask_fraction_at_zero']=fractions.reshape(N,2)
    savez(O/'photo_prepared'/f'{site}.npz',**result)
    rec=dict(at=now(),site=site,shared_load_tree_seconds=shared,rows=rows,total_seconds=time.monotonic()-start,peak_rss_gib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2,scientific_verdict=None)
    dump(O/'timing'/f'{site}_photo_prepare.json',rec);print('PHOTO_PREPARE_COMPLETE',json.dumps(rec),flush=True)
if __name__=='__main__':main(sys.argv[1])
