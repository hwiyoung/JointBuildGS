"""Split original local-frame 3D and inspectable arrays into bounded standalone ZIPs."""
import hashlib
import argparse
import json
import zipfile
from common import *

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--kind',choices=['geometry','arrays'],required=True);a=ap.parse_args()
    root=OUT/'packages';files=[]
    directories=['3d'] if a.kind=='geometry' else ['formation','gaussians','sections','four_depths','multiview']
    for directory in directories:
        for p in sorted((OUT/directory).rglob('*')):
            if p.is_file() and p.suffix in ['.ply','.npz','.json','.gz']:
                # Full 3D crops and every formation array, including saved birth
                # observations. Original global checkpoint PLYs are referenced,
                # not duplicated as a newly trained result.
                files.append(p)
    if a.kind=='arrays':
        for site in SITES:
            photos=json.loads((CFG/f'photos_{site}_ALS.json').read_text())['cases']
            names={r['main']['view'] for r in photos if r['main']}
            for result in RESULTS:
                root2=OUT/'diagnostics'/site/result
                files += [root2/(n+'.npz') for n in sorted(names)]
                files += [root2/'centre_gradients.npz',root2/'receipt.json']
    groups=[];current=[];n=0
    for p in files:
        assert p.stat().st_size<360000000,p
        if n+p.stat().st_size>360000000 and current:groups.append(current);current=[];n=0
        current.append(p);n+=p.stat().st_size
    if current:groups.append(current)
    rows=[]
    for i,group in enumerate(groups,1):
        label='원본3D' if a.kind=='geometry' else '원본배열'
        dest=root/f'{TASK}_가_{label}_{i:02}.zip';assert not dest.exists()
        digests={str(p.relative_to(OUT)):sha(p) for p in group}
        with zipfile.ZipFile(dest,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=4) as z:
            for p in group:z.write(p,str(p.relative_to(OUT)))
            z.writestr('SHA256SUMS',''.join(d+'  '+k+'\n' for k,d in digests.items()))
        with zipfile.ZipFile(dest) as z:
            assert z.testzip() is None
            for k,d in digests.items():
                h=hashlib.sha256()
                with z.open(k) as f:
                    for block in iter(lambda:f.read(2**20),b''):h.update(block)
                assert h.hexdigest()==d
        assert dest.stat().st_size<400000000
        digest=sha(dest);dest.with_suffix('.zip.sha256').write_text(digest+'  '+dest.name+'\n')
        rows.append(dict(part=i,file=dest.name,bytes=dest.stat().st_size,sha256=digest,members=digests,CRC='PASS',scientific_verdict=None))
        print(dest.name,dest.stat().st_size,'CRC/SHA PASS',flush=True)
    save(root/('payload_packages_'+a.kind+'.json'),dict(at=now(),parts=rows,scientific_verdict=None))

if __name__=='__main__':main()
