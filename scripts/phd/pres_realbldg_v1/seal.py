"""Package only this task's public delivery and verify every archived byte."""
from common import *

cfg()
archive=D/'PHD-PRES-REALBLDG-v1.zip'
excluded={'PHD-PRES-REALBLDG-v1.zip','PHD-PRES-REALBLDG-v1.zip.sha256','SHA256SUMS','delivery.json'}
members={}
for root,prefix in [(D,'docs'),(C,'config'),(R/'scripts/phd/pres_realbldg_v1','scripts')]:
    for p in sorted(root.rglob('*')):
        if not p.is_file() or p.name in excluded:continue
        assert not p.is_symlink()
        assert p.suffix not in {'.npz','.npy','.ply','.laz','.las','.zlist'},str(p)
        members[prefix+'/'+p.relative_to(root).as_posix()]=p
checks={name:sha(p) for name,p in members.items()}
manifest=''.join(f'{digest}  {name}\n' for name,digest in sorted(checks.items()))
(D/'SHA256SUMS').write_text(manifest)
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name,p in sorted(members.items()):z.write(p,name)
    z.writestr('SHA256SUMS',manifest)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert len(z.namelist())==len(members)+1
    for name,digest in checks.items():assert hashlib.sha256(z.read(name)).hexdigest()==digest,name
    assert z.read('SHA256SUMS').decode()==manifest
digest=sha(archive)
(D/'PHD-PRES-REALBLDG-v1.zip.sha256').write_text(digest+'  '+archive.name+'\n')
dump(D/'delivery.json',dict(at=now(),task_id='PHD-PRES-REALBLDG-v1',archive=archive.name,
    archive_bytes=archive.stat().st_size,sha256=digest,members=len(members)+1,
    crc='PASS',member_sha256='PASS',scope='saved roof and wall cases; ground cases unavailable',
    all_five_full_spatial_scope=None,scientific_verdict=None))
print('SEALED',archive.name,archive.stat().st_size,len(members)+1,digest)
