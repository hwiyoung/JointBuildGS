"""One new ZIP: byte-preserve the prior handover and add this presentation revision."""
from rfcore import *
from package import digest_stream
import zipfile,hashlib,shutil,os

def main():
    rev='representative_v1';assert load(DOC/rev/'verification.json')['status']=='PASS'
    old=PAY/'handover/PHD-MAIN-REGIONFIG-v2_handover.zip'
    expected='aa01dd0bd4043e346ae5386c841ec4b1f158d05d7466fae4067acc1a4f2604dc'
    assert sha(old)==expected
    root=PAY/rev/'handover';root.mkdir(parents=True,exist_ok=True)
    path=root/'PHD-MAIN-REGIONFIG-v2_representative_v1_handover.zip';assert not path.exists(),'Final archive already exists'
    sources={}
    for base,prefix in [(CFG/rev,'configs/phd/main_regionfig_v2/'+rev),
                        (DOC/rev,'docs/experiments/phd/main_regionfig_v2/'+rev)]:
        for p in sorted(base.rglob('*')):
            if p.is_file():sources[prefix+'/'+str(p.relative_to(base))]=p
    for p in sorted(Path('/repo/scripts/phd/main_regionfig_v2').glob('representative_*.py')):
        sources[str(p.relative_to('/repo'))]=p
    # Small supplied tables are useful for independent review. Large raw photos,
    # training payloads and unrelated tasks are deliberately outside this bundle.
    for p in sorted((PAY/'input').glob('*')):
        if p.is_file():sources['representative_inputs/'+p.name]=p
    hashes={};old_preserved=[]
    with zipfile.ZipFile(old) as zi,zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as zo:
        for info in zi.infolist():
            if info.is_dir():continue
            name=info.filename if info.filename!='SHA256SUMS' else 'handover_metadata/pre_representative_SHA256SUMS'
            assert name not in sources
            with zi.open(info) as a,zo.open(name,'w') as b:
                digest=hashlib.sha256()
                for chunk in iter(lambda:a.read(1<<20),b''):
                    b.write(chunk);digest.update(chunk)
            hashes[name]=digest.hexdigest();old_preserved.append(name)
        for name,p in sources.items():
            assert name not in hashes;hashes[name]=sha(p);zo.write(p,name)
        metadata=dict(task_id='PHD-MAIN-REGIONFIG-v2-REP1',at=now(),source_commit=os.environ['JBGS_SOURCE_HEAD'],
          original_archive_sha256=expected,original_members_preserved=len(old_preserved),
          original_root_manifest_renamed=True,scientific_verdict=None)
        payload=(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n').encode()
        name='handover_metadata/representative_commit.json';zo.writestr(name,payload);hashes[name]=hashlib.sha256(payload).hexdigest()
        name='먼저읽기_대표그림.txt';payload=('여덟 케이스 대표 그림 재작업\n\n먼저 docs/experiments/phd/main_regionfig_v2/representative_v1/index.html 을 여세요.\n대표그림_1.png ~ 대표그림_8.png 는 300 dpi 원본입니다.\n대표그림_보고.md 에 설명과 검증 링크가 있습니다. 기존 상세 그림과 보고서는 상위 폴더에 보존했습니다.\n\n모든 A는 결과 확인 후 고른 사례 설명용 패치입니다. 결과는 학습 없는 손실 최소점이며 과학적 판정은 null입니다.\n4번은 일부 실패가 포함된 보존, 7번은 물리적 비가시가 아닌 검사 사진 부족입니다.\n\n원본과 새 파일의 해시는 SHA256SUMS에 있습니다. 제공 NPZ는 representative_inputs에 포함했습니다.\n전체 재실행에는 기준 저장소와 기존 외부 입력, Docker 이미지가 필요합니다.\n').encode()
        zo.writestr(name,payload);hashes[name]=hashlib.sha256(payload).hexdigest()
        sums=''.join(f'{value}  {name}\n' for name,value in sorted(hashes.items())).encode();zo.writestr('SHA256SUMS',sums)
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(set(z.namelist()))==len(hashes)+1
        assert z.read('SHA256SUMS')==sums
        for name,value in hashes.items():
            with z.open(name) as f:assert digest_stream(f)==value,name
    assert all(sha(p)==hashes[name] for name,p in sources.items())
    assert sha(old)==expected
    receipt=dict(status='PASS',at=now(),file=str(path),bytes=path.stat().st_size,sha256=sha(path),
      original_members_preserved=len(old_preserved),files=len(hashes)+1,crc='PASS',member_sha256='PASS',
      source_commit=os.environ['JBGS_SOURCE_HEAD'],environment=environment(),scientific_verdict=None)
    dump(root/'package_receipt.json',receipt)
    path.with_suffix('.zip.sha256').write_text(f'{receipt["sha256"]}  {path.name}\n')
    print('PACKAGE',receipt,flush=True)

if __name__=='__main__':main()
