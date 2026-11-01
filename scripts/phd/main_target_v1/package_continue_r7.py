"""Seal verified continuation evidence and explicit unavailable rows, never raw holdout details."""
import hashlib,zipfile
from common import *
from package_r7 import stable_bytes

def main():
 audit=json.loads((DOC/'tables/final_audit_continue_r7.json').read_text());assert audit['status']=='PASS_CONTINUATION_DELIVERY_AUDIT';members={};external={};root=OUT/'r7_continue'
 for folder,prefix in [(CFG,'configs/phd/main_target_v1'),(Path(__file__).parent,'scripts/phd/main_target_v1'),(DOC,'docs/experiments/phd/main_target_v1')]:
  for p in sorted(folder.rglob('*')):
   if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ['.pyc','.zip'] and not p.name.startswith('delivery_receipt'):members[prefix+'/'+p.relative_to(folder).as_posix()]=stable_bytes(p)
 for p in sorted(root.rglob('*')):
  if not p.is_file() or p.suffix not in ['.json','.jsonl','.log','.diff'] or '/renders/' in str(p) or '/render/' in str(p) or '/inputs/' in str(p) or '/dist/' in str(p):continue
  members['payload/r7_continue/'+p.relative_to(root).as_posix()]=stable_bytes(p)
 cfg=json.loads((CFG/'scoring_continue_r7.r1.json').read_text());paths=set()
 for r in cfg['rows']:
  model=Path(r['model']);paths.add(model/f"point_cloud/iteration_{r['iteration']}/point_cloud.ply");paths.add(Path(r['current_mesh']));paths.add(root/'meshes'/r['key']/'final.ply')
  paths.update([model/f"jbgs_complete/iteration_{r['iteration']}/checkpoint.pth",model/f"target_monitor/snapshot_{r['iteration']}.npz"])
 for p in root.glob('scoring/*/*/dist/*.npz'):paths.add(p)
 for p in root.glob('scoring/*/*/patch_z.npz'):paths.add(p)
 for p in sorted(paths):
  if p.exists():external[str(p).replace('/art/phase-payloads/phd/','PH/').replace('/ph/','PH/').replace('/out/','PH/main_target_v1/PHD-MAIN-TARGET-v1/')]=dict(bytes=p.stat().st_size,sha256=sha(p))
 # Compact experiment-only numeric evidence. No sealed buildings enter this directory.
 for name in ['counterfactual_gaussians.npz','r6_floating_cross.npz','r7_floating_cross.npz']:
  p=root/'diagnostics/ALS'/name;members['payload/r7_continue/diagnostics/ALS/'+name]=stable_bytes(p)
 for p in sorted((root/'diagnostics/ALS/full_pixel_enumeration_r1').glob('*.npz')):members['payload/r7_continue/diagnostics/ALS/full_pixel_enumeration_r1/'+p.name]=stable_bytes(p)
 assert not any('/holdout/' in n for n in members)
 manifest=dict(at=stamp(),task_id='PHD-MAIN-TARGET-v1',revision='r7 continuation',status=audit['training_status'],mesh_scores_complete=audit['mesh_scores_complete'],mesh_scores_unavailable=audit['mesh_scores_unavailable'],other_six='NOT_STARTED',scientific_verdict=None,members=[dict(path=n,bytes=len(v),sha256=hashlib.sha256(v).hexdigest()) for n,v in members.items()],external_payloads=external,holdout_patch_details_included=False,recomputation_boundary='The ZIP contains code/configuration/reports/figures and compact numeric evidence. Large models, meshes and per-point distance arrays stay at the manifest paths. Original S0/S1/UNCERT inputs, frozen r21 fork, inherited AXES71-v2 source, original cleanup and Docker images are required; their hashes are in included locks. This is not a self-contained data backup. CRC and SHA checks do not establish a scientific verdict.')
 name='PHD-MAIN-TARGET-v1_이어학습점검r7_'+dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%m%d-%H%M')+'.zip';dest=OUT/'handover'/name;assert not dest.exists()
 with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for n,b in members.items():z.writestr(n,b)
  z.writestr('MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');z.writestr('SHA256SUMS',''.join(f'{m["sha256"]}  {m["path"]}\n' for m in manifest['members']))
  z.writestr('README.txt','PHD-MAIN-TARGET-v1 r7 이어 학습 점검 [이 발주에서 냄]\n최신 보고: docs/experiments/phd/main_target_v1/이어학습과채점_r7.md\n항공 LiDAR 진단: docs/experiments/phd/main_target_v1/항공LiDAR_r7_원인점검.md\n상태: '+audit['training_status']+'\n채점 완료 '+str(audit['mesh_scores_complete'])+'건, 저장 모델 없음 '+str(audit['mesh_scores_unavailable'])+'건. 나머지 여섯 판 미시작.\n지금 채점 메시와 최종 메시를 따로 채점. 참값 열두 칸·두 축·덩어리의 원래 정의 유지. 기존 AXES71-v2 참고 줄은 원래 가시/비가시 메시 규칙을 유지함.\n항공 LiDAR 뜬 면 화소 진단은 full_pixel_enumeration_r1을 사용. 원본 ALS 경사 패치 접선으로 복원한 면적이며, 이전 정사각형 119화소 계산은 대체된 이력으로 보존.\n확인용 패치 상세와 큰 모델/메시는 제외. 외부 원본 없이는 완전 재계산 불가. CRC/SHA-256은 무결성만 검증. scientific_verdict: null.\n')
 with zipfile.ZipFile(dest) as z:
  assert z.testzip() is None
  for m in manifest['members']:assert hashlib.sha256(z.read(m['path'])).hexdigest()==m['sha256']
 h=sha(dest);dest.with_suffix('.zip.sha256').write_text(h+'  '+name+'\n');receipt=dict(at=stamp(),status='PASS_ARCHIVE_INTEGRITY',zip_name=name,zip_path='PH/main_target_v1/PHD-MAIN-TARGET-v1/handover/'+name,bytes=dest.stat().st_size,sha256=h,members_checked=len(members),external_payloads=len(external),crc='PASS',member_sha256='PASS',mesh_scores_complete=audit['mesh_scores_complete'],mesh_scores_unavailable=audit['mesh_scores_unavailable'],training_status=audit['training_status'],scientific_verdict=None);dump(OUT/'handover/delivery_receipt_continue_r7.json',receipt);dump(DOC/'delivery_receipt_continue_r7.json',receipt);print(json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
