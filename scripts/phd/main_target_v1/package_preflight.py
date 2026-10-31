"""Deliver the amended stage 0 and stopped stage 1, excluding sealed/large payloads."""
import hashlib,os,zipfile
from common import *

def main():
    cfg,lock=training_locked();status=json.loads((OUT/'stage1_status.json').read_text())
    verification=json.loads((OUT/'stage1_verification.json').read_text())
    assert status['status']=='STOP_STAGE1_INITIAL_RENDER_DEPTH' and status['training_steps']==0
    assert verification['status']=='PASS_STOPPED_PREFLIGHT_EVIDENCE' and verification['maps_sha256_checked']==1838
    roots=[(CFG,'configs/phd/main_target_v1'),(Path(__file__).parent,'scripts/phd/main_target_v1'),
        (DOC,'docs/experiments/phd/main_target_v1'),(REPO/'src/phd/forks/GeoGS-conf-guided-v1-r19','src/phd/forks/GeoGS-conf-guided-v1-r19')]
    members={}
    for root,prefix in roots:
        for p in sorted(root.rglob('*')):
            if not p.is_file() or '__pycache__' in p.parts or p.suffix in ['.zip','.pyc'] or p.name=='delivery_receipt.json':continue
            members[prefix+'/'+p.relative_to(root).as_posix()]=p
    for name in ['stage1_status.json','stage1_verification.json','stage0_r1/verification.json']:
        members['payload/'+name]=OUT/name
    for p in sorted((OUT/'stage1').glob('*/seed_receipt.json')):members['payload/stage1/'+p.parent.name+'/'+p.name]=p
    for p in sorted((OUT/'stage1').glob('*/maps/index.json')):members['payload/stage1/'+p.parent.parent.name+'/maps/index.json']=p
    for folder in ['preflight_commands','diagnose_commands','decompose_commands']:
        for p in sorted((OUT/folder).glob('*/*.json')):members['payload/'+str(p.relative_to(OUT))]=p
    assert not any('/holdout/' in n or n.endswith('.npz') for n in members)
    report=(DOC/'영역별목표학습_보고_v1.md').read_text();assert len(report)<20000
    manifest=dict(at=stamp(),task_id='PHD-MAIN-TARGET-v1',experiment_status=status['status'],training_iterations=0,
        config_sha256=lock['config_sha256'],source_parent_commit=os.environ['TARGET_COMMIT'],
        members=[dict(path=n,bytes=p.stat().st_size,sha256=sha(p)) for n,p in members.items()],
        recomputation_boundary='Source and compact receipts only. Recalculation needs read-only external S0/S1/UNCERT/JUDGENUM/PHOTOCHECK payloads and exact Docker images; maps and large scenes are external.',
        holdout_patch_details_included=False,scientific_verdict=None)
    folder=OUT/'handover';folder.mkdir(exist_ok=True)
    filename='PHD-MAIN-TARGET-v1_결과_'+dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%m%d-%H%M')+'.zip'
    dest=folder/filename;assert not dest.exists()
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for n,p in members.items():z.write(p,n)
        z.writestr('MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        z.writestr('SHA256SUMS',''.join(f'{m["sha256"]}  {m["path"]}\n' for m in manifest['members']))
        z.writestr('README.txt','단계 0 개정 계산 통과. 단계 1 초기 렌더 깊이 5 cm 기준 미충족으로 학습 전 중단.\n최적화 0회. 7,000회 점검/본 학습/최종 메시/본 채점 완료 묶음이 아닙니다.\n현재 보고서: docs/experiments/phd/main_target_v1/영역별목표학습_보고_v1.md\nrevisions/는 이전 상태를 보존한 기록입니다. 확인용 상세 패치 및 큰 장면/지도는 포함하지 않습니다.\n무결성 검사는 과학적 결론이 아닙니다. scientific_verdict: null.\n')
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        for m in manifest['members']:assert hashlib.sha256(z.read(m['path'])).hexdigest()==m['sha256']
    digest=sha(dest);dest.with_suffix('.zip.sha256').write_text(f'{digest}  {filename}\n')
    receipt=dict(at=stamp(),status='PASS_ARCHIVE_INTEGRITY',experiment_status=status['status'],zip_path=str(dest),zip_name=filename,
        bytes=dest.stat().st_size,sha256=digest,crc='PASS',member_sha256='PASS',members_checked=len(members),
        training_iterations=0,holdout_patch_details_included=False,scientific_verdict=None)
    dump(DOC/'delivery_receipt.json',receipt);dump(folder/'delivery_receipt.json',receipt)
    print(json.dumps(receipt,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
