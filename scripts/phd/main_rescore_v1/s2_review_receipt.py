"""Record the completed first manual R1 figure review; not an automated visual verdict."""
from common import *

notes = {
    3: 'ALS 최초 검토에서 제목 겹침·하단 글자 잘림 발견. 두 사전 정보의 배치만 수정하고 300 dpi 글자 경계·겹침 자동 검사 통과. LoD2는 수정 후 최초 시각 검토 통과. 점수·시점·색·형상 변경 없음.',
    4: '열 방법의 점·범례·두 칸의 완전성 축 확인. 읽을 수 있는 범례와 제목.',
    5: '두 사전 정보에서 같은 A·B 자리. LoD2 A 일치, B 보정 이름 확인. 칸 전체 값과 정확한 삼각형 단면 표시.',
    6: '같은 B 자리의 기준선·본 방법 비교, 12 m 단면과 해당 칸 전체 값 표시 확인.',
    7: '두 지도 동일 범위·같은 m 색척도, 제목·색 막대·축 확인.',
}
for prior in ['ALS', 'LoD2']:
    dest = O/'validation'/f'visual_R1_{prior}.json'
    assert not dest.exists(), 'Do not repeat the visual review'
    rows = []
    for n in range(3, 8):
        name = f'R1rep_b10__그림7_{n}_{prior}'
        p = D/'figures'/(name+'.png')
        row = dict(name=name, review_count=1, status='PASS', notes=notes[n], final_png_sha256=sha(p))
        if n == 3:
            meta = json.loads(p.with_suffix('.json').read_text())
            assert meta['layout_check']['status'] == 'PASS'
            row['initial_visual_status'] = 'LAYOUT_REPAIR_REQUIRED' if prior == 'ALS' else 'PASS'
            row['repair_verification'] = 'automated text bounding boxes at 300 dpi; ALS not visually reopened'
        rows.append(row)
    dump(dest, dict(at=now(), rows=rows, scientific_verdict=None))
progress('R1 두 사전 정보 그림 7.3~7.7의 최초 시각 검토 완료. 7.3 배치 수정은 300 dpi 글자 경계·겹침 검사로 확인; 기존 그림 재검토·메시·점수 재계산 없음.')
