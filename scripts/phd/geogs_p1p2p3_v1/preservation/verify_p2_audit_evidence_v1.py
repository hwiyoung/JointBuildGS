"""Verify only closed files declared by the additive P2 audit receipt v2."""
import hashlib
import json
from pathlib import Path
import platform
import sys
from datetime import datetime, timezone


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    assert Path('/.dockerenv').exists() and not Path('/reference').exists()
    root, sources, output = Path('/audit'), Path('/sources'), Path('/verification')
    receipt_path = root/'audit_receipt_v2.json'
    value = json.loads(receipt_path.read_text())
    assert value['bookkeeping_revision']=='CLOSED_EVIDENCE_FILES_v2'
    assert value['status']=='PASS_P2_RESOURCE_BINDINGS_AND_CURRENT_SERVICE_IDENTITIES'
    assert value['scientific_verdict'] is None
    items = value['sources']+value['evidence_files']
    assert len({row['path'] for row in items}) == len(items)
    rows = []
    for item in items:
        original = Path(item['path'])
        assert '..' not in original.parts
        if original.is_relative_to('/out'):
            path = root/original.relative_to('/out')
        elif original.is_relative_to('/code'):
            path = sources/original.relative_to('/code')
        else:
            raise ValueError('Unexpected audit evidence path')
        actual = dict(path=item['path'], bytes=path.stat().st_size, sha256=sha(path))
        rows.append(dict(expected=item, actual=actual, passed=actual==item))
    result = dict(status='PASS_ALL_DECLARED_CLOSED_HASHES' if all(row['passed'] for row in rows) else 'FAIL',
        scientific_verdict=None, checked_at_utc=datetime.now(timezone.utc).isoformat(),
        audit_receipt_sha256=sha(receipt_path), declared_files=len(rows), matching_files=sum(row['passed'] for row in rows),
        checks=rows, verifier_sha256=sha(__file__), command_sha256=sha(output/'command.sh'),
        runtime_image_id=(root/'image_id.txt').read_text().strip(), python_version=platform.python_version(),
        command_argv=sys.argv, reference_accessed=False, model_payload_accessed=False,
        limitation='Only hashes of closed files declared by audit_receipt_v2; intentionally excluded finalizer streams are retained but not asserted by that receipt.')
    with (output/'receipt.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({key:result[key] for key in ('status', 'declared_files', 'matching_files', 'scientific_verdict')}))
    raise SystemExit(0 if result['status'].startswith('PASS') else 1)


if __name__ == '__main__':
    main()
