"""Seal r6 checkpoint evidence, excluding holdout details and large external payloads."""
import hashlib,zipfile
from common import *
def main():
 audit=json.loads((DOC/'tables/final_audit_r6.json').read_text());assert audit['status']=='PASS_R6_DELIVERY_AUDIT'
 members={}
 for root,prefix in [(CFG,'configs/phd/main_target_v1'),(Path(__file__).parent,'scripts/phd/main_target_v1'),(DOC,'docs/experiments/phd/main_target_v1'),
  (REPO/'src/phd/forks/GeoGS-conf-guided-v1-r19','src/phd/forks/GeoGS-conf-guided-v1-r19'),(REPO/'src/phd/forks/GeoGS-conf-guided-v1-r20','src/phd/forks/GeoGS-conf-guided-v1-r20')]:
  for p in sorted(root.rglob('*')):
   if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ['.pyc','.zip'] and not p.name.startswith('delivery_receipt'):members[prefix+'/'+p.relative_to(root).as_posix()]=p
 for p in sorted((OUT/'r6').rglob('*')):
  if p.is_file() and p.suffix in ['.json','.jsonl','.log'] and '/renders/' not in str(p) and '/maxid_build/' not in str(p):members['payload/'+p.relative_to(OUT).as_posix()]=p
 root=OUT/'r6/revisions/unit_source'
 for p in root.rglob('*'):
  if p.is_file() and p.suffix!='.pyc':members['preserved_source/r6_unit/'+p.relative_to(root).as_posix()]=p
 for prior in ['ALS','LoD2']:
  for name in ['maps/index.json','seed_receipt.json']:
   p=OUT/'r2/stage1'/f'B173nb_b10_{prior}'/name;members['payload/'+p.relative_to(OUT).as_posix()]=p
 for name in ['r4n/preflight_acceptance.json','r2/stage0/verification.json','r2/stage0/status.json']:
  p=OUT/name;members['payload/'+name]=p
 for p in [OUT/'r5/runtime/maxid_rasterizer/cuda_rasterizer/forward.cu',OUT/'r5/runtime/maxid_rasterizer/LICENSE.md']:
  if p.exists():members['diagnostic_renderer/'+p.name]=p
 assert not any('/holdout/' in name or name.endswith('.npz') for name in members)
 external=[]
 for prior in ['ALS','LoD2']:
  run=OUT/'r6/runs'/f'tg_B173nb_b10_{prior}_s0_r6'
  candidates=[run/'model/point_cloud/iteration_7000/point_cloud.ply',run/'post7000/merged.ply',run/'post7000/patch_z.npz',run/'post7000/origin_attribution.npz',OUT/'r2/stage1'/f'B173nb_b10_{prior}/seeds.npz']
  candidates+=list((run/'model/target_monitor').glob('snapshot_*.npz'))
  for i in [7000,15000,30000]:
   p=run/'model/jbgs_complete'/f'iteration_{i}/checkpoint.pth'
   if p.exists():candidates.append(p)
  for p in candidates:external.append(dict(path='PH/main_target_v1/PHD-MAIN-TARGET-v1/'+p.relative_to(OUT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)))
 manifest=dict(at=stamp(),task_id='PHD-MAIN-TARGET-v1',revision='r6',experiment_status=audit['experiment_status'],source_parent_commit=json.loads((CFG/'fork_r20_base.json').read_text())['base_commit'],
  config_sha256=sha(CFG/'target_v1.r6.json'),members=[dict(path=n,bytes=p.stat().st_size,sha256=sha(p)) for n,p in members.items()],external_payloads=external,
  render_hashes='docs/experiments/phd/main_target_v1/tables/verification7000_{ALS|LoD2}_r6.json',
  recomputation_boundary='Exact external S0/S1/UNCERT inputs, locked r2 maps/seeds, large models/checkpoints/meshes, existing scorer repository and Docker image are required. Archive contains code, reports, figures and compact evidence.',holdout_patch_details_included=False,scientific_verdict=None)
 folder=OUT/'handover';name='PHD-MAIN-TARGET-v1_점검r6_'+dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%m%d-%H%M')+'.zip';dest=folder/name;assert not dest.exists()
 with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for n,p in members.items():z.write(p,n)
  z.writestr('MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');z.writestr('SHA256SUMS',''.join(f'{m["sha256"]}  {m["path"]}\n' for m in manifest['members']))
  z.writestr('README.txt','PHD-MAIN-TARGET-v1 r6 7,000회 점검\n상태: '+audit['experiment_status']+'\n최신 보고서: docs/experiments/phd/main_target_v1/단계1_7000회_점검_r6.md\n전체 보고서: docs/experiments/phd/main_target_v1/영역별목표학습_보고_v1.md\nr4n/r5 보고서는 이전 이력입니다. r6는 화소 80%를 통과 기준으로 쓰지 않습니다.\n두 판의 7,000회 Adam 포함 전체 상태를 외부 payload로 보존합니다. 미도달/미저장 반복을 완료로 해석하지 마세요.\n확인용 패치 상세 및 큰 모델/메시/배열은 제외합니다. 재계산에는 MANIFEST의 외부 자료와 Docker 환경이 필요합니다.\nCRC 및 SHA-256은 무결성 검사입니다. scientific_verdict: null.\n')
 with zipfile.ZipFile(dest) as z:
  assert z.testzip() is None
  for m in manifest['members']:assert hashlib.sha256(z.read(m['path'])).hexdigest()==m['sha256']
 digest=sha(dest);dest.with_suffix('.zip.sha256').write_text(digest+'  '+name+'\n')
 receipt=dict(at=stamp(),status='PASS_ARCHIVE_INTEGRITY',experiment_status=audit['experiment_status'],zip_name=name,zip_path='PH/main_target_v1/PHD-MAIN-TARGET-v1/handover/'+name,
  bytes=dest.stat().st_size,sha256=digest,members_checked=len(members),crc='PASS',member_sha256='PASS',scientific_verdict=None)
 dump(folder/'delivery_receipt_r6.json',receipt);dump(DOC/'delivery_receipt_r6.json',receipt);print(json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
