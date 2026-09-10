"""Run the main-revision technical CPU suite and bind its evidence."""
import contextlib
import json
import os
from pathlib import Path
import platform
import time
import unittest

from common import require_docker, record, write_new


def main():
    require_docker()
    root = Path('/workspace')
    output = Path('/validation')
    started = time.time()
    paths = sorted((root/'tests/phd/local_complementary_refinement_v1').glob('test_*_v2.py'))
    names = {p.name for p in paths}
    if not {'test_local_depth_loss_v2.py', 'test_evaluation_v2.py', 'test_runtime_v2.py'} <= names:
        raise ValueError('Incomplete main CPU validation suite')
    suite = unittest.defaultTestLoader.discover(str(paths[0].parent), pattern='test_*_v2.py')
    with (output/'cpu_tests.log').open('x') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    status = 'PASS' if result.wasSuccessful() and not result.skipped else 'FAIL'
    import numpy, torch
    receipt = dict(schema='JBGS_LOCAL_CPU_VALIDATION_v2', status=status, scientific_verdict=None,
        tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
        wall_seconds=time.time()-started, config=record('/config.json'), tests=[record(p) for p in paths],
        helpers=[record(p) for p in sorted((root/'scripts/phd/local_complementary_refinement_v1').glob('*_v2.*'))],
        log=record(output/'cpu_tests.log'), versions=dict(python=platform.python_version(),numpy=numpy.__version__,torch=torch.__version__),
        runtime_image_id=os.environ['JBGS_RUNTIME_IMAGE_ID'], repository_commit=os.environ['JBGS_REPOSITORY_COMMIT'],
        reference_accessed=False)
    write_new(output/'cpu_validation.json', receipt)
    print(json.dumps(dict(status=status, tests_run=result.testsRun, failures=len(result.failures),errors=len(result.errors),skips=len(result.skipped))),flush=True)
    raise SystemExit(0 if status=='PASS' else 1)


if __name__ == '__main__':
    main()
