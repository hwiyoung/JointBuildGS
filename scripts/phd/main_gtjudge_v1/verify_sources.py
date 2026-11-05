"""Verify inherited hashes under the original container mount/symlink namespace."""
from common import *
cfg()
path=D/'provenance/inspected_source_lock.json'
lock=json.loads(path.read_text())
changed=[p for p,h in lock['files'].items() if sha(p)!=h]
dump(D/'provenance/source_recheck.json',dict(at=now(),lock_sha256=sha(path),
    files=len(lock['files']),changed=changed,status='FAIL' if changed else 'PASS',
    namespace='Docker: /out, /art, /repo; original absolute symlinks preserved',scientific_verdict=None))
assert not changed,changed
print('SOURCE_HASH_PASS',len(lock['files']))
