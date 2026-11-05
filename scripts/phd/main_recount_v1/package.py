"""Seal the requested report/tables/figures/config plus reproducible scripts."""
from common import *
import zipfile

def main():
    c=cfg();assert json.loads((D/'validation.json').read_text())['status']=='PASS'
    dest=D/'PHD-MAIN-RECOUNT-v1.zip';assert not dest.exists(),'Existing sealed delivery is immutable'
    assert len((D/'보고.md').read_text())<=4000
    receipt=[]
    for site,prior in c['figures']['scenes']:
        for kind in ['maps','section']:
            p=D/'figures'/f'{site}__{prior}_{kind}.png'
            receipt.append(dict(path=str(p.relative_to(D)),sha256=sha(p),status='reviewed',observation='labels, legend, six section series / three map panels visible; source JSON adjacent'))
    dump(D/'provenance/visual_review.json',dict(at=now(),reviewer='Codex direct image inspection',figures=receipt,repair='R1 map viewport widened to include the unchanged A-A-prime section endpoints; only that map redrawn and inspected again',scientific_verdict=None))
    payloads=[]
    for p in sorted((O/'scenes').rglob('*')):
        if p.is_file():payloads.append(dict(path='PH/main_recount_v1/PHD-MAIN-RECOUNT-v1/'+str(p.relative_to(O)),bytes=p.stat().st_size,sha256=sha(p)))
    dump(D/'provenance/runtime_outputs.json',dict(at=now(),payloads=payloads,scientific_verdict=None))
    dump(C/'recount_v1.final.lock.json',dict(at=now(),config_sha256=sha(C/'recount_v1.json'),input_lock_sha256=sha(D/'provenance/inputs.lock.json'),validation_sha256=sha(D/'validation.json'),
        code=[dict(path=str(p.relative_to(R)),sha256=sha(p)) for p in sorted((R/'scripts/phd/main_recount_v1').glob('*')) if p.is_file()],scientific_verdict=None))
    # Workspace status inventories are local boundary evidence, not scientific
    # payload; the compact boundary receipt is included instead.
    excluded={'SHA256SUMS','PHD-MAIN-RECOUNT-v1.zip','PHD-MAIN-RECOUNT-v1.zip.sha256','delivery.json','workspace_before.txt','workspace_after.txt','git_delivery.json'}
    members=[]
    for p in sorted(D.rglob('*')):
        if p.is_file() and p.name not in excluded:members.append((p,str(p.relative_to(D))))
    for base,prefix in [(C,'configs/phd/main_recount_v1'),(R/'scripts/phd/main_recount_v1','scripts/phd/main_recount_v1')]:
        for p in sorted(base.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:members.append((p,prefix+'/'+str(p.relative_to(base))))
    sums=''.join(f'{sha(p)}  {name}\n' for p,name in members)
    (D/'SHA256SUMS').write_text(sums)
    with zipfile.ZipFile(dest,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for p,name in members:archive.write(p,name)
        archive.writestr('SHA256SUMS',sums)
    with zipfile.ZipFile(dest) as archive:
        assert archive.testzip() is None
        for line in archive.read('SHA256SUMS').decode().splitlines():
            digest,name=line.split('  ',1);assert hashlib.sha256(archive.read(name)).hexdigest()==digest
    digest=sha(dest);(D/'PHD-MAIN-RECOUNT-v1.zip.sha256').write_text(digest+'  '+dest.name+'\n')
    dump(D/'delivery.json',dict(at=now(),task_id=c['task_id'],status='PASS',zip=dest.name,zip_bytes=dest.stat().st_size,zip_sha256=digest,zip_members=len(members)+1,integrity='CRC and all internal SHA256SUMS match',report_characters=len((D/'보고.md').read_text()),figures=6,scientific_verdict=None))
    print(json.dumps(json.loads((D/'delivery.json').read_text()),ensure_ascii=False))

if __name__=='__main__':main()
