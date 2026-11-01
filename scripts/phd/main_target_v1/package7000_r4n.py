"""Seal the stopped 7000 checkpoint handover, excluding holdout details and large scenes."""
import hashlib,os,zipfile
from common import *

def main():
    audit=json.loads((DOC/'tables/final_7000_audit_r4n.json').read_text());assert audit['status']=='PASS_DELIVERY_AUDIT'
    status=json.loads((OUT/'r4n/pilot_status.json').read_text());assert status['status']=='STOP_PILOT'
    members={}
    for root,prefix in [(CFG,'configs/phd/main_target_v1'),(Path(__file__).parent,'scripts/phd/main_target_v1'),
        (DOC,'docs/experiments/phd/main_target_v1'),(REPO/'src/phd/forks/GeoGS-conf-guided-v1-r19','src/phd/forks/GeoGS-conf-guided-v1-r19')]:
        for p in sorted(root.rglob('*')):
            if not p.is_file() or '__pycache__' in p.parts or p.suffix in ['.zip','.pyc'] or p.name.startswith('delivery_receipt'):continue
            members[prefix+'/'+p.relative_to(root).as_posix()]=p
    for revision in ['r2_stage1_source','r4_stage1_source']:
        root=OUT/'revisions'/revision
        for p in sorted(root.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':members['preserved_source/'+revision+'/'+p.relative_to(root).as_posix()]=p
    for revision in ['r4','r4n','r5']:
        for p in sorted((OUT/revision).rglob('*')):
            if not p.is_file() or p.suffix not in ['.json','.jsonl','.log']:continue
            # TSDF planning logs and compact receipts are included; arrays, mesh and model bytes stay external.
            if '/renders/' in str(p) or '/failed_attempts/' in str(p) or '/before_original_glass_masks/' in str(p):continue
            members['payload/'+p.relative_to(OUT).as_posix()]=p
    for name in ['r2/preflight_verification.json','r3/verification.json','r2/stage0/verification.json','r2/stage0/status.json']:
        p=OUT/name
        if p.exists():members['payload/'+name]=p
    for folder,pattern in [('r2/stage1','*/maps/index.json'),('r2/stage1','*/seed_receipt.json'),('r2/verification','*.json'),
        ('r3/replay_v2','*/verification.json'),('r2/background','*/*/receipt.json')]:
        for p in sorted((OUT/folder).glob(pattern)):members['payload/'+p.relative_to(OUT).as_posix()]=p
    for p in sorted((OUT/'r5/code_versions').glob('*.py')):members['preserved_source/r5/'+p.name]=p
    for p in [OUT/'r5/runtime/maxid_rasterizer/cuda_rasterizer/forward.cu',OUT/'r5/runtime/maxid_rasterizer/LICENSE.md']:
        if p.exists():members['diagnostic_renderer/'+p.name]=p
    assert not any('/holdout/' in name or name.endswith('.npz') for name in members)
    external=[]
    for prior in ['ALS','LoD2']:
        run=OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0'
        files=[run/'model/point_cloud/iteration_7000/point_cloud.ply',run/'post7000/merged.ply',
            run/'model/target_monitor/snapshot_0.npz',run/'model/target_monitor/snapshot_6000.npz',run/'model/target_monitor/snapshot_7000.npz',
            run/'model/check7000/large_background_descendants.npz',run/'post7000/patch_z.npz',run/'post7000/origin_attribution.npz',
            OUT/'r2/stage1'/f'B173nb_b10_{prior}'/'seeds.npz']
        for p in files:external.append(dict(path='PH/main_target_v1/PHD-MAIN-TARGET-v1/'+p.relative_to(OUT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    for p in sorted((OUT/'r5').rglob('*.npz')):
        if any(x in p.parts for x in ['failed_attempts','before_original_glass_masks']):continue
        external.append(dict(path='PH/main_target_v1/PHD-MAIN-TARGET-v1/'+p.relative_to(OUT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    for model in json.loads((CFG/'diagnostics_r5.json').read_text())['models']:
        p=Path(model['model'])/f"point_cloud/iteration_{model['iteration']}/point_cloud.ply"
        external.append(dict(path='PH/'+p.relative_to(PH).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    manifest=dict(at=stamp(),task_id='PHD-MAIN-TARGET-v1',status='STOP_7000_TARGET_COVERAGE',
        source_parent_commit=json.loads((CFG/'target_v1.runtime.r4n.lock.json').read_text())['source_commit'],diagnostic_revision='r5',record_continuation_status='NOT_RUN_NO_OPTIMIZER_STATE',config_sha256=sha(CFG/'target_v1.stage1.r4n.json'),
        members=[dict(path=n,bytes=p.stat().st_size,sha256=sha(p)) for n,p in members.items()],external_payloads=external,
        render_hashes='docs/experiments/phd/main_target_v1/tables/verification7000_{ALS|LoD2}_r4n.json',
        recomputation_boundary='Requires exact external S0/S1/UNCERT/JUDGENUM/PHOTOCHECK inputs, r2 target maps and seeds, saved large arrays/models/meshes, base repository and Docker image. This archive contains code, reports and compact evidence.',
        holdout_patch_details_included=False,scientific_verdict=None)
    folder=OUT/'handover';folder.mkdir(exist_ok=True)
    name='PHD-MAIN-TARGET-v1_점검_'+dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%m%d-%H%M')+'.zip';dest=folder/name;assert not dest.exists()
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for n,p in members.items():z.write(p,n)
        z.writestr('MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        z.writestr('SHA256SUMS',''.join(f'{m["sha256"]}  {m["path"]}\n' for m in manifest['members']))
        z.writestr('README.txt','PHD-MAIN-TARGET-v1 7,000회 점검 묶음\n두 판 7,000회 모델 저장. 목표 따름 ALS 32.7237%, LoD2 34.2787%로 80% 미달하여 공동 중단.\n나머지 여섯 판 미시작. 기록용 30,000회 이어 학습은 최적화 상태 부재로 미실행. 저장 기준선의 동일 목표 비교, 개별 최대 기여, 출신별 이동, 자리별 판단 집계는 완료.\n현재 보고서: docs/experiments/phd/main_target_v1/영역별목표학습_보고_v1.md\n최신 진단: docs/experiments/phd/main_target_v1/중단후_비교진단_r5.md\n자리별 판단: docs/experiments/phd/main_target_v1/자리별_판단점검_r5.md\n상세 점검: docs/experiments/phd/main_target_v1/단계1_7000회_점검_r4n.md\n이전 개정의 실패와 사용자 결정은 이력으로 보존합니다.\n확인용 패치 상세와 큰 장면·지도·메시는 포함하지 않습니다. 외부 자료와 환경이 있어야 재계산할 수 있습니다.\nCRC와 SHA-256은 무결성 검사이며 scientific_verdict는 null입니다.\n')
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        for m in manifest['members']:assert hashlib.sha256(z.read(m['path'])).hexdigest()==m['sha256']
    digest=sha(dest);dest.with_suffix('.zip.sha256').write_text(digest+'  '+name+'\n')
    receipt=dict(at=stamp(),status='PASS_ARCHIVE_INTEGRITY',experiment_status='STOP_7000_TARGET_COVERAGE',zip_name=name,
        zip_path='PH/main_target_v1/PHD-MAIN-TARGET-v1/handover/'+name,bytes=dest.stat().st_size,sha256=digest,members_checked=len(members),
        crc='PASS',member_sha256='PASS',saved_iteration=7000,holdout_patch_details_included=False,scientific_verdict=None)
    dump(folder/'delivery_receipt_r4n.json',receipt);dump(DOC/'delivery_receipt_r4n.json',receipt)
    print(json.dumps(receipt,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
