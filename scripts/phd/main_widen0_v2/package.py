"""Explicit allowlist for light/full delivery; no holdout payloads."""
import json
from pathlib import Path
import zipfile
import numpy as np
from preflight import sha,dump
O=Path('/out');D=Path('/docs');C=Path('/cfg');S=Path(__file__).parent
def main():
    gate=json.loads((O/'gates/final_values.json').read_text());assert gate['status']=='PASS'
    files=[]
    for root,prefix in [(D,'docs'),(C,'configs'),(S,'scripts')]:
        for p in sorted(root.rglob('*')):
            if p.is_file() and p.suffix in ['.md','.json','.csv','.png','.pdf','.py','.sh']:
                files.append((p,f'{prefix}/{p.relative_to(root)}'))
    patch=[]
    for p in sorted((O/'patch_values').glob('*')):
        if p.suffix not in ['.json','.npz']:continue
        if p.suffix=='.npz':
            with np.load(p) as z:assert not z['holdout'].any(),p
        patch.append((p,f'patch_values/{p.name}'))
    records=[]
    for suffix,selected in [('handover_light',files),('handover',files+patch)]:
        name=f'PHD-MAIN-WIDEN0-v2_{suffix}.zip';target=O/name
        sums=''.join(f'{sha(p)}  {arc}\n' for p,arc in selected)
        with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as z:
            for p,arc in selected:
                assert '/holdout/' not in arc and not arc.startswith('holdout/'),arc
                z.write(p,arc,compress_type=zipfile.ZIP_STORED if p.suffix in ['.npz','.png','.pdf'] else zipfile.ZIP_DEFLATED)
            z.writestr('SHA256SUMS',sums)
        with zipfile.ZipFile(target) as z:
            assert z.testzip() is None
            names=z.namelist();assert all(not n.startswith('holdout/') for n in names)
            if suffix=='handover_light':assert not any(n.startswith('patch_values/') for n in names)
        records.append(dict(file=name,bytes=target.stat().st_size,sha256=sha(target),members=len(selected)+1,holdout_included=False))
        print('archive validated',name,flush=True)
    dump(O/'handover_manifest.json',dict(archives=records,scientific_verdict=None))
    (O/'SHA256SUMS').write_text(''.join(f"{r['sha256']}  {r['file']}\n" for r in records))
if __name__=='__main__':main()
