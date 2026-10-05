"""Read-only source preservation ledger; run in Docker with /repo:ro /out:rw."""
import hashlib
import json
import subprocess
from pathlib import Path

repo, out = Path('/repo'), Path('/out')
out.mkdir(parents=True, exist_ok=True)
def git(*args):
    return subprocess.check_output(['git', '-c', 'safe.directory=/repo', '-C', str(repo), *args])
files = set(git('ls-files', '-z').split(b'\0')) | set(git('ls-files', '--others', '--exclude-standard', '-z').split(b'\0'))
entries = []
for raw in sorted(files):
    if not raw:
        continue
    name = raw.decode()
    if 'geogs_p1p2p3_v1/' in name or name == 'Dockerfile.geogs-v1':
        continue
    p = repo / name
    if p.is_file():
        entries.append({'path': name, 'bytes': p.stat().st_size,
                        'sha256': hashlib.file_digest(p.open('rb'), 'sha256').hexdigest()})
manifest = {'head': git('rev-parse', 'HEAD').decode().strip(), 'files': entries,
            'scientific_verdict': None, 'mode': 'read-only preservation ledger; not a backup claim'}
target = out / 'workspace_before.json'
with target.open('x') as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)
with (out / 'tracked_before.patch').open('xb') as f:
    f.write(git('diff', '--binary', 'HEAD'))
with (out / 'status_before.txt').open('xb') as f:
    f.write(git('status', '--short'))
print(json.dumps({'status': 'CAPTURED', 'files': len(entries), 'bytes': sum(x['bytes'] for x in entries)}))
