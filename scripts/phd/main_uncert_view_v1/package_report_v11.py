"""Make a small report/screens bundle from the already verified full ZIP."""
import hashlib
import json
import os
from pathlib import Path
import zipfile

ROOT = Path('/view')
FULL = ROOT / 'PHD-MAIN-UNCERT-VIEW-v1.1_results.zip'
NAME = 'PHD-MAIN-UNCERT-VIEW-v1.1_report_and_screens.zip'
FULL_SHA = '9612a4d12fdcab4a186f7b248a43607984d364e110865282a77aa6eae4886148'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    assert sha(FULL) == FULL_SHA
    destination = ROOT / NAME
    assert not destination.exists(), 'Preserve an existing release bundle'
    rows = []
    part = destination.with_suffix('.zip.part')
    with zipfile.ZipFile(FULL) as source, zipfile.ZipFile(part, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as result:
        def add(name, data):
            result.writestr(name, data)
            rows.append(dict(path=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
        for info in source.infolist():
            if not info.is_dir() and info.filename.startswith(('report/', 'config/')):
                add(info.filename, source.read(info.filename))
        add('읽어주세요.txt', (
            '불확실도 지도 v1.1 — 캡처·보고서 묶음\n\n'
            '화면 캡처 37장, 보고서, 수치 표, 설정과 검증 기록을 담았습니다.\n'
            '웹 화면 코드와 전체 표시 데이터는 큰 결과 묶음에 포함되어 있습니다.\n'
            '웹 화면: http://192.168.10.203:8912/ (연구실 네트워크 또는 VPN)\n'
            'report/불확실도보기_보고_v1_1.md : 보고서\n'
            'report/screens_v1_1/ : 화면 캡처 37장\n'
            'report/tables_v1_1/ : 수치 표와 검증 기록\n'
            'config/ : 설정·잠금\n\n'
            '원래 결과 묶음의 해당 파일을 바이트 변경 없이 옮겼습니다.\n'
            'scientific_verdict: null\n').encode('utf-8'))
        assert len([r for r in rows if r['path'].startswith('report/screens_v1_1/')]) == 37
        result.writestr('MANIFEST.json', json.dumps(dict(
            task_id='PHD-MAIN-UNCERT-VIEW-v1.1', source_archive=FULL.name,
            source_sha256=FULL_SHA, files=rows, scientific_verdict=None), ensure_ascii=False, indent=2) + '\n')
        result.writestr('SHA256SUMS.txt', ''.join(r['sha256'] + '  ' + r['path'] + '\n' for r in rows))
    with zipfile.ZipFile(part) as result:
        assert result.testzip() is None
        for row in rows:
            assert hashlib.sha256(result.read(row['path'])).hexdigest() == row['sha256']
    part.replace(destination)
    downloads = ROOT / 'web_v1_1/downloads'
    os.link(destination, downloads / NAME)
    checksum = sha(destination)
    (downloads / (NAME + '.sha256')).write_text(checksum + '  ' + NAME + '\n')
    receipt = dict(archive=NAME, bytes=destination.stat().st_size, sha256=checksum,
                   source_sha256=FULL_SHA, screenshots=37, payload_files=len(rows),
                   crc_and_sha256_verified=True, scientific_verdict=None)
    (Path('/docs/tables_v1_1/report_download.json')).write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
