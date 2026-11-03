"""Seal stage 1–3 only after evidence verification; original models stay external."""
import datetime,hashlib,shutil,zipfile,subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from r8_screen_prepare import R,A,PH,O,C,j,sha,dump,local
ROOT=O/'rfix';DOC=R/'docs/experiments/phd/main_target_v1';DEST=DOC/'rfix'

def main():
 validation=j(DEST/'validation.json');assert validation['status']=='PASS_EVIDENCE_CONSISTENCY'
 status=j(DEST/'report_status.json');assert status['status']=='STOP_GRADIENT_PARITY' and not status['training_started']
 # Read every previously locked original input again. No inferred immutability.
 locked=j(C/'rfix.lock.json')['files'];items=list(locked.items())
 def check(item):
  path,expected=item;p=local(path);actual=sha(p);assert actual==expected,(path,expected,actual);return dict(path=str(p),bytes=p.stat().st_size,sha256=actual)
 with ThreadPoolExecutor(max_workers=4) as pool:original=list(pool.map(check,items))
 immutable=dict(at=datetime.datetime.now().astimezone().isoformat(),status='PASS',files=len(original),original_inputs=original,scientific_verdict=None);dump(ROOT/'immutable_final.json',immutable)
 name='PHD-MAIN-TARGET-v1_렌더러상자고침_'+datetime.datetime.now().astimezone().strftime('%m%d-%H%M');folder=ROOT/'handover'/name;folder.mkdir(parents=True,exist_ok=False)
 def copy(p,rel):
  target=folder/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
 copy(DOC/'렌더러_화면상자_고침.md',Path('docs/렌더러_화면상자_고침.md'))
 for p in sorted(DEST.rglob('*')):
  if p.is_file() and p.name not in ['delivery_receipt.json','git_receipt.json']:copy(p,Path('docs/rfix')/p.relative_to(DEST))
 for p in sorted(C.glob('rfix*.json')):copy(p,Path('configs/phd/main_target_v1')/p.name)
 scripts=R/'scripts/phd/main_target_v1'
 for p in sorted(scripts.glob('rfix*')):
  if p.is_file():copy(p,Path('scripts/phd/main_target_v1')/p.name)
 for name2 in ['common.py','r8_screen_prepare.py','screen_sim_render_r3.py','screen_sim_render.py','r8_record_prepare.py','run_cpu.sh']:
  p=scripts/name2
  if p.exists():copy(p,Path('scripts/phd/main_target_v1')/p.name)
 included=set();external=[]
 for p in sorted(ROOT.rglob('*')):
  if not p.is_file() or 'handover' in p.relative_to(ROOT).parts:continue
  rel=p.relative_to(ROOT)
  compact=p.suffix in ['.json','.log','.txt','.patch']
  source=('source' in rel.parts and p.suffix in ['.cu','.cuh','.h','.hpp','.cpp','.py','.md']) or p.name in ['LICENSE','LICENSE.md','LICENSE.txt']
  if compact or source:
   copy(p,Path('evidence')/rel);included.add(str(p))
  elif p.suffix in ['.npz','.so','.npy','.ply','.pth']:
   external.append(dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p),role='rfix raw measurement or separate binary'))
 for label in ['target','imageonly','geogs']:
  copy(ROOT/'builds'/label/'renderer.patch',Path('renderer_patches')/(label+'.patch'))
 copy(ROOT/'cdgs_prepared/renderer.patch',Path('renderer_patches/CDGS_unapplied.patch'))
 dump(folder/'external_payloads.json',dict(original_inputs=original,derived_payloads=external,recompute_boundary='Full replay needs external frozen images/models/targets and Docker images; this ZIP contains compact evidence and scripts, not original scientific payloads.',scientific_verdict=None))
 (folder/'README.md').write_text('''# 렌더러 화면 상자 고침 1~3단계

기술 상태: **STOP_GRADIENT_PARITY**. 요청한 저장 상태 비교를 완료했지만 기울기가 원본 두 번의 차 안에 든다는 조건을 충족하지 못했습니다. 이어 학습과 나머지 여섯 판을 시작하지 않았습니다.

- [보고서](docs/렌더러_화면상자_고침.md)
- [상태별 표](docs/rfix/tables/state_summary.md)
- [자료 일관성 점검](docs/rfix/validation.json)
- [기존 메시 출처](docs/rfix/기존메시_출처.md)
- 잠금: `configs/phd/main_target_v1/rfix.json`과 관련 lock 파일
- 렌더러 차이: `renderer_patches/` (원본 소스 및 설치 바이너리 보존)
- 큰 원시 자료: `external_payloads.json`의 경로·크기·SHA256
- 내부 무결성: `SHA256SUMS`

ZIP은 원본 모델과 영상 전체를 포함하지 않습니다. 재계산에는 외부 자료와 잠긴 Docker 이미지가 필요합니다. 전달물 해시 검증과 수치 통과 판정은 별개입니다. `scientific_verdict: null`.
''')
 manifest=[]
 for p in sorted(folder.rglob('*')):
  if p.is_file():manifest.append((p.relative_to(folder).as_posix(),sha(p)))
 (folder/'SHA256SUMS').write_text(''.join(h+'  '+rel+'\n' for rel,h in manifest))
 handover=O/'handover';handover.mkdir(exist_ok=True);archive=handover/(name+'.zip');assert not archive.exists()
 with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in sorted(folder.rglob('*')):
   if p.is_file():z.write(p,p.relative_to(folder).as_posix())
 with zipfile.ZipFile(archive) as z:
  assert z.testzip() is None
  for rel,h in manifest:assert hashlib.sha256(z.read(rel)).hexdigest()==h,rel
 receipt=dict(at=datetime.datetime.now().astimezone().isoformat(),status='SEALED',archive=str(archive),bytes=archive.stat().st_size,sha256=sha(archive),crc='PASS',internal_sha256_files=len(manifest),internal_sha256='PASS',immutable_original_files=len(original),immutable_original_sha256='PASS',external_derived_files=len(external),measurement_status='COMPLETE_STAGE_1_TO_3',acceptance_status='STOP_GRADIENT_PARITY',training_started=False,scientific_verdict=None)
 dump(DEST/'delivery_receipt.json',receipt);dump(ROOT/'delivery_receipt.json',receipt);print(receipt,flush=True)

if __name__=='__main__':main()
