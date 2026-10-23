"""Create separate v1.2 result/report bundles, preserving every v1.1 bundle."""
import os
import sys
import zipfile
sys.path.insert(0, '/repo/scripts/phd/main_uncert_view_v1')
from common import *

WEB = OUT/'web_mvs_v1_2'


def package(kind, sources):
    name=f'PHD-MAIN-UNCERT-VIEW-v1.2_{kind}.zip'
    destination=OUT/name
    assert not destination.exists(), 'Preserve existing bundle'
    part=OUT/(name+'.part');records=[]
    with zipfile.ZipFile(part,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as out:
        for path,arc in sources:
            out.write(path,arc)
            records.append(dict(path=arc,bytes=path.stat().st_size,sha256=sha(path)))
        info=dict(task_id='PHD-MAIN-UNCERT-VIEW-v1.2',made=now(),files=records,
                  screenshots=sum(x['path'].endswith('.png') for x in records),scientific_verdict=None)
        out.writestr('MANIFEST.json',json.dumps(info,ensure_ascii=False,indent=2)+'\n')
        out.writestr('SHA256SUMS.txt',''.join(x['sha256']+'  '+x['path']+'\n' for x in records))
        out.writestr('읽어주세요.txt','불확실도 보기 v1.2\n웹 주소 http://192.168.10.203:8912/\nreport/MVS점군_표시_v1_2.md : 이번 변경과 캡처\nreport/불확실도보기_보고_v1_1.md : 기존 수치 보고\nMVS 점의 좌표는 원본, 색은 연결 패치의 기존 값입니다. 표시 점만 솎았으며 수치는 유지했습니다.\nresults 묶음에는 web/index.html과 오프라인 자료가 포함됩니다. report_and_screens 묶음에는 보고·캡처·설정·검증이 들어 있습니다.\nscientific_verdict: null\n')
    with zipfile.ZipFile(part) as out:
        assert out.testzip() is None
        for record in records:
            assert hashlib.sha256(out.read(record['path'])).hexdigest()==record['sha256']
    part.replace(destination);downloads=WEB/'downloads';downloads.mkdir(exist_ok=True)
    os.link(destination,downloads/name)
    checksum=sha(destination);(downloads/(name+'.sha256')).write_text(checksum+'  '+name+'\n')
    return dict(archive=name,url='http://192.168.10.203:8912/downloads/'+name,bytes=destination.stat().st_size,
        sha256=checksum,screenshots=info['screenshots'],files=len(records),crc_and_sha256_verified=True)


def main():
    sources=[]
    for name in ['MVS점군_표시_v1_2.md','불확실도보기_보고_v1_1.md','issues_v1_1.md']:
        sources.append((DOC/name,'report/'+name))
    for folder in ['screens_v1_1','screens_v1_2','tables_v1_1','tables_v1_2']:
        for path in sorted((DOC/folder).rglob('*')):
            if path.is_file() and path.name!='downloads.json':sources.append((path,'report/'+str(path.relative_to(DOC))))
    sources += [(path,'config/'+path.name) for path in sorted(CFG.glob('*.json'))]
    small=package('report_and_screens',sources)
    web=[(path,'web/'+str(path.relative_to(WEB))) for path in sorted(WEB.rglob('*')) if path.is_file() and 'downloads' not in path.relative_to(WEB).parts]
    full=package('results',sources+web)
    receipt=dict(task_id='PHD-MAIN-UNCERT-VIEW-v1.2',made=now(),commit=os.environ.get('VIEW_COMMIT'),
                 full=full,report=small,scientific_verdict=None)
    dump(DOC/'tables_v1_2/downloads.json',receipt)
    progress(f'v1.2 별도 결과 묶음: 전체 {full["bytes"]/1e6:.1f} MB, 캡처·보고 {small["bytes"]/1e6:.1f} MB. 캡처 {full["screenshots"]}장. 모든 ZIP 항목 CRC·SHA-256 확인. 기존 v1.1 묶음 보존.')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':main()
