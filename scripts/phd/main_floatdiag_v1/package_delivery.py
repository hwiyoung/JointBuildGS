"""Immutable staged ZIP with exact member SHA-256 and full CRC/hash read-back."""
import argparse
import hashlib
import json
import zipfile
from common import *

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['A1','A2'],required=True);a=ap.parse_args()
    folder=OUT/'packages';folder.mkdir(exist_ok=True)
    name=TASK+('_가_눈으로.zip' if a.stage=='A1' else '_가_셈.zip');dest=folder/name;assert not dest.exists()
    files={}
    def add(root,prefix,pattern='*'):
        for p in sorted(root.rglob(pattern)):
            if p.is_file():files[prefix+'/'+str(p.relative_to(root))]=p
    add(DOC/'보기','보기')
    if a.stage=='A1':
        add(DOC/'3d','3d')
        assert len(json.loads((DOC/'보기/data.json').read_text())['cases'])==7
        assert json.loads((OUT/'qa/A1/receipt.json').read_text())['status']=='PASS'
        for p in (DOC/'figures').glob('*'):
            if '_A1.' in p.name or any(p.stem.endswith(s) for s in ['_mesh','_gaussian']):files['figures/'+p.name]=p
    else:
        add(DOC/'figures','figures','*_A2*');add(DOC/'tables','tables')
        for p in DOC.glob('*.md'):files[p.name]=p
        add(Path('/repo/scripts/phd/main_floatdiag_v1'),'scripts')
        # Main-view arrays contain all requested paired values and stable pixel IDs.
        for site in SITES:
            for result in [f'nojudge_ALS_s0',f'lt_dynnow_ALS_s0']:
                for p in (OUT/'four_depths'/site/result).glob('*_paired.npz'):
                    files['pixels/'+site+'/'+result+'/'+p.name]=p
        add(OUT/'sections','sections')
        add(OUT/'four_depths/cases','pixels/cases')
        add(OUT/'provenance/open3d_source','open3d_source');add(OUT/'provenance/tsdf_update','tsdf_update')
        for p in (OUT/'multiview').rglob('patch_counts.csv.gz'):files['multiview/'+str(p.relative_to(OUT/'multiview'))]=p
        for p in (OUT/'multiview').rglob('patch_views.npz'):files['multiview/'+str(p.relative_to(OUT/'multiview'))]=p
    add(CFG,'configs');add(DOC/'provenance','provenance')
    hashes={name:sha(p) for name,p in files.items()}
    manifest=''.join(hashes[name]+'  '+name+'\n' for name in sorted(files))
    with zipfile.ZipFile(dest,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=4,allowZip64=True) as z:
        for name,p in files.items():z.write(p,name)
        z.writestr('SHA256SUMS',manifest)
        z.writestr('전달_범위.txt',('묶음 ①: 단계 가의 눈으로 보기. 원인 셈과 조건부 재실행은 묶음 ②에 담습니다.\n' if a.stage=='A1' else '묶음 ②: 단계 가의 진단, 조건부 짧은 재실행, 네 깊이 비교. 단계 나는 이번 발주에서 실행하지 않았습니다.\n')+'보기/index.html을 인터넷 없이 여십시오. scientific_verdict: null\n')
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        for name,digest in hashes.items():
            with z.open(name) as f:
                h=hashlib.sha256()
                for block in iter(lambda:f.read(2**20),b''):h.update(block)
            assert h.hexdigest()==digest,name
    assert dest.stat().st_size<400000000,'split is required before delivery'
    digest=sha(dest);dest.with_suffix('.zip.sha256').write_text(digest+'  '+dest.name+'\n')
    save(folder/(a.stage+'_package_verified.json'),dict(at=now(),file=str(dest),bytes=dest.stat().st_size,sha256=digest,
        files=len(files),CRC='PASS',all_member_sha256='PASS',scientific_verdict=None))
    print(dest,dest.stat().st_size,digest,flush=True)

if __name__=='__main__':main()
