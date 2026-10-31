"""Public handover ZIP with explicit replay boundary, hashes and CRC verification."""
import hashlib
import zipfile
from cp2_common import *

def main():
    report=DOC/'원인확인_보고_v1.md';assert report.exists()
    validation=json.loads((DOC/'tables/final_validation.json').read_text())
    assert validation['status']=='PASS_WITH_2_STOPPED_ARMS'
    folder=OUT/'handover';folder.mkdir(exist_ok=True)
    stamp=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%m%d-%H%M')
    archive=folder/f'PHD-MAIN-CANDPICK-v2_결과_{stamp}.zip';assert not archive.exists()
    files=[]
    for root,name in [(CFG,'configs'),(Path('/repo/scripts/phd/main_candpick_v2'),'scripts'),(DOC,'report')]:
        files += [(p,name+'/'+str(p.relative_to(root))) for p in sorted(root.rglob('*')) if p.is_file() and p.name!='package_receipt.json']
    for sub in ['bounds','depth_views','preflight','depth','renders','photo_dl','revisions','source_reference']:
        root=OUT/sub
        files += [(p,'payload/'+sub+'/'+str(p.relative_to(root))) for p in sorted(root.rglob('*')) if p.is_file()]
    for run in sorted((OUT/'runs').iterdir()):
        if not run.is_dir():continue
        for p in sorted(run.iterdir()):
            if p.suffix in ['.json','.jsonl','.npz']:
                files.append((p,'payload/runs/'+run.name+'/'+p.name))
    assert all('/holdout/' not in name for _,name in files)
    # Count/hash-only public manifest is permitted, never sealed point/patch data.
    manifest=[dict(path=name,bytes=p.stat().st_size,sha256=sha(p)) for p,name in files]
    note=('PHD-MAIN-CANDPICK-v2 결과\n\n'
          '22판 학습 완료, 2판 단위 점검 중단. 새 22판과 v1 기준 6판의 깊이 채점.\n'
          'report/원인확인_보고_v1.md에서 시작한다.\n'
          '공개 점/패치 값, 후보 상태 0/500/1000/끝, 기록, 표/그림, 설정/코드를 포함한다.\n'
          '주 깊이 결과는 수정 기록 depth_readout_amendment_r1을 적용했다. revisions/depth_r0의 첫 채점은 오류 이력이며 주 결과로 사용하지 않는다.\n'
          '확인용 상세 값은 제외했다. 공개 확인용 자료는 수, 넓이, SHA-256뿐이다.\n'
          '원본 사진, 바탕 PLY, v1 상태와 외부 원본 입력은 포함하지 않는다. 설정의 정확한 입력 경로와 SHA-256으로 연결한다.\n'
          '원본 입력이 있어야 학습과 렌더를 다시 실행할 수 있다. 이 ZIP만으로는 원본 입력을 복원할 수 없다.\n'
          'SHA256SUMS는 파일 바이트를 확인하며 과학적 타당성이나 사용자 시각 검토를 뜻하지 않는다.\n'
          'scientific_verdict: null\n')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as z:
        z.writestr('README.txt',note)
        for p,name in files:z.write(p,name)
        z.writestr('manifest.json',json.dumps(dict(files=manifest,source=SOURCE,scientific_verdict=None),ensure_ascii=False,indent=2)+'\n')
        z.writestr('SHA256SUMS',''.join(f'{r["sha256"]}  {r["path"]}\n' for r in manifest))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for r in manifest:
            h=hashlib.sha256()
            with z.open(r['path']) as f:
                for chunk in iter(lambda:f.read(4<<20),b''):h.update(chunk)
            assert h.hexdigest()==r['sha256'],r['path']
    receipt=dict(status='PASS_CRC_AND_MEMBER_SHA256',at=now(),archive=bind(archive),members=len(manifest)+3,
        holdout_details_included=False,source=SOURCE,scientific_verdict=None)
    save(folder/(archive.stem+'.verification.json'),receipt)
    save(DOC/'tables/package_receipt.json',receipt,replace=True)
    print(clean(receipt),flush=True)

if __name__=='__main__':main()
