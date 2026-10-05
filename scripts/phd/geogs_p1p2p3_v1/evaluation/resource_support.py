"""Explicit extraction resource amendment, without changing scientific inputs."""
from pathlib import Path
import sys


RESOURCE_SEAL_STATUS = 'ALL_REQUIRED_CANDIDATES_SEALED_OPTIONAL_ACCOUNTED'
UNAVAILABLE = 'TECHNICAL_RESOURCE_UNAVAILABLE'


def make_resource(task, path, layout, repeat):
    if path is None:
        if (Path(task)/'contracts/extraction_resource_v3.json').exists():
            raise ValueError('This task requires explicit --resource-contract before evaluation')
        return None
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from resource_contract import ResourceContract
    return ResourceContract(task, path, layout, repeat)


def binding(resource):
    return resource.binding() if resource else {}


def require(resource, receipt):
    if resource:
        if receipt.get('resource_contract_sha256') != resource.digest:
            raise ValueError('Extraction resource contract SHA differs from sealed evaluation')
    elif receipt.get('resource_contract_sha256'):
        raise ValueError('Resource-amended results require explicit --resource-contract')


def seal_status(resource, repeat=None):
    repeat = repeat if repeat is not None else getattr(resource, 'repeat', None)
    if getattr(repeat, 'completion', None):
        return 'PRIMARY18_CANDIDATES_SEALED_SUPPLEMENTAL_INCOMPLETE'
    return RESOURCE_SEAL_STATUS if resource and getattr(resource, 'data', True) else 'ALL_FIXED_CANDIDATES_SEALED'


def comparison_family(candidate):
    if candidate in ('als_points', 'mvs_points', 'prior_mesh'):
        return 'input_baseline'
    variant = candidate.split('.')[1]
    if variant == 'final':
        return 'primary_1024'
    if variant in ('anchor_512', 'mesh_512'):
        return 'anchor_refinement_512'
    return 'optional_extraction_diagnostic'


def inventory_availability(seal):
    """One row per planned variant, even when no surface exists to evaluate."""
    rows = []
    for entry in seal.get('extraction_inventory', []):
        unavailable = entry['status'] == UNAVAILABLE
        if entry['status'] not in ('PASS', UNAVAILABLE) or entry['required'] and unavailable:
            raise ValueError('Unresolved or unavailable required extraction in candidate seal')
        rows.append(dict(region=entry['region'], condition=entry['condition'],
            scientific_condition=entry['scientific_condition'], variant=entry['variant'],
            iteration=entry['iteration'], mesh_res=entry['mesh_res'], required=entry['required'],
            supplemental_only=entry['supplemental_only'], status=entry['status'],
            producer_directory=entry['producer_directory'], receipt_path=entry['receipt']['path'],
            receipt_sha256=entry['receipt']['sha256'],
            metric_status='NOT_ASSESSED_TECHNICAL_RESOURCE_UNAVAILABLE' if unavailable else 'SURFACE_AVAILABLE_FOR_SEPARATE_EVALUATION',
            precision=None, recall=None, f1=None, surface_distances=None,
            far_from_observed_reference_area_estimate_m2=None,
            is_reference_absence=False, is_reconstruction_failure=False,
            scientific_verdict=None))
    return rows


def optional_final_inventory_complete(seal, regions, conditions):
    """No conditional aggregate from only surviving high-resolution outputs."""
    expected = {(region, condition) for region in regions for condition in conditions}
    actual = [row for row in seal.get('extraction_inventory', []) if row['variant'] == 'mesh_2048']
    keys = [(row['region'], row['condition']) for row in actual]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError('Optional final resolution inventory is not the complete declared matrix')
    return all(row['status'] == 'PASS' for row in actual)
