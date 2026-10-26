"""Record exact replay dependencies and completed execution receipts, CPU only."""
from rfcore import *
import importlib.metadata as metadata
import platform
import os
import subprocess


def main():
    repo = Path('/repo')
    paths = [repo/'scripts/phd/main_regionfig_v1/common.py',
             repo/'scripts/phd/main_regionfig_v1/prepare.py',
             repo/'configs/phd/main_regionfig_v1/regionfig_v1.json',
             V1/'prepared.json', W/'image_split.json',
             W/'mvs/full/sparse/cameras.bin', W/'mvs/full/sparse/images.bin',
             DENSE/'triangulated/cameras.bin', DENSE/'triangulated/images.bin']
    cfg = load(CFG/'regionfig_v2.json')
    completed = []
    for path in sorted((PAY/'logs').glob('*.json')):
        item = load(path)
        if item.get('finished_at'):
            completed.append(dict(file=path.name, sha256=sha(path), receipt=item))
    head = os.environ['JBGS_SOURCE_HEAD']
    assert len(head) == 40 and all(c in '0123456789abcdef' for c in head)
    record = dict(task_id='PHD-MAIN-REGIONFIG-v2', at=now(), source_base_head=head,
                  python=platform.python_version(),
                  process_priority=dict(nice=os.getpriority(os.PRIO_PROCESS,0),
                    io=subprocess.check_output(['ionice','-p',str(os.getpid())],text=True).strip()),
                  versions={n: metadata.version(n) for n in ['numpy', 'scipy', 'Pillow', 'matplotlib']},
                  dependencies=[dict(path=str(p), bytes=p.stat().st_size, sha256=sha(p)) for p in paths],
                  input_receipt=load(PAY/'input_receipt.json'),
                  joined_sources={k:load(PAY/f'join_{k}.json') for k in ['ALS','LoD2']},
                  completed_execution_receipts=completed,
                  final_blind_images={i:sha(DOC/f'figures/검토용_{i}_제목숨김.png') for i in ['5','6']},
                  scientific_verdict=None)
    dump(DOC/'tables/provenance.json', record)
    for path in sorted((repo/'scripts/phd/main_regionfig_v2').glob('*.py')):
        compile(path.read_text(), str(path), 'exec')
    readme = f'''# 영역 표본 그림 v2 재현 기록

이 작업은 제공된 손실 최소점 결과와 사진 검사값을 표시한다. 학습, 새 최적화, 새 사진 검사를 실행하지 않는다. 과학적 판정은 `null`이다.

## 입력과 실행 환경

- 실행 당시 저장소 기준 커밋: `{head}`. 이 작업의 최종 커밋과 원격 확인은 외부 작업 폴더의 `delivery_receipt.json`에 별도로 기록한다.
- 이미지: `jointbuildgs:dev`. 실제 이미지 ID와 실행마다의 전체 Docker 명령은 `tables/provenance.json`의 완료 영수증에 있다.
- Python {record['python']}; 라이브러리 버전과 이전 코드·설정·카메라 파일 해시는 같은 파일에 있다.
- `/repo`는 이 저장소, `/art`는 형제 폴더 `JointBuildGS-artifacts`다.
- `/payload`는 `JointBuildGS-artifacts/phase-payloads/phd/main_regionfig_v2/PHD-MAIN-REGIONFIG-v2`다.
- `/cfg`, `/docs`는 이 작업의 설정과 문서 폴더다. 이 세 출력만 쓰기 가능하게 연결했다.
- 원본 사진: `/art/phase-payloads/p0-audit/data/raw/uav/Images.zip`. 그림별 원본 JPEG 이름과 바이트 해시는 각 그림의 숫자 파일에 있다. 전체 대형 사진 묶음은 다시 해시하지 않았다.
- 원본 카메라: `/art/phase-payloads/p0-audit/data/work/mvs/triangulated/`.
- 사진 소속·보정 카메라: `/art/phase-payloads/phd/main_widen0_v2/PHD-MAIN-WIDEN0-v2/image_split.json`, `mvs/full/sparse/`.
- 제공값: `/payload/input/ALS_sites.npz`, `LoD2_sites.npz`, `sites_summary.json`. 원본 묶음과 세 파일의 해시는 입력 영수증에 있다.
- 패치 연결은 넓히기 v2의 공개 패치 파일에서 같은 번호의 중심·법선만 얻는다. 파일별 해시와 선택한 건물은 연결 영수증에 있다. 확인용 19동을 읽지 않았다.
- 좌표: EPSG:25832에서 `[690953, 5336071, 604] m`를 뺀 모델 좌표. 북쪽은 양의 y다.

## 잠금과 순서

설정은 첫 그림 전에 잠갔다. 원래 해시 `{sha(CFG/'regionfig_v2.json')}`를 유지한다. 표시 수정은 `amendment_01_projection*`, `amendment_02_legends*`에 따로 시각과 해시를 남겼다. 수정 전 결과는 외부 `revision_01/`에 보존했다.

처음 실행한 순서는 입력 확인 → 패치 연결 → 사진·자른 상자 잠금 → 그림 → 투영 유효 범위 보완 → 독립 점검 → 범례 보완 → 최종 그림 → 독립 수치 검증 → 보고서·전달 묶음이다. 실행별 명령·시각·실패·자원 조건은 완료 영수증에 있다. `prepare_figures.py`는 잠금이 있으면 중단하므로 현재 잠금을 지워서 다시 고르지 않는다.

현재 잠긴 자료의 재검증 명령은 저장소 루트에서 다음과 같다. 호스트 런처는 표준 라이브러리만 사용하며 실제 검증은 제한된 Docker 안에서 실행한다.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/phd/main_regionfig_v2/run_cpu.py verify python verify.py
```

그림을 다시 만들 필요가 있을 때만 같은 런처로 `python draw_figures.py 1`부터 `8`까지 한 장씩 실행한다. 현재 설정·원본·연결값·단면 파일이 모두 필요하다. 기존 그림 파일은 덮어쓰므로 이번 전달본을 별도로 보존해야 한다. 전달 ZIP은 검토용 묶음이며 대형 원본 사진·공개 패치·연결 배열까지 포함하는 완전 독립 실행 환경은 아니다.

## 전달과 검증

전달 파일은 그림별 8개다. 모두 같은 폴더에 풀면 보고서의 여덟 그림 링크가 연결된다. 중복된 공통 파일은 바이트가 같다. `SHA256SUMS`는 전체 전달 파일 목록이며 여덟 파일을 모두 푼 뒤 `sha256sum -c SHA256SUMS`로 확인할 수 있다. 각 ZIP 자체의 크기·전체 해시·CRC·멤버 해시 검사는 외부 `handover/package_receipt.json`에 기록한다.

그림 수치 검증은 `tables/verification.json`의 192개 검사를 통과했다. 원본 사진 화소, 실제 보정 시야, 동일한 사진 캔버스, 제공 입력으로 따로 합산한 넓이 비율, 독립 단면 구간·중앙값 확인을 포함한다. 사진·수치 검증은 과학적 판정과 다르다. 처음 보는 사람 점검의 전체 답과 보완 전 그림도 함께 제공한다.

## 자원 조건

사용자의 “응 그래보자” 승인으로 시작 기준을 24 GiB로 바꿨다. 컨테이너 메모리 상한 4 GiB, 추가 스왑 없음, 프로세서 2개, GPU 없음, 낮은 우선순위, 한 번에 한 장이다. 호스트 여유 16 GiB 미만이나 큰 후처리 시작이 확인되면 이번 실행의 고유 컨테이너만 중단하도록 했다. 다른 작업의 잠금은 읽기 전용으로 잠깐 확인하고 즉시 해제했다. 다른 작업을 중단하지 않았다.
'''
    (DOC/'재현기록.md').write_text(readme)
    print('PROVENANCE', len(completed), 'receipts; script syntax PASS')


if __name__ == '__main__':
    main()
