"""Validate the exact frozen numerical code, then dispatch mask computation."""
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

command=[sys.executable,'-m','unittest','discover','-s','tests/phd','-p','test_irregular_source_masks_v1.py','-v']
result=subprocess.run(command,capture_output=True,text=True)
Path('/out/numerical_validation.log').write_text(result.stdout+result.stderr)
Path('/out/numerical_validation.json').write_text(json.dumps(dict(
    status='PASS_NUMERICAL_TESTS' if result.returncode==0 else 'FAIL_NUMERICAL_TESTS',
    scientific_verdict=None,command=command,exit_code=result.returncode,
    created_utc=datetime.now(timezone.utc).isoformat(),
    git_base=os.environ.get('JBGS_GIT_COMMIT'),source_manifest='source_sha256.txt',
    interpretation='Synthetic numerical and implementation checks, not scene mask accuracy.'),indent=2)+'\n')
print(result.stdout+result.stderr,flush=True)
if result.returncode:sys.exit(result.returncode)
os.execv(sys.executable,[sys.executable,'/repo/scripts/phd/irregular_source_masks_v1/build.py',*sys.argv[1:]])
