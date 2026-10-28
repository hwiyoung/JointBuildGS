"""Bounded functional checks before admitting full source meshes."""
from mesh_worker import *
cfg=json.loads((C/'mesh_targets_v1.json').read_text());func=original_cleanup(cfg)
m=o3d.geometry.TriangleMesh()
for i in range(52):m+=o3d.geometry.TriangleMesh.create_sphere(radius=1,resolution=5).translate((i*3,0,0))
small=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector([[200,0,0],[201,0,0],[200,1,0]]),o3d.utility.Vector3iVector([[0,1,2]]));m+=small
v0=np.asarray(m.vertices).copy();f0=np.asarray(m.triangles).copy();clean=func(m,cluster_to_keep=50)
assert np.array_equal(v0,np.asarray(m.vertices));assert np.array_equal(f0,np.asarray(m.triangles))
_,counts,_=clean.cluster_connected_triangles();assert len(counts)==52 and min(counts)==80 and len(clean.triangles)==4160
# A horizontal top surface at z=1 is hit first from +z; absence remains NaN.
top=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector([[-2,-2,1],[2,-2,1],[2,2,1],[-2,2,1]]),o3d.utility.Vector3iVector([[0,1,2],[0,2,3]]))
e=dict(centre=np.array([[0.,0,0],[5.,0,0]]),normal=np.tile([0.,0,1.],(2,1)),p_mvs=np.zeros(2),p_gt=np.zeros(2),tau=np.full(2,.2),in_eval=np.ones(2,bool),scoring_allowed=np.ones(2,bool),area=np.ones(2),cell=np.zeros(2,int))
v=dict(sigma_prior=np.full(2,.1),sigma_mvs=np.full(2,.1));z=first_hit(top,e,v)
assert abs(z['z'][0]-1)<1e-6 and np.isnan(z['z'][1]);assert np.array_equal(classes(e,z),[1,4])
sys.path.insert(0,'/repo/scripts/phd/main_stage1_v1');sys.path.insert(0,'/repo');import metrics_s1
metrics_s1.OUT=S1;I=metrics_s1.Inputs('B0_b10','ALS');assert len(I.pt)>0
receipt=dict(status='PASS',checks=['original function leaves source unchanged','threshold ties retain 52 components','minimum 50-triangle rule removes singleton','first-hit and no-surface classification','existing stage1 Inputs import'],original_function_sha256=cfg['source_function']['sha256'],open3d=o3d.__version__,numpy=np.__version__,at=now(),scientific_verdict=None)
dump(D/'tables/mesh_preflight.json',receipt);print(json.dumps(receipt))
