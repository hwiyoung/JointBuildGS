import hashlib
import json
from pathlib import Path
root=Path('/bundle')
for name,expected in json.loads((root/'frozen_files.json').read_text()).items():
    h=hashlib.sha256()
    with (root/name).open('rb') as f:
        for block in iter(lambda:f.read(8<<20),b''):h.update(block)
    assert h.hexdigest()==expected,name
print('PASS_FROZEN_BUNDLE')
