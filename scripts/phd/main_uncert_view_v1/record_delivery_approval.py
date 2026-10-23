"""Record the user's delivery decisions without rebuilding the frozen web payload."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_uncert_view_v1')
from common import *

NAME = 'delivery_approval_20261023.json'
package = load(DOC / 'tables/package.json')
archive = OUT / 'PHD-MAIN-UNCERT-VIEW-v1_web.zip'
assert sha(archive) == package['zip_sha256']
assert sha(CFG / 'view_v1.json') == load(CFG / 'view_v1.lock.json')['sha256']
approval = dict(
    task_id='PHD-MAIN-UNCERT-VIEW-v1', recorded_at=now(),
    source='User replies to the two pending delivery questions in this chat',
    network_answer='연구실 네트워크나 VPN에서 접속',
    size_answer='정밀도·표본 유지, 300 MB 초과 허용',
    network_scope='research_server_lan_or_vpn',
    allow_over_300_mb=True, preserve_numeric_precision=True, preserve_samples=True,
    accepted_web_bytes=package['web_bytes'], accepted_zip_bytes=package['zip_bytes'],
    accepted_zip_sha256=package['zip_sha256'],
    frozen_view_config_sha256=sha(CFG / 'view_v1.json'),
    scientific_verdict=None,
)
for path in (CFG / NAME, DOC / 'tables' / NAME, OUT / NAME):
    if path.exists():
        old = load(path)
        assert all(old[k] == v for k, v in approval.items() if k != 'recorded_at')
    else:
        dump(path, approval)

report = DOC / '불확실도보기_보고_v1.md'
text = report.read_text()
text = text.replace(
    'Windows Chrome·Edge는 확인 불가이며 전체 웹 크기는 300 MB 초과다.',
    'Windows Chrome·Edge는 확인 불가다. 연구실 네트워크·VPN 접속과 정밀도·표본을 유지한 300 MB 초과는 사용자 승인 완료다.',
)
text = text.replace(
    '- 전체 웹 폴더가 300 MB를 넘어 표본 또는 정밀도를 줄이기 전에 사용자에게 선택을 요청했다. 응답 전에는 원본 유지판을 제공한다. 압축 파일 크기와 풀린 웹 크기를 구별한다.',
    '- 사용자 확정: 연구실 네트워크나 VPN에서 접속하며, 정밀도·표본을 유지한 300 MB 초과를 허용한다. 승인 대상은 현재 웹 392.43 MB / ZIP 293.07 MB 묶음이다. '
    '[승인 기록](tables/delivery_approval_20261023.json). 최초 설정·잠금·배포 당시 receipt·웹·ZIP 바이트는 보존했다.',
)
report.write_text(text)
issues = DOC / 'issues.md'
text = issues.read_text().replace(
    '- 열림: 전체 웹 폴더가 300 MB를 초과했다. 발주문 2절에 따라 표시 점 수 또는 정밀도를 줄이기 전 사용자에게 질문했다. 현재는 모든 잠근 표본과 정밀도를 유지한 버전이며, 줄이는 조치는 실행하지 않았다.',
    '- 해결: 사용자가 정밀도·표본 유지와 300 MB 초과를 명시적으로 허용했다. 현재 웹 392.43 MB / ZIP 293.07 MB를 유지한다. 승인 기록은 tables/delivery_approval_20261023.json에 추가했다.',
)
text = text.replace(
    '- 범위: 연구 서버와 연결된 네트워크/VPN 주소를 제공한다. 외부 인터넷에서의 접속은 검증하지 않았다.',
    '- 범위 확정: 사용자는 연구실 네트워크나 VPN에서 접속한다고 답했다. 현재 연구 서버 주소를 유지한다. 외부 인터넷 공개는 요청 범위에 포함되지 않는다.',
)
issues.write_text(text)
progress('사용자 전달 조건 확정: 연구실 네트워크·VPN 접속, 정밀도·표본 유지 및 300 MB 초과 허용. 승인 기록 추가. 기존 웹·ZIP·설정 잠금·배포 당시 receipt 보존.')
print('Delivery approval recorded; archive and frozen config hashes unchanged.')
