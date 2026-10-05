import hashlib,importlib.util,json,shutil
from pathlib import Path
import numpy as np
from plyfile import PlyData
A=Path('/artifacts/JointBuildGS');T=Path('/task');old=A/'phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1';src=T/'sources/GeoGS'
spec=importlib.util.spec_from_file_location('colmap_loader',src/'scene/colmap_loader.py');col=importlib.util.module_from_spec(spec);spec.loader.exec_module(col)
example=old/'native_example/scene';ex=col.read_extrinsics_binary(str(example/'sparse/0/images.bin'));common=col.read_extrinsics_binary(str(A/'phase-payloads/p0-audit/data/work/mvs/colmap_dense/sparse/images.bin'));by={i.name:i for i in common.values()}
a=[];b=[];ups=[]
for i in ex.values():
 j=by[i.name];a.append(-i.qvec2rotmat().T@i.tvec);b.append(-j.qvec2rotmat().T@j.tvec);ups.append(i.qvec2rotmat().T@j.qvec2rotmat()@np.array([0,0,1]))
a=np.array(a);b=np.array(b);ups=np.array(ups);delta=a-b
reference=json.loads((A/'phase-payloads/p0-audit/data/work/opf/opf/scene_reference_frame.json').read_text())
assert reference['base_to_canonical']['swap_xy'] is False
assert np.allclose(reference['base_to_canonical']['scale'],[1,1,1])
assert np.max(np.linalg.norm(delta-np.array([-2,29,0]),axis=1))<.03
assert np.min(ups[:,2])>.99999
frame={'base_to_canonical':{'scale':[1,1,1],'shift':[-690955,-5336042,-604],'swap_xy':False},'provenance':'Recovered from OPF frame, 15 corresponding cameras, rounded translation [-2,29,0]; not supplied author JSON','source_crs':'EPSG:25832 CityGML; OPF reference names EPSG:32632; horizontal datum bridge not independently calibrated','additional_z_offset_m':45.66}
(T/'provenance/reference_frame.json').write_text(json.dumps(frame,indent=2))
axis={'status':'PASS_UP_AXIS','up':[0,0,1],'matched_cameras':len(a),'camera_delta_mean':delta.mean(0).tolist(),'camera_delta_std':delta.std(0).tolist(),'max_translation_residual_m':float(np.max(np.linalg.norm(delta-[-2,29,0],axis=1))),'max_up_tilt_deg':float(np.max(np.degrees(np.arccos(np.clip(ups[:,2],-1,1))))),'scientific_verdict':None}
(T/'provenance/axis_validation.json').write_text(json.dumps(axis,indent=2))
z=np.load(T/'provenance/mesh_recovery_candidate.npz');v=z['vertices_global'];f=z['faces'];labels=z['labels'];ids=z['building_ids'];shift=z['shift'];mask=ids=='DEBY_LOD2_4959323';assert mask.any()
np.savez(T/'provenance/original_mesh.npz',vertices=v+shift,faces=f,labels=labels,building_ids=ids,target_face_mask=mask)
cams=col.read_intrinsics_binary(str(example/'sparse/0/cameras.bin'))
conditions={'B+0.25':.25,'B+0.5':.5,'B+1.0':1.,'B-1.0':-1.}
records=[]
for name,dz in conditions.items():
 root=T/'conditions'/name;scene=root/'scene';scene.mkdir(parents=True,exist_ok=True)
 for key in ['images','da3_prior','sparse']:
  p=scene/key
  if not p.exists():p.symlink_to(example/key,target_is_directory=True)
 sparse=scene/'sparse_lod/0';sparse.mkdir(parents=True,exist_ok=True)
 txt=scene/'sparse_txt';txt.mkdir(exist_ok=True)
 with (txt/'cameras.txt').open('w') as o:
  for cam in cams.values():o.write(f'{cam.id} {cam.model} {cam.width} {cam.height} '+ ' '.join(map(str,cam.params))+'\n')
 with (txt/'images.txt').open('w') as o:
  for i in ex.values():o.write(f'{i.id} '+' '.join(map(str,i.qvec))+' '+' '.join(map(str,i.tvec))+f' {i.camera_id} {i.name}\n\n')
 shutil.copyfile(txt/'cameras.txt',sparse/'cameras.txt')
 # Preserve exact provided poses for training; generated synthetic tracks are not used for poses.
 for key in ['images.bin','cameras.bin']:shutil.copyfile(example/'sparse/0'/key,sparse/key)
 biased=v.copy();biased[:,2]+=dz
 with (scene/'lod2_biased.obj').open('w') as o:
  for vv in biased:o.write('v '+' '.join(f'{x:.9f}' for x in vv)+'\n')
  for ff in f:o.write('f '+' '.join(str(int(x)+1) for x in ff)+'\n')
 p=PlyData.read(str(example/'lod2_pcd.ply'));p['vertex']['z']+=dz;p.write(str(scene/'lod2_pcd.ply'))
 records.append({'condition':name,'delta_z_m':dz,'before_global':v[0].tolist(),'after_global':biased[0].tolist(),'before_local':(v[0]+shift).tolist(),'after_local':(biased[0]+shift).tolist(),'axis_verified_before_shift':True})
(T/'provenance/vertex_shift_log.json').write_text(json.dumps(records,indent=2))
# Hash all supplied files against the historical acquired archive manifest.
manifest=json.loads((old/'native_example/input_manifest.json').read_text());checked=[]
for row in manifest['files']:
 p=old/'native_example'/row['path'];h=hashlib.file_digest(p.open('rb'),'sha256').hexdigest() if hasattr(hashlib,'file_digest') else hashlib.sha256(p.read_bytes()).hexdigest();assert h==row['sha256'],p;checked.append(row)
(T/'provenance/supplied_input_hashes.json').write_text(json.dumps(checked,indent=2))
print(json.dumps(axis));print('prepared shifted meshes, protected clouds, preserved DA3 and poses',len(conditions))
