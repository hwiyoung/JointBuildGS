"""Run a UAS-free analytic correctness audit and freeze its evidence receipt."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import time
import unittest


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(output):
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker execution required')
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    modules = [
        'tests.phd.test_wu_vallet_matched_v5_core',
        'tests.phd.test_wu_vallet_ray_runtime_v2',
        'tests.phd.test_wu_vallet_filter_v3',
        'tests.phd.test_wu_vallet_ray_update',
        'tests.phd.test_wu_vallet_sensor_mesh',
    ]
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    from src.phd.wu_vallet_matched_v5 import core
    import inspect
    files = list(dict.fromkeys([
        Path(__file__), Path(__file__).with_name('update_regions.py'),
        Path(inspect.getfile(core)),
        Path(inspect.getfile(core._classify_v2)),
        Path(inspect.getfile(core._assemble_v3)),
        *[Path(*name.split('.')).with_suffix('.py') for name in modules],
        Path('src/phd/wu_vallet_p3_v1/ray_update.py'),
        Path('src/phd/wu_vallet_p3_v1/sensor_mesh.py'),
        Path('scripts/phd/wu_vallet_p3_v2/update_points.py'),
        Path('scripts/phd/wu_vallet_regions_v4/prepare_inputs.py'),
    ]))
    hashes = {str(p): sha(p) for p in files}
    with (output / 'tests.log').open('x') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    unchanged = all(sha(p) == expected for p, expected in hashes.items())
    receipt = dict(
        status='PASS' if result.wasSuccessful() and unchanged else 'FAIL',
        scientific_verdict=None, reference_accessed=False, synthetic_inputs_only=True,
        tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        test_modules=modules, input_hashes=hashes, source_unchanged=unchanged,
        runtime=dict(python=platform.python_version(),
                     **{name: importlib.metadata.version(name) for name in ('numpy', 'scipy', 'open3d')}),
        container_image=os.environ.get('JBGS_CONTAINER_IMAGE_ID'),
        source_git_head=os.environ.get('JBGS_SOURCE_GIT_HEAD'),
        elapsed_seconds=time.monotonic() - started,
        audit_findings=dict(
            historical_v2_filtered_new_reentry='confirmed present in historical v2 assembler; preserved as historical evidence',
            latest_v3_v4_reentry='already corrected before v5; new tests independently verify no filtered-only readmission',
            v5_algorithm_change='none: unchanged raw sampled relations and v3 point policy, added validation and raw-only API',
            mixed_face_point_aggregation='declared policy consistent > accepted_changed > raw_single > filtered > unassessed; not identified as a bug',
            synthetic_coherent_wrong_depth='indistinguishable from real change under the available geometry and sensor-ray evidence; test demonstrates this limit, not author-code equivalence',
            visibility='own foreground blocks background free-space ray; raw SINGLE remains uncertified and retained by declared baseline policy',
            origin_policy='unsupported origins on old triangles fail; isolated unavailable origins preserved without invented rays',
            context_policy='changed-component area measured on context before final region crop',
            unresolved_author_differences=['PSMNet multi-view forward intersection replaced by COLMAP depth',
                'estimated instead of measured ALS optical origins',
                'sampled rays instead of exact author triangle-volume intersection',
                'area threshold/connectivity/vertex aggregation not published in sufficient detail']),
        outputs={'tests.log': sha(output / 'tests.log')})
    with (output / 'receipt.json').open('x') as stream:
        json.dump(receipt, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(json.dumps({key: receipt[key] for key in ('status', 'tests_run', 'failures', 'errors', 'source_unchanged')}), flush=True)
    return 0 if receipt['status'] == 'PASS' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(run(parser.parse_args().output))
