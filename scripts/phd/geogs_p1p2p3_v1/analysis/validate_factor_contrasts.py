"""Run only synthetic contrast tests in an isolated source snapshot."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import unittest


def main():
    if not Path('/.dockerenv').exists() or Path('/task').exists() or Path('/reference').exists():
        raise RuntimeError('Synthetic validation requires Docker without task/reference mounts')
    source = Path('/repo')
    start = time.monotonic()
    suite = unittest.defaultTestLoader.discover(str(source/'tests/phd/geogs_p1p2p3_v1'), pattern='test_factor_contrasts.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    syntax = subprocess.run(['bash', '-n', str(source/'scripts/phd/geogs_p1p2p3_v1/analysis/run_factor_contrasts.sh')],
                            check=False, capture_output=True, text=True)
    records = [dict(path=str(path.relative_to(source)), bytes=path.stat().st_size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest())
               for path in sorted(source.rglob('*')) if path.is_file()]
    passed = result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped)
    receipt = dict(schema='GEOGS_SYNTHETIC_FACTOR_CONTRAST_VALIDATION_v1',
        status='PASS' if result.wasSuccessful() and syntax.returncode == 0 else 'FAIL', scientific_verdict=None,
        completed_at_utc=datetime.now(timezone.utc).isoformat(), wall_seconds=time.monotonic()-start,
        tests_run=result.testsRun, passed=passed, failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
        shell_syntax=dict(exit_code=syntax.returncode, stderr=syntax.stderr), source_files=records,
        runtime_image_id=os.environ['EXECUTION_IMAGE_ID'], python_version=platform.python_version(),
        command_argv=sys.argv, actual_regional_execution=False, task_payload_mounted=False,
        reference_payload_mounted=False, actual_metrics_examined=False)
    with Path('/out/test_receipt.json').open('x') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
    print(json.dumps({key:receipt[key] for key in ('status', 'tests_run', 'passed', 'failures', 'errors', 'skipped', 'scientific_verdict')}))
    raise SystemExit(0 if receipt['status']=='PASS' else 1)


if __name__ == '__main__':
    main()
