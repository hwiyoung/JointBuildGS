"""Run final verification before writing the factual report."""
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from lock_config import dump,sha,stamp
S=Path(__file__).parent;O=Path('/out');D=Path('/docs');C=Path('/cfg')
assert (O/'montage_complete.json').exists()
for name in ['supplement_tables.py','validate_final.py','report.py']:
    print('START',name,flush=True);subprocess.run([sys.executable,'-B','-u',str(S/name)],check=True)
report=D/'판단숫자셈_보고_v1.md';text=report.read_text()
assert len(text)<20000
for word in ['판정','견주다','재다','언저리','가르다','갈래','가져온다','계승','새로움','우리','꼴','층']:
    assert word not in text,word
for link in re.findall(r'\]\(([^)]+)\)',text):assert (D/link).exists(),link
versions={'python':platform.python_version()}
for name in ['numpy','scipy','matplotlib','Pillow','shapely','opencv-python']:
    try:versions[name]=importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:versions[name]='not reported by distribution metadata'
runtime={'at':stamp(),'commit':os.environ.get('JUDGENUM_COMMIT'),'container_image':os.environ.get('JUDGENUM_IMAGE'),
  'versions':versions,'nice':os.getpriority(os.PRIO_PROCESS,0),'CUDA_VISIBLE_DEVICES':os.environ.get('CUDA_VISIBLE_DEVICES'),
  'gpu_devices_present':list(map(str,Path('/dev').glob('nvidia*'))),'cgroup_memory_max':Path('/sys/fs/cgroup/memory.max').read_text().strip(),
  'source_sha256':{p.name:sha(p) for p in S.iterdir() if p.is_file()},'scientific_verdict':None}
assert runtime['nice']==19 and not runtime['gpu_devices_present'] and runtime['CUDA_VISIBLE_DEVICES']==''
dump(D/'tables/runtime_receipt.json',runtime)
(D/'progress.md').write_text('# PHD-MAIN-JUDGENUM-v1 진행\n\n'+f'- 갱신: {stamp()}\n'+
  '- 단계 가: 완료, 중간 보고 커밋 52e91da1 및 푸시 완료\n'+
  '- 단계 나: 최소 넓이, 135개 조합, 두 기준선, 건물 동일 비중·한 동 제외 계산 완료\n'+
  '- 단계 다: 민감도 5개, 그림 8.1~8.7, 확인용 적용·봉인 완료\n'+
  '- 0.5 m 사진 작업 이름 충돌: 앞 결과 보존, 재계산 및 넓이 보존 검증 완료\n'+
  '- 독립 검증: 전체 기본 코어, 후보 합계·선택, A, 공개 범위, 입력 잠금, PNG 검증 PASS\n'+
  '- 확인 불가: 원자료 법선/σp, 항공 LiDAR 법선 25배 규칙, 혼합 덩어리의 서로 다른 A 처리\n'+
  '- 전달 구성: light/full ZIP, scripts와 설정 및 표·그림 포함, 확인용 제외; 외부 페이로드 delivery_receipt.json에 CRC·SHA-256 기록\n'+
  '- 최종 보고: 판단숫자셈_보고_v1.md (20,000자 미만)\n- scientific_verdict: null\n')
dump(O/'ready_for_handover.json',{'at':stamp(),'status':'VERIFIED_WITH_RECORDED_UNAVAILABLE_INPUTS','report_sha256':sha(report),'characters':len(text),'scientific_verdict':None})
print('READY_FOR_HANDOVER',len(text),flush=True)
