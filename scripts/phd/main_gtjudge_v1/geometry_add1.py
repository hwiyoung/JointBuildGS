"""Inherited coordinate frames, exact samples, and pointcloud reference normals."""
import ast,gc,sys
import numpy as np
from scipy.spatial import cKDTree
from common import *
sys.path.insert(0,'/repo')
from src.phd.metrics_v3.surface import MeshScene

def inherit(path,names,scope):
    nodes=[x for x in ast.parse(Path(path).read_text()).body if isinstance(x,(ast.FunctionDef,ast.ClassDef)) and x.name in names]
    assert len(nodes)==len(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),scope)
    return {n:scope[n] for n in names}

globals().update(inherit(R/'scripts/phd/main_rescore_v1/figures.py',['read_surface','section_segments','section_points'],dict(np=np,Path=Path,loadz=loadz)))

class Grid:
    def __init__(self,site):self.data=loadz(S1/'defs'/site/'bsurf.npz')
    def in_cells(self,P):
        b=self.data
        x=np.floor((P[:,0]+690953-float(b['e0']))/float(b['res'])).astype('i8')
        y=np.floor((P[:,1]+5336071-float(b['n0']))/float(b['res'])).astype('i8')
        return np.isin(y*int(b['nx'])+x,b['keys'])

def views(site):
    path=RS/('addendum3_stage1' if site=='B173nb_b10' else 'addendum3_stage2')/'views'/f'{site}.json'
    z=json.loads(path.read_text());v=[x for x in z['views'] if not x['virtual']]
    return v,path

def orient(P,N,wall,centres):
    N=np.asarray(N,float).copy();N/=np.linalg.norm(N,axis=1)[:,None]
    sign=N[:,2]<0
    if np.any(wall):
        q=cKDTree(centres).query(P[wall],workers=4)[1]
        sign[wall]=np.einsum('ij,ij->i',N[wall],centres[q]-P[wall])<0
    N[sign]*=-1
    return N

def reference(site):
    root=O/'reference'/site;root.mkdir(parents=True,exist_ok=True)
    p=root/'dense.npz'
    if not p.exists():
        z=loadz(S1/'defs'/site/'gt_classes.npz');grid=Grid(site)
        normalfile=PH/'main_axes71_v2/PHD-MAIN-AXES71-v2/work'/f'normals_{site}.npz'
        nn=loadz(normalfile);vv,vpath=views(site)
        centres=np.array([np.linalg.inv(v['W2C'])[:3,3] for v in vv])
        allp=[];alln=[];allwall=[];parts=[];normal_points=[];normal_values=[]
        for source,name in [(0,'gt_points'),(1,'gt_primary')]:
            if 'xyz_'+name not in z:continue
            use=nn[f'use_{source}'];points=z['xyz_'+name][use].astype(float)
            normal_points.append(points);normal_values.append(nn[f'normal_{source}'])
            take=z['use_'+name][use].astype(bool)&grid.in_cells(points)
            N=nn[f'normal_{source}'][take].astype(float);P=points[take]
            wall=z['vert_'+name][use][take].astype(bool)
            valid=np.isfinite(N).all(1)&(np.linalg.norm(N,axis=1)>0)
            assert valid.all(),'AXES normal invalid in inherited used reference points'
            allp.append(P);alln.append(orient(P,N,wall,centres));allwall.append(wall)
            parts.append(dict(source=source,name=name,n=len(P)))
        savez(root/'normal_points.npz',xyz=np.concatenate(normal_points),normal=np.concatenate(normal_values))
        P=np.concatenate(allp);N=np.concatenate(alln);wall=np.concatenate(allwall)
        del normal_points,normal_values
        del z,nn,allp,alln;gc.collect()
        tree=cKDTree(P);spacing=tree.query(P,k=2,workers=4)[0][:,1];med=float(np.median(spacing));radius=max(.05,2*med)
        savez(p,xyz=P,normal=N,wall=wall,cameras=centres,radius=np.asarray(radius))
        dump(root/'receipt.json',dict(at=now(),site=site,points=len(P),parts=parts,radius_m=radius,median_spacing_m=med,
            normal_source=str(normalfile),normal_source_sha256=sha(normalfile),view_source=str(vpath),view_sha256=sha(vpath),
            population='inherited use and building-surface cells; B0 additionally primary use points inside cells',
            reference_triangulated=False,scientific_verdict=None))
        print('REFERENCE_READY',site,len(P),radius,flush=True)
    return loadz(p)

def rows(site,prior,ref):
    stem=f'{site}__{prior}';root=O/'scenes'/stem;root.mkdir(parents=True,exist_ok=True)
    path=root/'rows.npz'
    if path.exists():return loadz(path)
    d=loadz(RL/'stage0'/stem/'cells.npz')
    rr=loadz(S1/'defs'/site/f'rows_{prior}.npz',['kind','thin']);kind=rr['kind'][rr['thin'].astype(bool)]
    normal_points=loadz(O/'reference'/site/'normal_points.npz')
    dist,idx=cKDTree(normal_points['xyz']).query(d['xyz'],workers=4)
    wall=(kind==2) if prior=='LoD2' else np.zeros(len(kind),bool)
    normal=orient(d['xyz'],normal_points['normal'][idx],wall,ref['cameras'])
    d.update(normal=normal,wall=wall,row_kind=kind,normal_join_distance_m=dist)
    savez(path,**d)
    dump(root/'normal_join.json',dict(at=now(),exact_coordinate_rows=int((dist==0).sum()),nearest_rows=int((dist>0).sum()),
        maximum_nearest_distance_m=float(dist.max()),rows=len(dist),ALS_all_nonwall=prior=='ALS',scientific_verdict=None))
    return d

def sample_normals(V,F,grid,saved=None):
    # Same seeded triangle selection and barycentric draws as cloud.sample_mesh.
    keep=np.zeros(len(F),bool)
    area=np.empty(len(F),float)
    for start in range(0,len(F),500000):
        tri=V[F[start:start+500000]];a=.5*np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)
        area[start:start+len(a)]=a;keep[start:start+len(a)]=grid.in_cells(tri.mean(1))|(a>.01)
    faces=F[keep];A=area[keep];n=int(round(A.sum()*400));rng=np.random.default_rng(0)
    cs=np.cumsum(A);ids=np.minimum(np.searchsorted(cs,rng.random(n)*cs[-1],side='right'),len(faces)-1)
    r1=np.sqrt(rng.random(n))[:,None];r2=rng.random(n)[:,None];f=faces[ids]
    P=(1-r1)*V[f[:,0]]+r1*(1-r2)*V[f[:,1]]+r1*r2*V[f[:,2]]
    inside=grid.in_cells(P);P=P[inside];f=f[inside]
    normals=np.cross(V[f[:,1]]-V[f[:,0]],V[f[:,2]]-V[f[:,0]])
    normals/=np.linalg.norm(normals,axis=1)[:,None]
    if saved is not None:assert np.array_equal(P.astype('f4'),saved),'Inherited sample mismatch'
    return P,normals
