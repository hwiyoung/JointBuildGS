"""Record the actual final title-masked self-review and pin the viewed assets."""
import json
import shutil
from common import *

observations = [
    ('B173-뜬면-1', '지붕 끝 위 붉은 조각, 학습 깊이와 메시 첫 교차의 차이, 잠근 높이 범위의 단면이 구분됨.'),
    ('B173-뜬면-2', '지붕 가장자리 붉은 조각과 단면의 높은 점, 네 깊이와 힘 지도가 구분됨.'),
    ('B173-날개', '낮은 돌출 지붕 위 붉은 조각과 자료·결과 단면이 구분됨. 빗각 실사의 낮은 해상도를 유지함.'),
    ('B0-뜬면-1', '박공지붕 위 수직 조각과 메시 첫 교차의 세부 차이가 보임. 표본 부족 표지가 있음.'),
    ('R1-뜬면-1', '곡면 지붕 위 넓은 붉은 조각과 학습 깊이·메시 첫 교차 차이가 보임.'),
    ('R1-뜬면-2', '긴 지붕 끝의 붉은 조각, 깊이 차이와 높은 단면 점이 구분됨.'),
    ('R1-보존띠-1', '주 시점·빗각 실사는 확인 불가로 명시됨. 3차원·단면·숫자만 비교 가능하며 사진 종류를 추정하지 않음.'),
]
qa = OUT/'qa/A2'
assert json.loads((qa/'receipt.json').read_text())['status'] == 'PASS'
history = OUT/'history/A2_before_visual_review_metadata'
history.mkdir(exist_ok=False)
rows = []
for i, (case, observation) in enumerate(observations):
    screenshot = qa/f'blind_{i}.png'
    plate = DOC/'보기/img'/f'{case}_plate_A2.jpg'
    metadata = DOC/'figures'/f'{case}_plate_A2.json'
    entry = dict(case=case, screenshot=str(screenshot), screenshot_sha256=sha(screenshot),
                 plate_sha256=sha(plate), observation=observation,
                 status='PARTIAL_PHOTO_UNAVAILABLE' if i == 6 else 'PASS_READABILITY')
    rows.append(entry)
    shutil.copy2(metadata, history/metadata.name)
    data = json.loads(metadata.read_text())
    assert data['visual_review'] == 'PENDING'
    data['visual_review'] = dict(status=entry['status'], receipt='provenance/A2_visual_review_complete.json')
    metadata.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
save(DOC/'provenance/A2_visual_review_complete.json', dict(
    at=now(), reviewer='Codex self-check, not independent human review',
    method='Actually displayed all seven final title-masked browser screenshots in groups of two or three.',
    rows=rows, additional_actual_checks=['R1-뜬면-2_formation_A2.jpg', 'R1-보존띠-1_multiview_map_A2.jpg', 'B0-뜬면-1_multiview_examples_A2.jpg'],
    scientific_verdict=None))
shutil.copy2(qa/'receipt.json', DOC/'provenance/A2_browser_QA.json')
assets = {str(p.relative_to(DOC/'보기')):dict(bytes=p.stat().st_size, sha256=sha(p))
          for p in sorted((DOC/'보기').rglob('*')) if p.is_file()}
save(DOC/'provenance/viewer_final_assets.json', dict(at=now(), assets=assets,
    bytes=sum(x['bytes'] for x in assets.values()), scientific_verdict=None))
print('Final seven-case self-review and offline browser evidence sealed')
