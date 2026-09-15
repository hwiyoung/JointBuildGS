#!/usr/bin/env python3
"""Materialize explicit candidate and principal-support memberships from a sealed audit."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

root=Path('/input');out=Path('/output/exports');out.mkdir(exist_ok=False)
summary=json.loads((root/'summary.json').read_text());manifest=json.loads((root/'candidate_memberships.json').read_text())
hashes={}
for rid,selection in manifest['regions'].items():
    rows=list(csv.DictReader((root/(rid+'_views.csv')).open()))
    for role in ('candidates','train','evaluation'):
        path=out/(rid+'_'+role+'_names.txt')
        path.write_text(''.join(manifest['names'][i]+'\n' for i in selection[role]))
    train=[rows[i] for i in selection['train']]
    ranked=sorted(train,key=lambda r:-float(r['support_mass']))
    total=sum(float(r['support_mass']) for r in ranked);cumulative=0.;principal=[]
    for rank,row in enumerate(ranked,1):
        fraction=float(row['support_mass'])/total;cumulative+=fraction
        principal.append(dict(rank=rank,name=row['name'],native_pixels=int(row['native_pixels']),
            rgb_pixels=int(row['rgb_pixels']),share=fraction,cumulative_share=cumulative))
        if cumulative>=.9:break
    assert len(principal)==summary['regions'][rid]['train']['n_cumulative']['0.9']
    path=out/(rid+'_principal_90pct.csv')
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=principal[0].keys());w.writeheader();w.writerows(principal)
for path in out.iterdir():
    hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
receipt=dict(scientific_verdict=None,actual_training=False,
    input_receipt_sha256=hashlib.sha256((root/'receipt.json').read_bytes()).hexdigest(),
    script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),outputs_sha256=hashes)
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({rid:s['train']['n_cumulative']['0.9'] for rid,s in summary['regions'].items()}))
