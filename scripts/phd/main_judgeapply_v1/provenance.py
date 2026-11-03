"""Record copied bytes, adapter source ranges, software and deliverable lineage."""
from common import *
import ast,platform,importlib.metadata
def main():
    copies=json.loads((C/'source_copy_manifest.json').read_text())+json.loads((C/'source_copy_additions.json').read_text())
    for row in copies:
        assert sha(R/row['source'])==row['sha256']==sha(R/row['copy']),row['source']
    adapters=[]
    for p in sorted(HERE.glob('*.py')):
        tree=ast.parse(p.read_text());functions=[dict(name=n.name,start=n.lineno,end=n.end_lineno) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
        adapters.append(dict(path=str(p.relative_to(R)),sha256=sha(p),new_lines=[1,len(p.read_text().splitlines())],functions=functions))
    dump(D/'source_changes.json',dict(at=now(),copied_files=copies,adapters=adapters,scientific_verdict=None))
    lines=['# 상속 파일과 적용 줄','', '상속 파일 24개는 원본과 SHA256이 같다. 원본 파일을 고치지 않고 아래 새 어댑터에서 입력 위치와 발주 변경을 적용했다. 정확한 함수별 줄·SHA256은 source_changes.json에 있다.', '', '| 새 파일 | 적용 범위 |','| --- | --- |']
    notes={'geometry_run.py':'지역 in_eval·source_index 연결, 지붕10m/벽5m 선택, 원본 불확실성 유지, LiDAR 법선/높이 상속',
      'calibrate.py':'참값 없이 지역 r, 10동 ALS 잔차 NMAD σ_W 및 기존 L 식',
      'photo_prepare.py':'기존 kind+point_id 연결 및 같은 2×2 규칙 생성; column의 H만 벽5m, 사전 높이 hp+r, 높이 배열 [0.], 자른 mask',
      'score.py':'상속 score AST의 mode 루프만 range(1); single height, 원본 JPEG4GiB/float64 그대로',
      'cameras.py':'지역 train split과 원본 JPEG·카메라로 입력 어댑트; 기존 projection 상속',
      'sight.py':'TARGET r7 지역 시선 검사 상속; 5m/10m 결측 합집합만 계산',
      'judgments.py':'지역·종류별 q05/q10, 기존 사진 판단 순서, 6방식 및 TARGET 번호 두 목표',
      'truth.py':'판단 저장 뒤 지역 τ로 평가; ALS 새 법선 축에서 기존 참값 규칙',
      'ring_missing.py':'누락만 원래 법선·같은 지역 RNG·1.5m 링 재계산',
      'tables.py':'칸1+2 공통분모, 영역9 미판정 별도, 6.3/6.4 집계',
      'figures.py':'상속 background/rgb, 지역mesh만 연결; 3×5 및 행PNG, 발주 색과 영역9 빗금',
      'verify_once.py':'저장 핵심점의 독립 교차집계로 표7.1/6.3 한 번 검산'}
    for a in adapters:
        name=Path(a['path']).name
        lines.append(f'| {name}:1–{a["new_lines"][1]} | {notes.get(name,"지역 실행·기록·전달 보조; 원본 상속 파일 변경 없음")} |')
    lines+=['','그룹 함수 AST에서 개발용 타일의 전체 면 원점 파일을 지역 전체 면 파일로 연결했다. 점 배치식은 바꾸지 않았다. 사진 점수 AST는 자르지 않은 판의 루프만 제거했다. 입력 연결 함수 추출은 원본 모듈의 부수적인 파일 읽기·쓰기를 실행하지 않도록 한다.',
      '', '결합: `scripts/phd/main_baselines_v1/mvsfuse/detect.py:315–353,355–364,725–732,770–772`; 문턱 정의 `mf_common.py:56–101`. 색 차이 25의 저장된 `in_change_25`를 그대로 사용한다. 지역별 정확한 경로·SHA256·전체 문턱은 `tables/*_fusion_sources.json`에 있다.',
      '', 'r8 패치: `scripts/phd/main_target_v1/prepare_inputs_r8.py:41`에서 r7 target을 복사한다. 이번 입력은 동일 source_index·centre·in_eval에 대응하는 단계0 패치다. B0와 R1은 별도 r8 targets가 없으므로 그 교차만 확인 불가다.',
      '', '후속 학습은 수행하지 않았다. 설정 초기/최종 두 잠금 사이 스크립트 수정은 progress.md에 남겼다. scientific_verdict: null','']
    (D/'source_changes.md').write_text('\n'.join(lines))
    versions={}
    for name in ['numpy','scipy','torch','open3d','matplotlib','opencv-python']:
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]='확인 불가: package metadata 없음'
    dump(D/'runtime_environment.json',dict(at=now(),python=platform.python_version(),packages=versions,image=os.environ['JUDGEAPPLY_IMAGE'],commit=os.environ['JUDGEAPPLY_COMMIT'],crs='EPSG:25832; original regional coordinate frames and registered shifts',GPU='device 1; float64 photo arithmetic only; wait 0',CPU='nice 19; each container <=32 GiB; 4 CPUs',scientific_verdict=None))
    print('PROVENANCE_COMPLETE',len(copies),len(adapters),flush=True)
if __name__=='__main__':main()
