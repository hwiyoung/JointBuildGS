"""Record deployment, immutable bundle identity, and transport acceptance."""
import os
import sys
sys.path.insert(0, '/repo/scripts/phd/main_uncert_view_v1')
from common import *

inspection = load(OUT / 'download_runtime_inspect.json')
browser = load(DOC / 'tables_v1_1/download_browser_live.json')
resumed = load(DOC / 'tables_v1_1/download_http_resume.json')
assert browser['pass'] and resumed['hash_matches']
checks = []
for name, expected in [
    ('PHD-MAIN-UNCERT-VIEW-v1.1_results.zip', '9612a4d12fdcab4a186f7b248a43607984d364e110865282a77aa6eae4886148'),
    ('PHD-MAIN-UNCERT-VIEW-v1.1_web.zip', '74d1a37280cd48e1a076bcf8d62c6d5f027ae15ebcb9d8e3ea3a4da5004ef249')]:
    actual = sha(OUT / name)
    assert actual == expected
    checks.append(dict(path=name, sha256=actual, matches_frozen=True))
assert sha(CFG / 'view_v1_1.json') == 'beaead64ff5a5ffee1cfaee5fe7fa17efcfe074a47c136ee872dc622fc93533b'
assert sha(ROOT / 'scripts/phd/main_uncert_view_v1/index.html') == sha(OUT / 'web_v1_1/index.html')
assert sha(ROOT / 'scripts/phd/main_uncert_view_v1/download_server.py') == sha(OUT / 'delivery_server_v1/download_server.py')
containers = []
for item in inspection:
    containers.append(dict(name=item['Name'], id=item['Id'], image=item['Image'],
        status=item['State']['Status'], started=item['State']['StartedAt'],
        command=item['Config']['Cmd'], mounts=item['Mounts'],
        ports=item['HostConfig']['PortBindings'], readonly_root=item['HostConfig']['ReadonlyRootfs'],
        cpus=item['HostConfig']['NanoCpus']/1e9, memory_bytes=item['HostConfig']['Memory'],
        device_requests=item['HostConfig']['DeviceRequests']))
assert containers[0]['status'] == 'running'
assert all(c['status'] == 'exited' for c in containers[1:])
receipt = dict(task_id='PHD-MAIN-UNCERT-VIEW-v1.1', made=now(), commit=os.environ.get('VIEW_COMMIT'),
    unit_tests=dict(command='python -m unittest tests.phd.test_uncert_view_download -v', tests=8, failures=0),
    findings_before=['Range request returned 200 and the entire file',
                     'No attachment or Accept-Ranges headers',
                     'One client BrokenPipeError observed; client finalization cause unconfirmed'],
    browser_client='User reports Codex in-app browser',
    codex_client_completion='User confirms small bundle still stalls at completion after transport fix',
    client_transfer_observation=dict(time_utc='2026-10-23T12:52:12Z',
        file='PHD-MAIN-UNCERT-VIEW-v1.1_report_and_screens.zip',
        expected_bytes=5444856, sent_bytes=5444856, server_outcome='complete',
        client_outcome='not completed, per user'),
    linux_chromium_downloads='both completed and saved SHA-256 matched',
    resumed_full_zip_sha256=resumed['sha256'], preserved=checks, containers=containers,
    server_sha256=sha(OUT / 'delivery_server_v1/download_server.py'),
    index_sha256=sha(OUT / 'web_v1_1/index.html'), scientific_verdict=None)
dump(DOC / 'tables_v1_1/download_transport.json', receipt)
progress('v1.1 다운로드 후속 확인: 사용자에게서 수정 후에도 Codex 앱의 5.4 MB ZIP이 끝에서 멈춘다는 답을 받음. 해당 요청의 서버 로그는 2026-10-23 12:52:12 UTC에 5,444,856 bytes 전송 완료. 별도 Linux Chromium의 두 ZIP 저장 및 SHA-256은 통과. 서버 조치는 PASS이나 Codex 앱 최종 저장 문제는 미해결. Chrome/Edge에서 같은 URL을 직접 여는 우회 방법과 앱 다운로드 경로 확인 안내를 제공. 원래 ZIP·설정 보존.')
print(json.dumps(dict(server_sha256=receipt['server_sha256'], preserved=checks, scientific_verdict=None)))
