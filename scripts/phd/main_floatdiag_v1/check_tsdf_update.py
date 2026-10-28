"""Same Open3D runtime: per-frame touched blocks versus globally allocated blocks."""
import json
import numpy as np
import open3d as o3d
from common import *

assert o3d.__version__=='0.19.0'
I=o3d.pipelines.integration
intr=o3d.camera.PinholeCameraIntrinsic(64,64,100.,100.,31.5,31.5)
def frame(depth):
    d=np.full((64,64),depth,np.float32)
    return o3d.geometry.RGBDImage.create_from_color_and_depth(
        o3d.geometry.Image(np.full((64,64,3),128,np.uint8)),o3d.geometry.Image(d),
        depth_scale=1.,depth_trunc=300.,convert_rgb_to_intensity=False)
def scalable():return I.ScalableTSDFVolume(.05,.25,I.TSDFVolumeColorType.RGB8,16,4)
def voxels(v,lo=0.,hi=10.):
    p=v.extract_voxel_point_cloud();x=np.asarray(p.points);c=np.asarray(p.colors)
    m=(x[:,2]>=lo)&(x[:,2]<hi);a=np.column_stack([x[m],c[m]])
    return a[np.lexsort((a[:,2],a[:,1],a[:,0]))]
def integrate(v,d):v.integrate(frame(d),intr,np.eye(4))

v=scalable();integrate(v,2.);before=voxels(v,0.,3.);integrate(v,4.);after=voxels(v,0.,3.)
assert len(before)>0 and np.array_equal(before,after)
far=voxels(v,3.,5.);assert len(far)>0
v2=scalable();integrate(v2,2.);a=voxels(v2);integrate(v2,2.1);b=voxels(v2)
assert not np.array_equal(a,b)
v3=scalable();integrate(v3,4.);first_far=voxels(v3);integrate(v3,2.)
assert np.array_equal(first_far,voxels(v3,3.,5.))
v4=scalable();integrate(v4,2.);a0=voxels(v4);integrate(v4,0.)
assert np.array_equal(a0,voxels(v4))
# Dense control proves the farther depth would update already allocated free
# space if that block were actually submitted to the per-block integrator.
u=I.UniformTSDFVolume(.8,16,.25,I.TSDFVolumeColorType.RGB8,np.array([-.4,-.4,1.6]))
integrate(u,2.);ua=np.asarray(u.extract_volume_tsdf()).copy();integrate(u,4.);ub=np.asarray(u.extract_volume_tsdf()).copy()
valid=ua[:,1]>0
assert valid.any() and np.all(ub[valid,1]==ua[valid,1]+1)
assert np.any(ua[valid,0]!=ub[valid,0])
folder=OUT/'provenance/tsdf_update';folder.mkdir(parents=True,exist_ok=False)
np.savez_compressed(folder/'observations.npz',scalable_near_before=before,scalable_near_after_far=after,
    scalable_far=far,dense_before=ua,dense_after=ub)
source=OUT/'provenance/open3d_source';bind=json.loads((source/'binding.json').read_text())
for r in bind:assert sha(source/r['file'])==r['sha256']
code=[Path('/repo/scripts/phd/main_losstrain_v1/tiled_post.py'),Path('/repo/src/phd/streamed_tsdf.py')]
r=dict(at=now(),status='PASS',runtime_version=o3d.__version__,settings=dict(voxel_m=.05,trunc_m=.25,depth_trunc_m=300.,unit_resolution=16,stride=4),
    tests=[dict(test='near 2m then far 4m, scalable',near_voxel_samples=len(before),near_TSDF_samples_exactly_unchanged=True,far_voxel_samples=len(far)),
           dict(test='near 2m then 2.1m, overlapping touched blocks',changed=True),
           dict(test='far 4m then near 2m',far_TSDF_samples_exactly_unchanged=True),
           dict(test='zero depth frame',unchanged=True),
           dict(test='dense allocated-block control 2m then 4m',existing_weight_samples=int(valid.sum()),every_weight_incremented_by_one=True,TSDF_changed=True)],
    conclusion='ScalableTSDFVolume updates only blocks touched by the current frame sampled depth points +/- truncation cube. It does not traverse all previously allocated blocks. A previously allocated but currently untouched block receives no update. Within a touched block, projected voxels in front can receive +1 TSDF; sdf<=-trunc receives no update.',
    observation_limit='Scalable public API exposes near-zero TSDF samples through voxel point-cloud colors, not all raw weights. Dense control exposes full TSDF and weight arrays; source confirms touched-block traversal.',
    source_urls=bind,project_code=[dict(file=str(p),sha256=sha(p)) for p in code],
    tiling='Project tiled wrapper changes per-tile depth via bounded proxies; original validation proves full source mesh equivalence. It does not replace ScalableTSDFVolume with globally traversed dense integration.',
    arrays=str(folder/'observations.npz'),arrays_sha256=sha(folder/'observations.npz'),optimizer_steps=0,scientific_verdict=None)
save(DOC/'provenance/tsdf_update_behavior.json',r)
print(json.dumps(r,ensure_ascii=False),flush=True)
