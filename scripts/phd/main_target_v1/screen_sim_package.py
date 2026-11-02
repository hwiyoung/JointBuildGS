"""Seal requested compact delivery; keep raw models/meshes in external payload store."""
import datetime,hashlib,json,shutil,subprocess,zipfile
from pathlib import Path
from r8_screen_prepare import R,A,PH,O,C,local,docker,sha,dump
ROOT=O/'screen_sim';DOC=R/'docs/experiments/phd/main_target_v1';DEST=DOC/'screen_sim'
def main():
 verify=json.loads((ROOT/'verification.json').read_text());assert verify['status']=='PASS' and verify['meshes']==40;assert json.loads((DEST/'report_receipt.json').read_text())['status']=='PASS'
 subprocess.run(['python',str(R/'scripts/phd/main_target_v1/screen_sim_regression.py')],check=True)
 immutable={}
 for lock in ['screen_sim.lock.json','screen_sim_inputs.lock.json','screen_sim_inputs.result.lock.json','screen_sim_render.lock.json','screen_sim_render_r2.lock.json','screen_sim_render_r3.lock.json','screen_sim_mesh.lock.json','screen_sim_analysis.lock.json']:
  for p,h in json.loads((C/lock).read_text())['files'].items():
   q=local(p);assert sha(q)==h,('IMMUTABLE_CHANGED',p);immutable[p]=dict(sha256=h,bytes=q.stat().st_size)
 print('IMMUTABLE_VERIFIED',len(immutable),flush=True)
 camera_files={}
 for row in json.loads((DEST/'tables/geogs_camera_binding.json').read_text())['rows']:
  assert row['status']=='PASS_EQUIVALENT_REPRESENTATION'
  for p,h in row['files'].items():
   q=local(p);assert sha(q)==h,('CAMERA_VERIFICATION_INPUT_CHANGED',p)
   camera_files[p]=dict(sha256=h,bytes=q.stat().st_size)
 for name,script in [('screen_sim_cpu_resources.lock.json','screen_sim_cpu_resources.py'),('screen_sim_pipeline.lock.json','screen_sim_pipeline.py')]:
  lock=json.loads((C/name).read_text());assert sha(R/'scripts/phd/main_target_v1'/script)==lock['script_sha256']
 note=DEST/'자원과_실행기록.md';text=note.read_text();text=text.replace('큰 메시·채점 작업은 한 번에 하나다.','큰 TSDF 메시 추출은 한 번에 하나다. 처음에는 추출과 채점도 직렬이었으며, GPU 측정이 끝난 뒤 이미 추출한 메시의 채점 하나를 별도 CPU 컨테이너에서 병행했다. 각각 24 CPU·32 GiB 상한, OMP 6을 사용했다. 추출과 채점은 서로 다른 출력 폴더에 쓴다. 전환 전에 진행 중인 채점은 완료될 때까지 기다렸다.');note.write_text(text)
 camera_note='''

GeoGS 카메라 파일 형식 확인: 최초 잠금은 sparse/0의 이진 카메라 파일을 포함하며, 원 실행의 sparse_lod/0은 텍스트 파일을 읽는다. 두 사전 정보 각각 학습 영상 203장의 자세와 내부 파라미터를 대조한 최대 차이는 모두 0이었다. 이는 수치 동일성 확인이며 파일 바이트 동일성 또는 텍스트 파일의 사전 잠금으로 표시하지 않는다. 실제 텍스트 파일과 대응 이진 파일의 해시는 tables/geogs_camera_binding.json에 있고 전달 직전에 다시 확인했다.
'''
 if camera_note not in note.read_text():note.write_text(note.read_text()+camera_note)
 report=DOC/'화면크기_정리모의.md'
 camera_summary='GeoGS 실제 카메라 입력은 sparse_lod의 텍스트 형식이며 최초 잠금의 이진 형식과 203장 자세·내부 파라미터가 수치상 동일했다(최대 차이 0). 텍스트 파일의 사전 잠금으로 소급 표시하지 않았다. [파일별 대조](screen_sim/tables/geogs_camera_binding.json)와 [실행 기록](screen_sim/자원과_실행기록.md)에 구분해 적었다.'
 if camera_summary not in report.read_text():report.write_text(report.read_text().replace('## 영상 화소와 색 기여',camera_summary+'\n\n## 영상 화소와 색 기여'))
 cfg=json.loads((C/'screen_sim.json').read_text())
 assert subprocess.check_output(['docker','image','inspect','-f','{{.Id}}','jointbuildgs:dev'],text=True).strip()==json.loads((C/'screen_sim_mesh.lock.json').read_text())['image_id']
 for r in cfg['states']:assert subprocess.check_output(['docker','image','inspect','-f','{{.Id}}',r['image']],text=True).strip()==r['image_id']
 stamps=datetime.datetime.now().astimezone();name='PHD-MAIN-TARGET-v1_화면크기정리모의_'+stamps.strftime('%m%d-%H%M');folder=ROOT/'handover'/name;folder.mkdir(parents=True,exist_ok=False)
 shutil.copy2(DOC/'화면크기_정리모의.md',folder/'화면크기_정리모의.md');shutil.copytree(DEST,folder/'screen_sim');shutil.copytree(ROOT/'inputs',folder/'common_masks');shutil.copytree(ROOT/'execution',folder/'execution');shutil.copy2(ROOT/'verification.json',folder/'verification.json');shutil.copy2(ROOT/'cpu_resource_updates.json',folder/'cpu_resource_updates.json')
 (folder/'configs').mkdir();(folder/'scripts').mkdir()
 shutil.copy2(ROOT/'runtime_evidence.json',folder/'runtime_evidence.json')
 shutil.copy2(ROOT/'controller_transition.json',folder/'controller_transition.json')
 for p in C.glob('screen_sim*.json'):shutil.copy2(p,folder/'configs'/p.name)
 for p in (R/'scripts/phd/main_target_v1').glob('screen_sim*'):
  if p.is_file():shutil.copy2(p,folder/'scripts'/p.name)
 for p in [R/'scripts/phd/main_target_v1/common.py',R/'scripts/phd/main_target_v1/r8_screen_prepare.py',R/'scripts/phd/main_target_v1/cause_r8_spatial.py',R/'src/phd/streamed_tsdf.py',R/'src/phd/umap_order.cpp',R/'scripts/phd/main_meshpatch_v1/axes_adapter.py']:shutil.copy2(p,folder/'scripts'/p.name)
 # Renderer hashes were computed when these immutable cached frames entered TSDF.
 known={}
 for p in (ROOT/'meshes').glob('*/*/inputs/binding.json'):known.update(json.loads(p.read_text())['inputs'])
 for p in (ROOT/'scores').glob('*/*/*/values.json'):
  z=json.loads(p.read_text());known['/target/screen_sim/meshes/'+z['state']+'/'+z['variant']+'/merged.ply']=z['mesh_sha256']
 selected=[]
 for p in (ROOT/'states').rglob('*'):
  if p.is_file() and 'account_build' not in p.parts:selected.append(p)
 for pattern in ['*/*/merged.ply','*/*/merged.json','*/*/inputs/binding.json','*/*/inputs/meta.json','*/*/plan/plan.json']:
  selected+=list((ROOT/'meshes').glob(pattern))
 selected += [p for p in (ROOT/'scores').rglob('*') if p.is_file()]
 external=[]
 for i,p in enumerate(sorted(set(selected))):
  dp='/target/'+str(p.relative_to(O));external.append(dict(path=docker(p),bytes=p.stat().st_size,sha256=known.get(dp) or sha(p),hash_origin='producer read/score receipt' if dp in known else 'delivery read'))
  if i%1000==0:print('EXTERNAL_MANIFEST',i,len(selected),flush=True)
 dump(folder/'immutable_inputs.json',dict(verified_at=stamps.isoformat(),files=immutable,scientific_verdict=None));dump(folder/'external_payloads.json',dict(files=external,excluded='Regenerable TSDF tiles, unit order and temporary build products; requested raw arrays, frame renders, final current meshes and scoring distances retained externally',scientific_verdict=None))
 dump(folder/'camera_verification_inputs.json',dict(verified_at=stamps.isoformat(),files=camera_files,note='Post-render numerical equivalence and delivery-time byte verification; not a retrospective pre-calculation lock of sparse_lod text files.',scientific_verdict=None))
 (folder/'README.md').write_text('''# 화면 크기 정리 모의 전달

화면크기_정리모의.md에서 시작한다. screen_sim/에 표(md/json/csv), 그림(png/pdf/json), 미적용 패치가 있다. common_masks/는 203장에 공통인 평가 화소다. configs/는 계산 전 잠금과 읽기 도구 수정 기록이다. execution/은 실제 Docker 명령과 실패·완료 로그다.

학습·역전파·최적화는 실행하지 않았다. 패치의 문턱은 비어 있고 원 학습 소스에 적용하지 않았다. scientific_verdict: null.

재계산 경계: immutable_inputs.json의 원 모델·원본 영상/MVS·카메라·소스와 잠긴 Docker 이미지가 필요하다. /repo는 JointBuildGS-exp, /ph는 형제 JointBuildGS-artifacts/phase-payloads/phd, /out(렌더)/target(CPU 채점)은 main_target_v1/PHD-MAIN-TARGET-v1이다. external_payloads.json에 203장별 반지름, 가우시안별 최대/최대 영상/색 기여/자리, 네 삭제 마스크, 전체 렌더, 현재 메시, 채점 거리의 위치·크기·SHA가 있다. 모델과 메시 전체를 ZIP에 복제하지 않았다. 드라이버 출력 경로는 고정되어 있으므로 원본을 보존한 별도 작업공간 복제본에서 screen_sim 출력이 없는 상태로 전체 재계산한다. 기존 결과를 삭제하거나 덮어쓰지 않는다. 완료 상태는 다시 계산하지 않고 무결성 확인·표 재집계에 사용할 수 있다.

계산 순서: screen_sim_prepare → screen_sim_inputs → screen_sim_launch (GeoGS는 r3) → screen_sim_cpu_queue → screen_sim_tables → screen_sim_verify → screen_sim_figure_labels → screen_sim_report → screen_sim_package. 모든 프로젝트 Python 의존성은 기록된 Docker 명령에서 실행한다. 패치 생성·무결성·ZIP 작업은 host 표준 라이브러리만 쓴다.

SHA256SUMS는 ZIP 내부 파일의 바이트 무결성 목록이다. 과학적 타당성 또는 문턱 선택을 승인하는 자료가 아니다.
''')
 paths=sorted(p for p in folder.rglob('*') if p.is_file());sums={str(p.relative_to(folder)):sha(p) for p in paths};(folder/'SHA256SUMS').write_text(''.join(h+'  '+p+'\n' for p,h in sums.items()));zp=O/'handover'/(name+'.zip');assert not zp.exists()
 with zipfile.ZipFile(zp,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
  for p in sorted(folder.rglob('*')):
   if p.is_file():z.write(p,p.relative_to(folder))
 with zipfile.ZipFile(zp) as z:
  assert z.testzip() is None
  for p,h in sums.items():assert hashlib.sha256(z.read(p)).hexdigest()==h,p
 receipt=dict(at=datetime.datetime.now().astimezone().isoformat(),zip=str(zp),bytes=zp.stat().st_size,sha256=sha(zp),CRC='PASS',internal_sha256_files=len(sums),internal_SHA256='PASS',immutable_inputs_verified=len(immutable),external_payload_files=len(external),training=False,scientific_verdict=None);dump(ROOT/'handover_receipt.json',receipt);dump(DEST/'handover_receipt.json',receipt);dump(zp.with_suffix('.receipt.json'),receipt);print(json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
