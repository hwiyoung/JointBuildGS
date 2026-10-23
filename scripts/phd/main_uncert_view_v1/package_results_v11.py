"""Package the verified v1.1 web snapshot, screenshots and evidence for download."""
import os
import shutil
import sys
import zipfile
sys.path.insert(0,'/repo/scripts/phd/main_uncert_view_v1')
from common import *

NAME='PHD-MAIN-UNCERT-VIEW-v1.1_results.zip'
URL='http://192.168.10.203:8912/downloads/'+NAME

def main():
    original=OUT/'PHD-MAIN-UNCERT-VIEW-v1.1_web.zip'
    reference=load(DOC/'tables_v1_1/package.json')
    assert sha(original)==reference['zip_sha256'], 'Original web ZIP changed'
    destination=OUT/NAME
    assert not destination.exists(), 'Result bundle already exists; preserve it'
    records=[]
    def record(name,data):
        records.append(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
    temp=OUT/(NAME+'.part')
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
        with zipfile.ZipFile(original) as web:
            for entry in web.infolist():
                if entry.is_dir():continue
                data=web.read(entry.filename);bundle.writestr(entry.filename,data);record(entry.filename,data)
        sources=[(DOC/'불확실도보기_보고_v1_1.md','report/불확실도보기_보고_v1_1.md'),
                 (DOC/'issues_v1_1.md','report/issues_v1_1.md')]
        for folder in ['screens_v1_1','tables_v1_1']:
            sources += [(p,'report/'+str(p.relative_to(DOC))) for p in sorted((DOC/folder).rglob('*')) if p.is_file() and not p.name.startswith('results_download')]
        for name in ['view_v1_1.json','view_v1_1.lock.json','view_v1.json','view_v1.lock.json','delivery_approval_20261023.json']:
            if (CFG/name).is_file():sources.append((CFG/name,'config/'+name))
        for path,name in sources:
            data=path.read_bytes();bundle.writestr(name,data);record(name,data)
        screenshots=[r for r in records if r['path'].startswith('report/screens_v1_1/') and r['path'].endswith('.png')]
        assert len(screenshots)==37
        readme=('불확실도 지도 보기 v1.1 — 결과 묶음\n\n'
                '웹 화면: http://192.168.10.203:8912/ (연구실 네트워크 또는 VPN)\n\n'
                'web/ : 검증한 v1.1 화면 코드와 표시 데이터. index.html이 시작 파일입니다.\n'
                'report/불확실도보기_보고_v1_1.md : 숫자, 검증 결과, 화면 사진 설명이 있는 보고서.\n'
                'report/screens_v1_1/ : 화면 캡처 37장 (발주문 34장 + 시작·부호 색·좁은 화면 3장).\n'
                'report/tables_v1_1/ : 수치 표, 다시 셈 비교, 브라우저·배포 검증 기록.\n'
                'config/ : 화면 설정과 SHA-256 잠금 기록.\n'
                'MANIFEST.json / SHA256SUMS.txt : 포함 파일 목록과 무결성 확인용 SHA-256.\n\n'
                '원래 패치 값과 정밀도를 유지했습니다. 학습과 GPU 사용은 없습니다.\n'
                '참값 관련 값은 참값 점검용이고, 집계 숫자는 화면에서 다시 셈입니다.\n'
                'scientific_verdict: null\n').encode('utf-8')
        bundle.writestr('읽어주세요.txt',readme);record('읽어주세요.txt',readme)
        manifest=dict(task_id='PHD-MAIN-UNCERT-VIEW-v1.1',made=now(),source_web_zip_sha256=reference['zip_sha256'],
                      screenshots=len(screenshots),file_count=len(records),files=records,scientific_verdict=None)
        bundle.writestr('MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        bundle.writestr('SHA256SUMS.txt',''.join(r['sha256']+'  '+r['path']+'\n' for r in records))
    # Verify every entry and its manifest bytes before making the URL available.
    with zipfile.ZipFile(temp) as bundle:
        assert bundle.testzip() is None
        for r in records:assert hashlib.sha256(bundle.read(r['path'])).hexdigest()==r['sha256'],r['path']
        assert 'web/index.html' in bundle.namelist()
    temp.replace(destination)
    checksum=sha(destination);downloads=OUT/'web_v1_1/downloads';downloads.mkdir(exist_ok=True)
    os.link(destination,downloads/NAME)
    (downloads/(NAME+'.sha256')).write_text(checksum+'  '+NAME+'\n')
    # Delivery-only HTML change; the original web ZIP and numerical release stay intact.
    page=ROOT/'scripts/phd/main_uncert_view_v1/index.html'
    shutil.copy2(page,OUT/'web_v1_1/index.html')
    receipt=dict(task_id='PHD-MAIN-UNCERT-VIEW-v1.1',made=now(),commit=os.environ.get('VIEW_COMMIT'),url=URL,
        archive=NAME,bytes=destination.stat().st_size,sha256=checksum,screenshots=len(screenshots),
        payload_files=len(records),zip_entries=len(records)+2,source_web_zip_sha256=reference['zip_sha256'],
        served_index_sha256=sha(OUT/'web_v1_1/index.html'),all_entries_crc_and_sha256_verified=True,scientific_verdict=None)
    dump(DOC/'tables_v1_1/results_download.json',receipt);dump(OUT/'results_download_v1_1.json',receipt)
    progress(f'v1.1 결과 다운로드: 화면 캡처 37장·보고서·수치 표·설정·검증 기록·원래 웹 묶음을 ZIP에 포함. {receipt["bytes"]/1e6:.2f} MB. ZIP 모든 항목의 CRC·SHA-256 확인. 화면에 다운로드 링크 추가.')
    print(json.dumps(receipt,ensure_ascii=False))

if __name__=='__main__':main()
