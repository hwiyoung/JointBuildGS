"""Build first requested delivery, including its failed gate and replay boundary."""
import hashlib
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from input_audit import sha
from prepare_places import save
from verify_stage1_bundle import verify


def main():
    repo, out = Path('/repo'), Path('/out')
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    dest = out / 'delivery' / ('PHD-MAIN-CANDPICK-v1_자리표_' + now.strftime('%m%d-%H%M') + '.zip')
    dest.parent.mkdir(exist_ok=True)
    assert not dest.exists(), dest
    files = {}
    for rel in ['scripts/phd/main_candpick_v1', 'configs/phd/main_candpick_v1', 'docs/experiments/phd/main_candpick_v1']:
        for p in sorted((repo / rel).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and 'delivery' not in p.parts:
                files[str(p.relative_to(repo))] = p
    p = repo / 'tests/phd/test_main_candpick_v1.py'; files[str(p.relative_to(repo))] = p
    for folder in ['places', 'validation', 'occlusion', 'logs']:
        for p in sorted((out / folder).rglob('*')):
            if p.is_file(): files['payload/' + str(p.relative_to(out))] = p
    for p in sorted((out / 'preflight').glob('*_all_views/*')):
        if p.is_file(): files['payload/' + str(p.relative_to(out))] = p
    scene_names = ['candidate_geometry.npz', 'initial_right_candidate.npz', 'candidate_color.npy',
                   'candidate_color_sample_count.npy', 'cleanup_masks.npz', 'scene.json', 'support_metadata_correction.json']
    for unit in ['B173_ALS', 'R1_LoD2', 'B173_LoD2', 'R1_ALS']:
        for name in scene_names:
            p = out / 'scenes' / unit / name
            if p.exists(): files['payload/' + str(p.relative_to(out))] = p
    note = '''# PHD-MAIN-CANDPICK-v1 1차 자리표 묶음

학습 전 자료다. 13,849점을 잠그고 장면 정리·가림 기록을 완료했다. 50cm 시험 칸 밖 동일성 실패로 학습은 0/24판이다. scientific_verdict: null.

먼저 docs/experiments/phd/main_candpick_v1/README.md와 stage1_report.md를 읽는다. 표 원본·점 목록·기울기 검사·전체 뷰의 동일성 검사·가림 분자/분모·실패 로그를 포함했다. preflight PNG의 outside_changes는 회색=시험 칸, 빨강=칸 밖 변화다. 검정은 해당 표시 없음이며 사진의 검정 물체를 뜻하지 않는다.

## 무결성과 재계산

MANIFEST.json은 자신을 제외한 모든 파일의 크기와 SHA-256을 기록한다. ZIP CRC와 파일 해시, 보기 값/1단계 값의 표 96행, 가림 13,849점의 비율을 함께 검사한다. 폴더를 푼 뒤 아래 도구를 같은 ZIP 파일에 실행한다. NumPy가 있는 jointbuildgs:dev Docker 환경을 사용한다.

    python scripts/phd/main_candpick_v1/verify_stage1_bundle.py /path/to/this.zip

잠근 places_v1.json의 해시는 그대로 유지한다. payload/validation의 judgment는 원본 15열, payload/places의 judgment는 보기 값 1열이다. 0부터 4번 열은 δ=0.10·최소 점수 0.3이고, 0번 열은 δ=0.05·최소 점수 0이다. 후자는 표에만 사용한다.

## 재현 범위

이 ZIP만으로 표와 가림 비율 집계, 삭제 마스크의 개수를 검산할 수 있다. 픽셀 가림 계산과 렌더를 다시 하려면 input_audit_v1.json·places_v1.json·scenes/*.json이 지정한 외부 원본, 저장소의 상속 코드, jointbuildgs:dev 이미지가 필요하다. 원본 모델 PLY/체크포인트와 전체 학습 사진, MVS 근거 공간은 용량 때문에 이 ZIP에 넣지 않았다. 정리 후 배경 PLY도 외부 작업 폴더에 보존한다. 사전 점검에 사용한 일부 사진은 PNG로 포함했다. 봉인 holdout은 포함하지 않았다.

run_cpu.sh와 run_gpu.sh는 원본을 읽기 전용으로 연결한다. 기존 출력이 있으면 일부 생성 도구는 중단하므로 재현은 별도 작업 출력 폴더에서 수행한다. 후보 렌더는 gsplat 1.4.0이며, 바탕은 후보 SH0에서도 SH3를 유지한다. 초기 사진 색은 두 높이의 유효 투영을 모두 모은 평균이며 GT는 읽지 않는다.

무결성 PASS는 파일 전달과 명시한 집계의 검증이며, 3.3 전체 통과나 학습 완료·연구 가설의 성공을 뜻하지 않는다. candpick_v1.json 학습 설정은 아직 잠그지 않았다.
'''
    manifest = dict(task_id='PHD-MAIN-CANDPICK-v1', created_at=now.isoformat(),
        commit=os.environ.get('CANDPICK_COMMIT'), docker_image=os.environ.get('CANDPICK_IMAGE'),
        scientific_verdict=None, files={})
    with zipfile.ZipFile(dest, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        for name, p in sorted(files.items()):
            manifest['files'][name] = dict(bytes=p.stat().st_size, sha256=sha(p))
            z.write(p, name)
        data = note.encode()
        manifest['files']['BUNDLE_README.md'] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        z.writestr('BUNDLE_README.md', data)
        z.writestr('MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    verification = verify(dest)
    receipt = dict(path=str(dest), bytes=dest.stat().st_size, sha256=sha(dest),
                   created_at=now.isoformat(), commit=manifest['commit'], verification=verification,
                   scientific_verdict=None)
    save(dest.with_suffix('.receipt.json'), receipt)
    dest.with_suffix('.zip.sha256').write_text(receipt['sha256'] + '  ' + dest.name + '\n')
    save(Path('/docs/delivery') / (dest.stem + '.json'), receipt)
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__': main()
