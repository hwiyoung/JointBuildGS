"""Create the final requested result archive after 24 completed, checked arms."""
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import zipfile
from input_audit import sha
from prepare_places import save
from verify_results_bundle import verify


def main():
    repo, out, doc = Path('/repo'), Path('/out'), Path('/docs')
    status = json.loads((doc / 'results/status.json').read_text())
    assert status['completed_count'] == 24 and status['status'] == 'SCORING_COMPLETE'
    validation = json.loads((doc / 'results/validation.json').read_text()); assert validation['completed_arms'] == 24 and validation['status'] == 'PASS'
    figs = json.loads((doc / 'figures/quantitative_index.json').read_text()); assert len(figs['files']) == 12
    reps = json.loads((doc / 'figures/representatives/index.json').read_text())['representatives']
    assert sum(r['status'] == 'COMPLETE' for r in reps) == 3
    for unit, count in [('B173_ALS', 6), ('R1_LoD2', 12)]:
        index = json.loads((doc / 'figures/representatives' / (unit + '_photos_index.json')).read_text())
        assert len(index['files']) == count
    visual = json.loads((doc / 'visual_review.json').read_text()); assert visual['status'] == 'PASS'
    inputs = json.loads((doc / 'final_input_verification.json').read_text()); assert inputs['status'] == 'PASS'
    cfg = json.loads(Path('/config/candpick_v1.json').read_text())
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    dest = out / 'delivery' / ('PHD-MAIN-CANDPICK-v1_결과_' + now.strftime('%m%d-%H%M') + '.zip')
    assert not dest.exists(); files = {}
    for rel in ['scripts/phd/main_candpick_v1', 'configs/phd/main_candpick_v1', 'docs/experiments/phd/main_candpick_v1']:
        for p in sorted((repo / rel).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and 'delivery' not in p.parts:
                files[str(p.relative_to(repo))] = p
    for rel in cfg['implementation_sha256']: files[rel] = repo / rel
    rel = 'tests/phd/test_main_candpick_v1.py'; files[rel] = repo / rel
    for folder in ['places', 'validation', 'occlusion', 'render_masks', 'scoring', 'visuals', 'logs']:
        for p in sorted((out / folder).rglob('*')):
            if p.is_file(): files['payload/' + str(p.relative_to(out))] = p
    for unit in cfg['units']:
        for name in ['candidate_geometry.npz', 'initial_right_candidate.npz', 'candidate_color.npy',
                     'candidate_color_sample_count.npy', 'cleanup_masks.npz', 'scene.json']:
            p = out / 'scenes' / unit / name; files['payload/' + str(p.relative_to(out))] = p
    for arm in status['completed_arms']:
        root = out / 'runs' / arm
        for p in sorted(root.iterdir()):
            if p.is_file() and p.suffix in ['.json', '.jsonl', '.npz']:
                files['payload/' + str(p.relative_to(out))] = p
    note = '''# PHD-MAIN-CANDPICK-v1 결과 묶음

24판 × 3,000회 학습과 채점이 끝난 진단 자료다. 먼저 docs/experiments/phd/main_candpick_v1/result_report.md를 읽는다. scientific_verdict: null.

## 구성

- results/outcomes.csv: 경우 × 묶음 × 앞뒤 × 판의 네 결과 넓이 비율, 건물별 중앙값과 건물 수. 가림 30% 초과 점의 별도 행 포함.
- results/criteria.csv: 묶음 가의 초기값 비교와 사전 수치 기준 대조. SH3가 주 기준이고 SH0는 진단 비교다.
- figures: 불투명도 곡선, 넓이 구성, 고정 대표 자리의 실제 사진·단면·시작/끝 렌더·여러 각도의 3D 후보 불투명도.
- payload/runs: 각 판의 0·500·3,000회 후보 상태, 100회 기록, 시작·끝 전체 학습 사진 오차, 고정 값 전후 해시, 완료 기록.
- payload/places, occlusion, validation: 점별 선택·나눔·넓이, 가림 분자/분모, 원본 사진 판정 열.
- configs, scripts: 고정 설정과 실행·검산 도구. candpick_v1.lock.json의 해시는 첫 최적화 이전 값이다.

## 검증

MANIFEST.json은 자신을 제외한 모든 회원 파일의 SHA-256과 크기를 담는다. NumPy가 있는 jointbuildgs:dev Docker 환경에서 다음 명령으로 CRC·해시·24판의 점별 결과 및 432개 넓이/건물 표 행을 다시 계산한다.

    python scripts/phd/main_candpick_v1/verify_results_bundle.py /path/to/this.zip

원본 사진·큰 바탕 PLY·MVS 근거 공간·전체 optimizer 복구 상태는 이 ZIP에 중복하지 않았다. 표와 후보 상태·그림 데이터의 검산은 ZIP만으로 가능하다. 전체 학습 재실행과 전체 사진 렌더에는 render_inputs_v1.json 및 입력 기록에 지정된 원본, 저장소의 상속 구현, Docker 이미지가 필요하다. 원본 바탕과 optimizer 복구 파일은 외부 작업 폴더에 보존했다. 정적 그림의 한글 폰트는 Noto Sans CJK이며 출력 이미지는 폰트 설치 없이 볼 수 있다.

## 기록의 시점

stage1_report.md, stage1_summary.json은 최초 50cm 칸 밖 동일 검사에서 멈춘 당시 기록이다. 이후 render_scope_resolution.md의 해석으로 정상적인 가우시안 번짐을 포함한 실제 영향영역 밖 불변을 적용했다. 최초 실패를 삭제하지 않았다. 현재 결과는 results/status.json과 result_report.md를 따른다.

사진 오차 감소, 파일 무결성, 고정 값 해시 일치는 각각의 기술적 증거다. 이를 맞는 후보 선택이나 연구적 성공으로 대신 판정하지 않는다. 높은 가림 점을 제외하지 않았으며, 대표 유리 채광창의 부재·낙엽 지붕의 대체 여부도 유지했다.
'''
    manifest = dict(task_id='PHD-MAIN-CANDPICK-v1', created_at=now.isoformat(),
        commit=os.environ.get('CANDPICK_COMMIT'), config_sha256=status['config_sha256'],
        scientific_verdict=None, files={})
    with zipfile.ZipFile(dest, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        for name, p in sorted(files.items()):
            manifest['files'][name] = dict(bytes=p.stat().st_size, sha256=sha(p)); z.write(p, name)
        data = note.encode(); manifest['files']['BUNDLE_README.md'] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        z.writestr('BUNDLE_README.md', data)
        z.writestr('MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    verification = verify(dest)
    receipt = dict(path=str(dest), bytes=dest.stat().st_size, sha256=sha(dest),
        created_at=now.isoformat(), commit=manifest['commit'], verification=verification, scientific_verdict=None)
    save(dest.with_suffix('.receipt.json'), receipt)
    dest.with_suffix('.zip.sha256').write_text(receipt['sha256'] + '  ' + dest.name + '\n')
    save(doc / 'delivery' / (dest.stem + '.json'), receipt)
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__': main()
