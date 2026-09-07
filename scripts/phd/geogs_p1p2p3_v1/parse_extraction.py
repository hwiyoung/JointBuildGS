"""Verify realized bounded-TSDF parameters in unmodified official GeoGS logs.

This helper has no scientific dependencies and performs no reconstruction. The
official log prints Python float representations, so its default arithmetic can
be checked exactly after round-trip parsing. Rounded radius text is diagnostic.
"""
import hashlib
import math
from pathlib import Path
import re

PARSER_SOURCE = Path(__file__).read_bytes()
PARSER_SHA256 = hashlib.sha256(PARSER_SOURCE).hexdigest()
TSDF_MARKER = 'Running tsdf volume integration ...'


def parse_extraction_text(text, mesh_res, expected_num_cluster=50):
    if isinstance(mesh_res, bool) or not isinstance(mesh_res, int) or mesh_res <= 0:
        raise ValueError('A positive integer mesh_res is required')
    if (isinstance(expected_num_cluster, bool) or not isinstance(expected_num_cluster, int)
            or expected_num_cluster <= 0):
        raise ValueError('A positive integer cluster count is required')
    text = text.replace('\r', '\n')
    if text.count(TSDF_MARKER) != 1:
        raise ValueError('Expected exactly one official bounded TSDF integration block')
    marker_position = text.index(TSDF_MARKER)
    values = {}
    for printed, field in (('voxel_size', 'voxel_size_m'), ('sdf_trunc', 'sdf_trunc_m'),
                           ('depth_truc', 'depth_trunc_m')):
        matches = list(re.finditer(r'^\s*' + printed + r':\s*([^\s]+)[^\n]*$', text, re.MULTILINE))
        if len(matches) != 1 or matches[0].start() < marker_position:
            raise ValueError('Expected exactly one parameter after the TSDF marker: ' + printed)
        try:
            value = float(matches[0].group(1))
        except ValueError as error:
            raise ValueError('Invalid floating-point extraction parameter: ' + printed) from error
        if not math.isfinite(value) or value <= 0:
            raise ValueError('Expected a finite positive extraction parameter: ' + printed)
        values[field] = value
    postprocess = list(re.finditer(r'^post processing the mesh to have (\d+) clusterscluster_to_kep[^\n]*$',
                                  text, re.MULTILINE))
    if len(postprocess) != 1 or postprocess[0].start() < marker_position:
        raise ValueError('Expected exactly one official postprocess cluster declaration')
    clusters = int(postprocess[0].group(1))
    if clusters != expected_num_cluster:
        raise ValueError('Actual postprocess cluster parameter differs from the frozen configuration')
    if values['voxel_size_m'] != values['depth_trunc_m'] / mesh_res:
        raise ValueError('Actual voxel size differs from the frozen depth_trunc / mesh_res default')
    if values['sdf_trunc_m'] != 5.0 * values['voxel_size_m']:
        raise ValueError('Actual sdf_trunc differs from the frozen 5 * voxel_size default')
    radii = list(re.finditer(r'^The estimated bounding radius is ([^\s]+)[^\n]*$',
                            text[:marker_position], re.MULTILINE))
    rounded_radius = float(radii[-1].group(1)) if radii else None
    # Native radius text uses :.2f; this is its rounding interval, not a
    # tolerance for comparing extraction parameters across experimental arms.
    if rounded_radius is not None and (not math.isfinite(rounded_radius) or rounded_radius <= 0
            or abs(rounded_radius - values['depth_trunc_m'] / 2.0) > 0.005000001):
        raise ValueError('Depth truncation disagrees with the last printed train-camera radius')
    return dict(schema='GEOGS_BOUNDED_TSDF_LOG_PARAMETERS_v1', mesh_res=mesh_res,
                num_cluster=clusters, **values, tsdf_block_count=1,
                camera_radius_last_printed_m=rounded_radius,
                camera_radius_derived_from_depth_trunc_m=values['depth_trunc_m'] / 2.0,
                camera_radius_print_rounding_abs_tolerance_m=0.005000001,
                numeric_relationship_policy='EXACT_FLOAT_EQUALITY_FOR_ROUNDTRIP_LOGGED_VALUES',
                bounded_default_relationships_verified=True,
                frozen_render_controls={'depth_ratio': 0.0, 'mesh_active_sh_degree': 0,
                    'provenance': 'frozen official source defaults; these two controls are not printed TSDF log measurements'},
                parser_sha256=PARSER_SHA256, scientific_verdict=None)


def parse_extraction_log(path, mesh_res, expected_num_cluster=50):
    contents = Path(path).read_bytes()
    result = parse_extraction_text(contents.decode('utf-8', errors='strict'), mesh_res, expected_num_cluster)
    result['source_log_sha256'] = hashlib.sha256(contents).hexdigest()
    return result
