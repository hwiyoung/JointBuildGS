"""Seal a byte snapshot of compact r7 evidence; exclude sealed patch details and large arrays."""
import hashlib,zipfile,time
from common import *
def stable_bytes(p):
    # Snapshot mutable compact logs without stopping authorized ongoing training.
    for attempt in range(60):
        before=p.stat();data=p.read_bytes();after=p.stat()
        if (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns):
            try:
                if p.suffix=='.json':json.loads(data)
                elif p.suffix=='.jsonl':
                    if data and not data.endswith(b'\n'):data=data[:data.rfind(b'\n')+1]
                    for line in data.splitlines():json.loads(line)
                return data
            except (ValueError,UnicodeError):pass
        time.sleep(.05)
    raise RuntimeError('Unable to snapshot compact file: '+str(p))
def main():
    audit=json.loads((DOC/'tables/final_audit_r7.json').read_text());assert audit['status']=='PASS_R7_DELIVERY_AUDIT';members={}
    roots=[(CFG,'configs/phd/main_target_v1'),(Path(__file__).parent,'scripts/phd/main_target_v1'),(DOC,'docs/experiments/phd/main_target_v1')]
    roots += [(REPO/'src/phd/forks'/f'GeoGS-conf-guided-v1-r{rev}',f'src/phd/forks/GeoGS-conf-guided-v1-r{rev}') for rev in [19,20,21]]
    for root,prefix in roots:
        for p in sorted(root.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ['.pyc','.zip'] and not p.name.startswith('delivery_receipt'):members[prefix+'/'+p.relative_to(root).as_posix()]=stable_bytes(p)
    for p in sorted((OUT/'r7').rglob('*')):
        if p.is_file() and p.suffix in ['.json','.jsonl','.log'] and '/renders/' not in str(p) and '/maxid_build/' not in str(p):members['payload/'+p.relative_to(OUT).as_posix()]=stable_bytes(p)
    for p in [OUT/'r5/runtime/maxid_rasterizer/cuda_rasterizer/forward.cu',OUT/'r5/runtime/maxid_rasterizer/LICENSE.md']:
        if p.exists():members['diagnostic_renderer/'+p.name]=stable_bytes(p)
    assert not any('/holdout/' in key or key.endswith('.npz') for key in members)
    external=[];candidates=[]
    for prior in ['ALS','LoD2']:
        run=OUT/'r7/runs'/f'tg_B173nb_b10_{prior}_s0_r7';base=OUT/'r7/baselines'/f'base7k_B173nb_b10_{prior}_s0'
        for root in [run,base]:candidates += [root/'model/point_cloud/iteration_7000/point_cloud.ply',root/'post7000/merged.ply',root/'post7000/patch_z.npz']
        candidates += [run/'post7000/origin_attribution.npz',run/'model/target_monitor/snapshot_0.npz',run/'model/target_monitor/snapshot_7000.npz',run/'model/jbgs_complete/iteration_7000/checkpoint.pth',OUT/'r7/stage1'/f'B173nb_b10_{prior}/seeds.npz']
    candidates += sorted((OUT/'r7/targets').glob('*.npz'))
    for p in candidates:external.append(dict(path='PH/main_target_v1/PHD-MAIN-TARGET-v1/'+p.relative_to(OUT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
    manifest=dict(at=stamp(),task_id='PHD-MAIN-TARGET-v1',revision='r7',experiment_status=audit['experiment_status'],source_parent_commit=json.loads((CFG/'fork_r21_base.json').read_text())['base_commit'],config_sha256=sha(CFG/'target_v1.r7.json'),stage0_config_sha256=sha(CFG/'target_v1.r7.stage0.json'),members=[dict(path=n,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for n,data in members.items()],external_payloads=external,holdout_patch_details_included=False,scientific_verdict=None,
        recomputation_boundary='Exact external S0/S1/UNCERT/JUDGENUM/WIDEN inputs, frozen r7 maps/seeds and full models/meshes, inherited scorer and Docker image are required. This archive contains code, reports, figures and compact byte snapshots; it is not a self-contained data backup.')
    folder=OUT/'handover';name='PHD-MAIN-TARGET-v1_점검r7_'+dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%m%d-%H%M')+'.zip';dest=folder/name;assert not dest.exists()
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for key,data in members.items():z.writestr(key,data)
        z.writestr('MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');z.writestr('SHA256SUMS',''.join(f'{m["sha256"]}  {m["path"]}\n' for m in manifest['members']))
        z.writestr('README.txt','PHD-MAIN-TARGET-v1 r7 7,000회 점검\n상태: '+audit['experiment_status']+'\n최신 보고: docs/experiments/phd/main_target_v1/단계1_7000회_점검_r7.md\n사라짐 판단: docs/experiments/phd/main_target_v1/단계0_사라짐_점검_r7.md\n전체 보고: docs/experiments/phd/main_target_v1/영역별목표학습_보고_v1.md\n기존 방법과 r7 모두 7,000회로 비교합니다. 이전 r4n/r6의 고정 기준은 현재 판정 기준이 아닙니다.\n참값 면 측정값이 없는 사라짐 패치는 확인 불가로 기록합니다. 특히 B173 LoD2 대부분의 사라짐 넓이가 이 경우이므로 맞게 지웠다고 해석하지 마세요.\n확인용은 집계 수/넓이/비율만 포함합니다. 상세 패치와 큰 모델/메시는 제외합니다. 정확한 재계산에는 MANIFEST의 외부 자료가 필요합니다.\nCRC/SHA-256은 무결성 검증입니다. scientific_verdict: null.\n')
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        for m in manifest['members']:assert hashlib.sha256(z.read(m['path'])).hexdigest()==m['sha256']
    digest=sha(dest);dest.with_suffix('.zip.sha256').write_text(digest+'  '+name+'\n');receipt=dict(at=stamp(),status='PASS_ARCHIVE_INTEGRITY',experiment_status=audit['experiment_status'],zip_name=name,zip_path='PH/main_target_v1/PHD-MAIN-TARGET-v1/handover/'+name,bytes=dest.stat().st_size,sha256=digest,members_checked=len(members),crc='PASS',member_sha256='PASS',scientific_verdict=None)
    dump(folder/'delivery_receipt_r7.json',receipt);dump(DOC/'delivery_receipt_r7.json',receipt);print(json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
