"""Record the deployed viewer, frozen-data preservation, and browser acceptance."""
import os
import sys
import zipfile
sys.path.insert(0, '/repo/scripts/phd/main_uncert_view_v1')
from common import *


def main():
    web = OUT/'web_mvs_v1_2'
    records = []
    old_hashes = {
        'PHD-MAIN-UNCERT-VIEW-v1.1_results.zip': '9612a4d12fdcab4a186f7b248a43607984d364e110865282a77aa6eae4886148',
        'PHD-MAIN-UNCERT-VIEW-v1.1_web.zip': '74d1a37280cd48e1a076bcf8d62c6d5f027ae15ebcb9d8e3ea3a4da5004ef249',
    }
    for name, expected in old_hashes.items():
        assert sha(OUT/name) == expected, name
    with zipfile.ZipFile(OUT/'PHD-MAIN-UNCERT-VIEW-v1.1_web.zip') as archive:
        for name in archive.namelist():
            relative = Path(name).relative_to('web')
            if relative.parts[0] not in ('data', 'sections', 'faces') or name.endswith('/'):
                continue
            expected = hashlib.sha256(archive.read(name)).hexdigest()
            assert sha(web/relative) == expected, name
            records.append(dict(path=str(relative), sha256=expected))
    assert records
    frozen_config = 'beaead64ff5a5ffee1cfaee5fe7fa17efcfe074a47c136ee872dc622fc93533b'
    assert sha(CFG/'view_v1_1.json') == frozen_config
    assert sha(CFG/'mvs_display_v1_2.json') == load(CFG/'mvs_display_v1_2.lock.json')['sha256']
    source = ROOT/'scripts/phd/main_uncert_view_v1'
    assets = []
    for path in sorted(web.iterdir()):
        if path.is_file() and (source/path.name).is_file():
            assert sha(path) == sha(source/path.name), path.name
            assets.append(dict(path=path.name, sha256=sha(path)))
    checks = {}
    for label in ('preview', 'live', 'offline'):
        result = load(DOC/f'tables_v1_2/browser_{label}.json')
        assert result['pass'] and not result['errors'], label
        checks[label] = dict(checks=len(result['checks']), pass_=True, receipt=f'browser_{label}.json')
    download_test = load(DOC/'tables_v1_2/download_browser_live.json')
    assert download_test['pass']
    downloads = load(DOC/'tables_v1_2/downloads.json')
    for kind in ('full', 'report'):
        entry = downloads[kind]
        assert sha(web/'downloads'/entry['archive']) == entry['sha256']
        matches = [x for x in download_test['downloads'] if x['suggestedFilename'] == entry['archive']]
        assert len(matches) == 1 and matches[0]['state'] == 'completed' and matches[0]['hash_matches']
        assert matches[0]['sha256'] == entry['sha256'] and matches[0]['saved_bytes'] == entry['bytes']
    containers = []
    for line in (OUT/'runtimeinspect_v12.jsonl').read_text().splitlines():
        obj = json.loads(line)
        containers.append(dict(name=obj['Name'], id=obj['Id'], image=obj['Image'],
            running=obj['State']['Running'], mounts=[dict(source=m['Source'], destination=m['Destination'], writable=m['RW']) for m in obj['Mounts']],
            ports=obj['HostConfig']['PortBindings'], readonly_root=obj['HostConfig']['ReadonlyRootfs']))
    active = next(x for x in containers if x['name'] == '/jbgs-main-uncert-view-8912')
    assert active['running'] and active['readonly_root']
    assert any(m['destination'] == '/web' and m['source'].endswith('/web_mvs_v1_2') and not m['writable'] for m in active['mounts'])
    receipt = dict(task_id='PHD-MAIN-UNCERT-VIEW-v1.2', made=now(),
        source_base_commit=os.environ.get('VIEW_COMMIT'), source_state='task changes pending commit; exact asset hashes below',
        url='http://192.168.10.203:8912/', image=os.environ.get('VIEW_IMAGE'),
        containers=containers, assets=assets, browser=checks, downloads=downloads,
        preserved_archives=old_hashes, preserved_config_sha256=frozen_config,
        unchanged_data=records, unchanged_data_files=len(records),
        codex_app_save_status='User previously reported hanging; native app saving remains unverified. Linux Chromium completed both new ZIP downloads.',
        pass_=True, scientific_verdict=None)
    dump(DOC/'tables_v1_2/deployment.json', receipt)
    progress(f'v1.2 기존 8912 주소 배포 완료. 미리보기 {checks["preview"]["checks"]}개, 실제 주소 {checks["live"]["checks"]}개, 오프라인 {checks["offline"]["checks"]}개 화면 검사 통과. 두 ZIP Chromium 저장 완료·SHA-256 일치. 기존 자료 {len(records)}개와 v1.1 ZIP·설정 해시 보존. v1.1 서비스는 중지 상태로 보존. Codex 앱 자체의 저장 완료는 미확인. scientific_verdict: null.')
    print(json.dumps(dict(pass_=True, unchanged_data_files=len(records), browser=checks), ensure_ascii=False))


if __name__ == '__main__':
    main()
