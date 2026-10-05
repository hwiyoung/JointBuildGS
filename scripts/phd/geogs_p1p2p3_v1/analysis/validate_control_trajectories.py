"""Docker-only synthetic checks; no task/reference trace payload is mounted."""
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
    root = Path('/repo')
    start = time.monotonic()
    suite = unittest.defaultTestLoader.discover(str(root/'tests/phd/geogs_p1p2p3_v1'), pattern='test_control_trajectories.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    syntax = []
    for name in ('run_control_trajectories.sh', 'run_control_synthetic_validation.sh'):
        checked = subprocess.run(['bash', '-n', str(root/'scripts/phd/geogs_p1p2p3_v1/analysis'/name)],
                                 capture_output=True, text=True, check=False)
        syntax.append(dict(path=name, exit_code=checked.returncode, stderr=checked.stderr))
    status = 'PASS' if result.wasSuccessful() and all(row['exit_code']==0 for row in syntax) else 'FAIL'
    value = dict(schema='GEOGS_SYNTHETIC_CONTROL_TRAJECTORY_VALIDATION_v1', status=status, scientific_verdict=None,
        completed_at_utc=datetime.now(timezone.utc).isoformat(), wall_seconds=time.monotonic()-start,
        tests_run=result.testsRun, passed=result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped),
        errors=len(result.errors), failures=len(result.failures), skipped=len(result.skipped), shell_syntax=syntax,
        source_files=[dict(path=str(path.relative_to(root)), bytes=path.stat().st_size,
                           sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in sorted(root.rglob('*')) if path.is_file()],
        runtime_image_id=os.environ['EXECUTION_IMAGE_ID'], python_version=platform.python_version(), command_argv=sys.argv,
        actual_trace_mounted=False, actual_trace_accessed=False, reference_mounted=False, actual_quality_examined=False,
        synthetic_figures=[dict(path=path.name, bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                           for path in sorted(Path('/out').glob('synthetic_*.png'))])
    with Path('/out/test_receipt.json').open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
    print(json.dumps({key:value[key] for key in ('status', 'tests_run', 'passed', 'errors', 'failures', 'skipped', 'scientific_verdict')}))
    raise SystemExit(0 if status=='PASS' else 1)


if __name__ == '__main__':
    main()
