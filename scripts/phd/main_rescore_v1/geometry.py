"""Inherited reference cleanup/sampling, plus the requested column ownership."""
import ast,sys,subprocess
from common import *
from scipy.spatial import cKDTree
sys.path.insert(0,'/repo')
from src.phd.metrics_v3.surface import MeshScene
def inherit(path,names,scope):
 p=R/path;tree=ast.parse(p.read_text());nodes=[x for x in tree.body if isinstance(x,(ast.FunctionDef,ast.ClassDef)) and x.name in names];assert {x.name for x in nodes}==set(names)
 exec(compile(ast.Module(body=nodes,type_ignores=[]),str(p),'exec'),scope)
 return {name:scope[name] for name in names}
env=dict(np=np,S1=S1,OFFSET=np.array([690953.,5336071.]),cKDTree=cKDTree,WORK=PH/'main_axes71_v2/PHD-MAIN-AXES71-v2/work')
globals().update(inherit('scripts/phd/main_dist71_v1/dm_common.py',['SiteGT','result_sample','owner_of_scene_points','closest'],env))
globals().update(inherit('scripts/phd/main_axes71_v2/a2x_sample.py',['Ref','normals_full'],env))
globals().update(inherit('scripts/phd/main_judgeapply_v1/inherited/photo_planes.py',['tangent'],dict(np=np)))
def patch_basis(core):
 a=core['tangent1'].astype(float).copy();b=core['tangent2'].astype(float).copy();n=core['normal'].astype(float)
 # JA refits ALS normals. Its photo plane uses tangent(n), not the old mesh tangents.
 if str(core['prior'][0])=='ALS':
  for i in np.flatnonzero(np.isfinite(n).all(1)):a[i],b[i]=tangent(n[i])
 return a,b,n
def columns(points,core,folder):
 folder.mkdir(parents=True,exist_ok=True);a,b,n=patch_basis(core);c=core['centre']+core['prior_height_m'][:,None]*n;length=np.where(core['kind']==1,10.,5.)
 basis=np.stack([a,b,n],axis=2);good=np.isfinite(basis).all((1,2))&np.isfinite(c).all(1)
 inverse=np.full_like(basis,np.nan);good[good]&=np.abs(np.linalg.det(basis[good]))>1e-10;inverse[good]=np.linalg.inv(basis[good])
 extent=.125*(abs(a)+abs(b))+length[:,None]*abs(n)
 records=np.c_[c,inverse.reshape(-1,9),np.where(good,length,0),c-extent,c+extent].astype('<f8');points.astype('<f8').tofile(folder/'points.bin');records.tofile(folder/'columns.bin')
 exe=O/'bin/prism';exe.parent.mkdir(exist_ok=True)
 source=Path(__file__).with_name('prism.cpp');stamp=exe.with_suffix('.sha256')
 if not exe.exists() or not stamp.exists() or stamp.read_text()!=sha(source):
  subprocess.run(['g++','-O3','-std=c++17',str(source),'-o',str(exe)],check=True);stamp.write_text(sha(source))
 subprocess.run([str(exe),str(folder/'points.bin'),str(folder/'columns.bin'),str(folder/'owner.bin'),str(folder/'hits.bin')],check=True)
 return np.fromfile(folder/'owner.bin',dtype='<i4'),np.fromfile(folder/'hits.bin',dtype='<i4')
def context(site,prior):
 gt=SiteGT(site);normals=normals_full(site,gt);ref=Ref(gt.Gb,normals[0][gt.bs_idx]);core=loadz(JA/'core_points'/f'{site}__{prior}.npz');v2=loadz(CELLS/f'{site}__{prior}.npz');assert np.array_equal(core['patch_id'],v2['patch_id'])
 r=loadz(S1/'defs'/site/f'rows_{prior}.npz');thin=r['thin'].astype(bool);pa=r['patch'][thin].astype(int);source=r['src'][thin];pt=r['point'][thin].astype(int);P=np.zeros((len(pa),3))
 for s,X in gt.X.items():P[source==s]=X[pt[source==s]]
 count=len(loadz(TG/'stage0_r1/inputs'/f'{site}_{prior}.npz',['area'])['area']);lookup=np.full(count,-1,np.int32);lookup[core['source_index']]=np.arange(len(core['area']))
 scene_owner=owner_of_scene_points(site,prior,gt);mapped=np.full(len(scene_owner),-1,np.int32);has=scene_owner>=0;mapped[has]=lookup[scene_owner[has]]
 refB=ref
 if site=='B0_b10':
  keep=gt.G['use_gt_primary'].astype(bool);P1=gt.X[1][keep];N1=normals[1][keep];k=gt.in_cells(P1);refB=Ref(np.vstack([gt.Gb,P1[k]]),np.vstack([normals[0][gt.bs_idx],N1[k]]))
 rownorm=np.full_like(P,np.nan)
 for s in gt.X:rownorm[source==s]=normals[s][pt[source==s]]
 return dict(gt=gt,ref=ref,region_ref=refB,normals=normals,core=core,v2=v2,rows=r,row_points=P,row_owner=lookup[pa],row_normals=rownorm,row_kind=r['kind'][thin],scene_owner=mapped)
