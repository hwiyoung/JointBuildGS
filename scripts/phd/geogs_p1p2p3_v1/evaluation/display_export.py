"""Display-only, unsimplified copies of the mesh already clipped for evaluation."""
import hashlib
import json
from pathlib import Path

import numpy as np


def display_candidate_state(metrics, display_metadata):
    """Describe visibility without changing evaluation status, NA or F1 policy."""
    if metrics['status']=='RECONSTRUCTION_FAILURE':
        return 'reconstruction_failure',None
    evaluated_count=metrics.get('surface_samples',metrics.get('prediction_points',display_metadata.get('full_evaluation_sample_count')))
    display_count=display_metadata.get('display_sample_count',evaluated_count)
    if metrics['status']=='NOT_ASSESSED_REFERENCE_ABSENT' and evaluated_count==0 and display_count==0:
        return 'no_geometry_reference_absent','표시 기하 없음 · 참조 부재로 품질평가 불가'
    return 'available',None


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def binary_array(path, array, dtype):
    """Bound conversion workspace; retain all rows and their existing order."""
    digest = hashlib.sha256()
    with path.open('xb') as stream:
        for start in range(0,len(array),65536):
            block = np.ascontiguousarray(array[start:start+65536],dtype=dtype)
            view = memoryview(block).cast('B')
            stream.write(view)
            digest.update(view)
    return dict(sha256=digest.hexdigest(),bytes=path.stat().st_size)


def export_clipped_mesh(path, arrays, bounds, source, color, viewer_root, evaluation_metadata=None):
    """No clipping, geometry processing, simplification, sampling or scoring here."""
    path, viewer_root = Path(path), Path(viewer_root)
    vertices, triangles = np.asarray(arrays['clipped_vertices']),np.asarray(arrays['clipped_triangles'])
    if vertices.ndim!=2 or vertices.shape[1]!=3 or triangles.ndim!=2 or triangles.shape[1]!=3:
        raise ValueError('Exact clipped triangle arrays require Nx3/Mx3 shape')
    if not np.isfinite(vertices).all() or not np.issubdtype(triangles.dtype,np.integer):
        raise ValueError('Exact clipped display mesh requires finite vertices and integer topology')
    if len(vertices)>np.iinfo(np.uint32).max or (triangles.size and (triangles.min()<0 or triangles.max()>=len(vertices))):
        raise ValueError('Display topology cannot be represented by the declared uint32 indices')
    vertices_path = path.with_suffix('.vertices.f64')
    triangles_path = path.with_suffix('.triangles.u32')
    targets = (path,vertices_path,triangles_path)
    if any(target.exists() for target in targets):
        raise FileExistsError('Preserve existing display mesh outputs: '+str(path))
    vertex_record = binary_array(vertices_path,vertices,'<f8')
    triangle_record = binary_array(triangles_path,triangles,'<u4')
    vertex_record['url'] = str(vertices_path.relative_to(viewer_root))
    triangle_record['url'] = str(triangles_path.relative_to(viewer_root))
    metadata = dict(schema='geogs_exact_clipped_display_mesh_v1',display_only=True,scientific_verdict=None,
        representation='EXACT_EVALUATION_CLIPPED_TRIANGLES',vertices_f64=vertex_record,triangles_u32=triangle_record,
        vertex_count=len(vertices),triangle_count=len(triangles),source_mesh=source,bounds_half_open=bounds,
        topology_simplified=False,vertices_reordered=False,triangles_reordered=False,artificial_clip_caps=False,
        coordinate_storage='little-endian float64',topology_storage='little-endian uint32',gpu_coordinate_dtype='float32',
        coordinate_frame='Existing evaluator local XYZ in meters; no new origin shift, registration or transform.',
        evaluation_bvh_coordinate_dtype=(evaluation_metadata or {}).get('bvh_coordinate_dtype'),
        precision_note='Float64 file storage does not imply float64 distance computation; the existing reference-to-triangle BVH uses the separately declared evaluation dtype.',
        gpu_conversion='The browser converts coordinates to float32 only for WebGL display; binary export retains evaluated float64 values.',
        evaluation_reinput=False,scoring_source='Existing native/evaluated geometry; this display export is never read by scoring.',
        color={'kind':'FIXED_SOURCE_COLOR','rgb_u8':list(color),'description':'Display source color; not measured RGB or a saved official RGB render.'},
        distance_mode_requires_points=True,
        scope='Exact evaluator-clipped surface portions inside the fixed XYZ prism; no added clip boundary faces. Original linked PLY retains the full input/extraction context.')
    with path.open('x') as stream:
        json.dump(metadata,stream,indent=2,allow_nan=False)
    return dict(format='json',url=str(path.relative_to(viewer_root)),sha256=sha(path),bytes=path.stat().st_size)


def original_mesh_provenance(task, source_path, seal_files, source_role):
    """Resolve a direct mesh download only from the input/candidate seal catalogue."""
    relative = str(Path(source_path).relative_to(task))
    records = [row for row in seal_files if row['path']==relative]
    if len(records)!=1:
        raise ValueError('Original display mesh is absent/ambiguous in the candidate/input seal: '+relative)
    record = records[0]
    path = Path(source_path)
    if path.stat().st_size!=record['bytes'] or sha(path)!=record['sha256']:
        raise ValueError('Original mesh changed after candidate/input seal: '+relative)
    prior = source_role=='prior'
    return dict(record,source_kind='ALS_CONVERTED_INPUT_MESH' if prior else 'OFFICIAL_GEOGS_TSDF_MESH',
                scope='FULL_PRIOR_INPUT_CONTEXT' if prior else 'FULL_CAMERA_BOUNDED_TSDF_EXTRACTION',
                evaluation_crop_separate=True,
                scope_note='Original PLY before evaluator XYZ-prism clipping; its extent can exceed the displayed/evaluated region.')


def manifest_mesh_links(task, mesh_data, original_mesh, sealed_files):
    """Bind display binaries separately from the unchanged original mesh download."""
    task=Path(task)
    downloads,files=[],[]
    if original_mesh:
        original=sealed_files.get(original_mesh['path'])
        if not original or any(original[key]!=original_mesh[key] for key in ('sha256','bytes')):
            raise ValueError('Original display mesh link is not bound by the input/candidate seal')
        downloads.append(dict(label=('Original ALS input PLY — full prior context' if original_mesh['source_kind']=='ALS_CONVERTED_INPUT_MESH'
            else 'Original official raw/post PLY — full TSDF extraction'),url='../../'+original_mesh['path']))
    if mesh_data:
        def checked(item):
            relative=Path(item['url'])
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Display mesh URL must remain within viewer output')
            path=task/'evaluation/viewer'/relative
            record=dict(path=str(path.relative_to(task)),sha256=sha(path),bytes=path.stat().st_size)
            if record['sha256']!=item['sha256'] or record['bytes']!=item['bytes']:
                raise ValueError('Exact clipped display mesh differs from exporter')
            files.append(record)
            return path
        metadata=json.loads(checked(mesh_data).read_text())
        for field in ('vertices_f64','triangles_u32'):
            checked(metadata[field])
        downloads.append(dict(label='Exact evaluated crop mesh metadata — no simplification',url=mesh_data['url']))
    return downloads,files
