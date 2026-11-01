"""Record final review and terminal checkpoint scope before sealing the archive."""
from common import *


def main():
    figures = [dict(file=p.name, sha256=sha(p))
               for p in sorted((DOC / 'figures').glob('r6_*.png'))]
    assert len(figures) == 40
    dump(DOC / 'tables/visual_review_r6.json', dict(
        at=stamp(), status='PASS_LAYOUT_AND_EVIDENCE_REVIEW', figures=figures,
        review_method='All 40 figures inspected on four contact sheets; section, movement and reset figures also inspected at full resolution.',
        reviewed_contact_sheets=[dict(file=p.name, sha256=sha(p)) for p in sorted((OUT / 'r6/visual_review').glob('sheet_*.png'))],
        limitations='Contact sheets establish layout and comparison coverage. Dense 3D points can occlude references; separate GT/prior panels are provided. This is not human visual acceptance or a scientific verdict.',
        scientific_verdict=None))
    result = dict(at=stamp(), status='STOP_R6_7000_AND_SCHEDULED_RESET',
        checkpoint_evaluation='COMPLETE_BOTH_FAIL', diagnostics='COMPLETE',
        saved_complete_iterations=[7000], not_reached_iterations=[15000, 30000],
        remaining_six_runs='NOT_STARTED', additional_training_authorized=False,
        delivery='See delivery_receipt_r6.json for sealed ZIP name and integrity checks.',
        scientific_verdict=None)
    dump(DOC / 'tables/final_status_r6.json', result)
    dump(OUT / 'r6/final_status.json', result)
    p = DOC / 'progress.md'
    body = p.read_text()
    marker = '## r6 최종 점검 완료'
    assert marker not in body
    p.write_text(body + '\n' + marker + ' · ' + stamp() + '\n\n'
        '두 판의 7,000회 메시 채점·화소 집계·출신 진단·상태 감사와 그림 40장을 마쳤다. '
        '뜬 면은 ALS 10.775%, LoD2 18.252%로 둘 다 5% 기준 미달이다. '
        '일치 영역 결과 τ 안은 ALS 84.918%(통과), LoD2 67.681%(74.1% 미달)이다. '
        '면 없음은 각각 2.530%, 1.996%로 r4n보다 줄었고 7,000회 건강은 둘 다 통과했다.\n\n'
        'r4n 동일 채점 재현, 각 판 첫 면 광선 2,048개, 406개 영상의 깊이 및 출신·σ 분포, '
        '각 판 7,000회 전체 Adam 상태 검증을 통과했다. r19와 잠근 입력은 그대로다. '
        '기하 기준 미달과 ALS 9,000회 정기 불투명도 초기화 직후 감시 중단을 구분해 기록했다. '
        '15,000·30,000회는 미도달, 나머지 여섯 판은 미시작이다. '
        '최종 ZIP 이름·CRC·SHA-256은 delivery_receipt_r6.json에 남긴다. '
        'r6 4절의 두 판 멈춤·후속 결정 요청 상태를 유지한다. scientific_verdict: null.\n')
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
