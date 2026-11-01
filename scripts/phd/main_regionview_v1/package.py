"""Portable public bundle with no sealed or per-patch payloads."""
import hashlib
import zipfile
from common import *

def main():
    revisions=['r2','r7'] if REV=='r7' else ['r2']
    for rev in revisions:assert read(OUT/f'verification_{rev}.json')['status']=='PASS_TECHNICAL_VERIFICATION'
    assert (DOC/'영역지도면요약_보고_v1.md').exists()
    held=set(read(JN/'holdout/scope_membership.json')['buildings'])
    selected=[]
    for p in sorted(DOC.rglob('*')):
        if not p.is_file():continue
        if p.name.startswith('package_'):continue
        if REV=='r2' and ('r7' in p.name):continue
        assert p.stat().st_size<20*1024*1024,('large file excluded by contract',str(p))
        if p.suffix in ['.md','.json','.csv']:
            text=p.read_text(encoding='utf-8-sig');assert not any(b in text for b in held)
        selected.append((p,p.relative_to(DOC).as_posix()))
    for root,prefix in [(REPO/'scripts/phd/main_regionview_v1','reproduce/scripts'),(CFG,'reproduce/configs')]:
        for p in sorted(root.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:selected.append((p,prefix+'/'+p.relative_to(root).as_posix()))
    for rev in revisions:
        for name in [f'input_ledger_{rev}.json',f'verification_{rev}.json',f'measurement_complete_{rev}.json',f'figures_complete_{rev}.json',f'figure_inputs_{rev}.json']:
            p=OUT/name
            if p.exists():selected.append((p,'receipts/'+name))
    created=dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    path=writable(OUT/'handover'/f'PHD-MAIN-REGIONVIEW-v1_결과_{created:%m%d-%H%M}.zip')
    assert not path.exists(),'immutable bundle name already exists'
    manifest={name:sha(p) for p,name in selected}
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p,name in selected:
            assert not name.startswith('holdout/') and '/holdout/' not in name
            z.write(p,name)
        z.writestr('SHA256SUMS',''.join(f'{digest}  {name}\n' for name,digest in manifest.items()))
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        for name,digest in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==digest
    digest=sha(path);writable(path.with_suffix('.zip.sha256')).write_text(f'{digest}  {path.name}\n')
    receipt=dict(at=stamp(),status='PASS_ZIP_CRC_AND_SHA256',revision=REV,revisions=revisions,
        path=str(path),sha256=digest,bytes=path.stat().st_size,member_count=len(manifest)+1,
        exclusions=['all holdout per-face/per-patch detail','all raw runtime inputs','all derived patch arrays','logs and caches'],
        recomputation_boundary='requires exact external inputs listed in receipts; bundle contains scripts/configuration and public figures/tables only',
        scientific_verdict=None)
    dump(OUT/f'package_{REV}.json',receipt);dump(DOC/f'package_{REV}.json',receipt)
    print(json.dumps(receipt,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
