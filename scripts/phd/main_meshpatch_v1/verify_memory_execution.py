"""Verify captured original components against independent Open3D results."""
import copy
import numpy as np
import open3d as o3d
from mesh_common import D, dump, mesh_config, now
from mesh_worker import original_cleanup
from mesh_staged import captured_cleanup

cfg=mesh_config();checks=[]
for with_degenerate in [False,True]:
    mesh=o3d.geometry.TriangleMesh()
    for i in range(55):
        mesh+=o3d.geometry.TriangleMesh.create_sphere(radius=1,resolution=5+(i%3)).translate((i*4,0,0))
    small=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector([[300.,0,0],[301.,0,0],[300.,1,0]]),o3d.utility.Vector3iVector([[0,1,2]]))
    mesh+=small
    if with_degenerate:
        faces=np.asarray(mesh.triangles).copy()
        mesh.triangles=o3d.utility.Vector3iVector(np.vstack([faces,[faces[0,0],faces[0,0],faces[0,1]]]))
    source=copy.deepcopy(mesh)
    expected=original_cleanup(cfg)(mesh,cluster_to_keep=50)
    actual,capture=captured_cleanup(mesh,cfg)
    assert np.array_equal(np.asarray(mesh.vertices),np.asarray(source.vertices))
    assert np.array_equal(np.asarray(mesh.triangles),np.asarray(source.triangles))
    for field in ['vertices','triangles','vertex_colors','vertex_normals']:
        assert np.array_equal(np.asarray(getattr(actual,field)),np.asarray(getattr(expected,field)))
    labels,counts,areas=mesh.cluster_connected_triangles()
    assert np.array_equal(capture['triangle_clusters'],np.asarray(labels))
    assert np.array_equal(capture['cluster_n_triangles'],np.asarray(counts))
    assert np.array_equal(capture['cluster_area'],np.asarray(areas))
    threshold=max(int(np.sort(np.asarray(counts))[-50]),50)
    f=np.asarray(mesh.triangles);deg=(f[:,0]==f[:,1])|(f[:,0]==f[:,2])|(f[:,1]==f[:,2])
    removed=(np.asarray(counts)[np.asarray(labels)]<threshold)|deg
    assert (~removed).sum()==len(actual.triangles)
    if not with_degenerate:
        _,after_counts,_=actual.cluster_connected_triangles()
        assert sorted(after_counts)==sorted(np.asarray(counts)[np.asarray(counts)>=threshold])
    checks.append(dict(degenerate=with_degenerate,triangles=len(f),after=len(actual.triangles),status='PASS'))
dump(D/'tables/memory_execution_validation.json',dict(status='PASS',checks=checks,
    original_function_sha256=cfg['source_function']['sha256'],original_function_unmodified=True,
    open3d_version=o3d.__version__,numpy_version=np.__version__,finished_at=now(),scientific_verdict=None))
print('PASS: original function output, captured component arrays, source unchanged, tie and degenerate accounting')
