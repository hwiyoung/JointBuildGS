"""Recheck immutable input pins before delivery; no source writes."""
from mesh_common import *
cfg=json.loads((C/'meshpatch_v1.json').read_text());rows=[]
for x in cfg['inputs']:
    p=Path(x['path']);got=sha(p);assert got==x['sha256'],p;rows.append(dict(path=str(p),sha256=got))
supp=C/'region_delivery_addendum_v1.json'
for x in json.loads(supp.read_text())['sources']:
    p=Path('/ph')/x['path'].split('/phase-payloads/phd/',1)[1];got=sha(p);assert got==x['sha256'],p;rows.append(dict(path=str(p),sha256=got))
dump(D/'tables/input_integrity.json',dict(status='PASS',checked_at=now(),files=len(rows),inputs=rows,region_addendum_sha256=sha(supp),scientific_verdict=None))
print('input integrity PASS',len(rows))
