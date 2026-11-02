"""Seal measured evidence, source references, and bounded reproduction inputs."""
import zipfile,hashlib,re
from common import *
ROOT=OUT/'r8_screen_prune';D=DOC/'screen_prune_r8_lod2'
def read(p):return json.loads(Path(p).read_text())
def main():
 assert read(ROOT/'verification.json')['status']=='PASS_WITH_PRE_RADIUS_NOT_SAVED';assert read(ROOT/'alpha_measure.json')['status']=='VALIDATED_FLOAT32_CPU_REPLAY'
 members={};content={}
 def add(p,name):assert name not in members and name not in content;members[name]=Path(p)
 report=DOC/'화면크기_정리규칙_점검_r8_LoD2.md';add(report,'report/'+report.name)
 for p in D.rglob('*'):
  if p.is_file():add(p,'report/screen_prune_r8_lod2/'+str(p.relative_to(D)))
 for p in CFG.glob('r8_screen*.json'):add(p,'configs/'+p.name)
 for p in Path(__file__).parent.glob('r8_screen*.py'):add(p,'scripts/'+p.name)
 for name in ['common.py','run_cpu.sh','run_pilot_r7.py']:add(Path(__file__).with_name(name),'scripts/'+name)
 for name in ['alpha_raw.npz','alpha_reference.npz','alpha_replay.npz','top1_depth_alpha.npz','alpha_command.json','alpha_export.log','alpha_gpu_receipt.json']:add(ROOT/name,'readout/'+name)
 for p in (OUT/'logs').glob('screen-*.log'):add(p,'execution/'+p.name)
 c=read(CFG/'r8_screen.json')
 for source in c['sources']:
  for name in ['train.py','scene/gaussian_model.py','scene/dataset_readers.py','arguments/__init__.py']:
   p=Path(source['source'])/name
   if p.exists():add(p,'source_reference/'+source['name']+'/'+name)
 for name in ['forward.cu','auxiliary.h','rasterizer_impl.cu','rasterizer_impl.h']:add(OUT/'r8_recorded_continue/runtime/rasterizer/cuda_rasterizer'/name,'source_reference/rasterizer/'+name)
 for name in ['jbgs_target.py','jbgs_target_r6.py','jbgs_target_r7.py']:add(REPO/'src/phd/forks/GeoGS-conf-guided-v1-r22'/name,'source_reference/r22_r8/'+name)
 add(REPO/'src/phd/forks/GeoGS-conf-guided-v1-r15/jbgs_judgment.py','source_reference/baseline_LoD2/jbgs_judgment.py')
 external={}
 for p in CFG.glob('r8_screen*.lock.json'):
  for name,h in read(p).get('files',{}).items():
   if name in external:assert external[name]==h,name
   external[name]=h
 # Snapshot all current analysis scripts after authoring; no model/source mutation.
 analysis={str(p):sha(p) for p in Path(__file__).parent.glob('r8_screen*.py')};dump(ROOT/'analysis_seal.json',dict(at=stamp(),files=analysis,scientific_verdict=None));add(ROOT/'analysis_seal.json','analysis_seal.json')
 dump(ROOT/'external_payloads.json',dict(at=stamp(),files=external,paths='Docker /repo is JointBuildGS-exp; /ph is JointBuildGS-artifacts/phase-payloads/phd; /out is its main_target_v1/PHD-MAIN-TARGET-v1; /cfg is repo configs/phd/main_target_v1.',boundary='Full model/PLY/camera/image inputs remain at locked external paths. Included raw alpha buffers allow CPU compositing replay without model rendering; full scene replay needs those external inputs.',scientific_verdict=None));add(ROOT/'external_payloads.json','external_payloads.json')
 portable=report.read_text();host='/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/docs/experiments/phd/main_target_v1/'
 portable=portable.replace(host,'');content['report/PORTABLE.md']=portable.encode()
 content['README.md']=('''# PHD-MAIN-TARGET-v1 화면 크기 정리 규칙 점검

보고서: `report/PORTABLE.md`. 표·그림·JSON: `report/screen_prune_r8_lod2/`.
학습 없음, 학습 코드 변경 없음, scientific_verdict: null.

확인 범위: 정리 규칙의 실제 소스·실행 인자, 8,000~14,000 직전/직후와 중단 상태,
203장 카메라 거리 및 네 상태의 카메라 30 m 안 수, 상위 1%의 실제 alpha*T 최대 기여.
직전 max_radii2D가 저장되지 않아 역사 반지름의 초과·생존 수는 확인 불가다.
CDGS는 준비 단계 중단으로 학습 결과가 없고, 원래 2DGS 줄은 고정 소스 참조다.

`configs/r8_screen*.lock.json`은 계산 전 잠금, `analysis_seal.json`은 보고서 작성 후 분석 코드 봉인이다.
`source_reference/`는 읽은 원본 소스의 사본이며 고친 학습 코드가 아니다.
`readout/alpha_raw.npz`는 원래 CUDA forward의 정렬 목록·기하 버퍼 일부다.
`alpha_reference.npz`는 원래 전체/선택 무리 RGB·알파, `alpha_replay.npz`는 검증된 CPU 계산이다.
`black_render.json`의 초기 개별 알파 미저장 표시는 후속 `alpha_measure.json`으로 보완했다.

재계산 순서: r8_screen_prepare → measure_r1 → rules → alpha_export/alpha_measure → verify → report.
모든 프로젝트 계산은 기록된 Docker 이미지에서 수행했다. `execution/`과 `readout/alpha_command.json` 참조.
기존 출력에 덮어쓰지 않는다. 전체 재계산은 원본 입력을 읽기 전용으로 연결한 별도 출력 사본이 필요하다.
대형 체크포인트·PLY·이미지는 포함하지 않으며 `external_payloads.json`의 경로/해시로 연결한다.
보고서의 절대 소스 링크는 원래 작업 공간에서 사용할 수 있다. 외부 모델이 없으면 ZIP만으로 전체 학습/렌더를 재현할 수 없다.

SHA256SUMS 및 ZIP CRC는 전달 무결성 검사이며 과학적 결론이 아니다.
''').encode()
 hashes={n:sha(p) for n,p in members.items()};hashes.update({n:hashlib.sha256(v).hexdigest() for n,v in content.items()});at=stamp();suffix=at[5:7]+at[8:10]+'-'+at[11:13]+at[14:16];path=OUT/'handover'/f'PHD-MAIN-TARGET-v1_화면크기점검r8LoD2_{suffix}.zip';assert not path.exists()
 with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for name,p in sorted(members.items()):z.write(p,name)
  for name,data in content.items():z.writestr(name,data)
  z.writestr('MANIFEST.json',json.dumps(dict(at=at,member_sha256=hashes,external_files=len(external),optimization_steps=0,scientific_verdict=None),ensure_ascii=False,indent=2)+'\n');z.writestr('SHA256SUMS',''.join(h+'  '+n+'\n' for n,h in sorted(hashes.items())))
 with zipfile.ZipFile(path) as z:
  assert z.testzip() is None
  for n,h in hashes.items():assert hashlib.sha256(z.read(n)).hexdigest()==h,n
 receipt=dict(at=stamp(),archive=str(path),bytes=path.stat().st_size,sha256=sha(path),checked_members=len(hashes),crc='PASS',member_sha256='PASS',external_files=len(external),optimization_steps=0,scientific_verdict=None)
 dump(ROOT/'delivery.json',receipt);dump(DOC/'delivery_receipt_screen_prune_r8_lod2.json',receipt);print(json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
