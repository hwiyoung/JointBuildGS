"""Stream eight review ZIPs, verify CRC, member SHA-256, coverage and size."""
import hashlib
import json
from pathlib import Path
import zipfile
from rfcore import PAY, DOC, CFG, dump, load, now, sha, environment


def digest_stream(stream):
    h = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1 << 20), b''):
        h.update(chunk)
    return h.hexdigest()


def main():
    repo = Path('/repo')
    assert (DOC/'재현기록.md').is_file()
    assert (DOC/'tables/provenance.json').is_file()
    assert load(DOC/'tables/verification.json')['status'] == 'PASS'
    root = PAY/'handover'
    root.mkdir(exist_ok=True)
    sources = {}
    groups = {i: [] for i in range(1,9)}
    common = []
    for base in [CFG, DOC, repo/'scripts/phd/main_regionfig_v2']:
        for path in sorted(base.rglob('*')):
            if not path.is_file():
                continue
            assert '__pycache__' not in path.parts
            if base == CFG:
                arc = 'configs/phd/main_regionfig_v2/'+str(path.relative_to(base))
            elif base == DOC:
                arc = 'docs/experiments/phd/main_regionfig_v2/'+str(path.relative_to(base))
            else:
                arc = str(path.relative_to(repo))
            assert arc not in sources
            sources[arc] = path
            if path.suffix == '.png' or (base == DOC and path.parent == DOC/'figures'):
                part = int(path.stem.split('_')[1]) if path.stem.startswith(('영역표본_', '검토용_')) else int(path.stem.split('_')[0])
                groups[part].append(arc)
            else:
                common.append(arc)
    hashes = {name: sha(path) for name, path in sources.items()}
    sums = ''.join(f'{hashes[name]}  {name}\n' for name in sorted(hashes)).encode()
    (root/'SHA256SUMS').write_bytes(sums)
    parts = []
    covered = set()
    for i in range(1,9):
        filename = f'PHD-MAIN-REGIONFIG-v2_handover_part{i:02d}of08.zip'
        path = root/filename
        members = sorted(common+groups[i])
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for name in members:
                z.write(sources[name],name)
            z.writestr('SHA256SUMS', sums)
        assert path.stat().st_size < 25_000_000, (filename,path.stat().st_size)
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
            assert len(z.namelist()) == len(set(z.namelist()))
            assert set(z.namelist()) == set(members)|{'SHA256SUMS'}
            assert z.read('SHA256SUMS') == sums
            for name in members:
                with z.open(name) as stream:
                    assert digest_stream(stream) == hashes[name], name
            covered.update(members)
        entry = dict(part=i,file=filename,bytes=path.stat().st_size,sha256=sha(path),
                     crc='PASS',member_sha256='PASS',members=len(members),figure=i)
        parts.append(entry)
        print('ZIP',i,entry['bytes'],entry['sha256'],flush=True)
    assert covered == set(sources)
    # Catch any concurrent edit during packaging; do not silently seal mixed versions.
    assert all(sha(path)==hashes[name] for name,path in sources.items())
    report = (DOC/'영역표본그림_보고_v1.md').read_text()
    assert len(report)<15000
    receipt = dict(task_id='PHD-MAIN-REGIONFIG-v2',at=now(),status='PASS',parts=parts,
                   unique_files=len(sources),manifest_sha256=sha(root/'SHA256SUMS'),
                   report_characters=len(report),all_task_files_included=True,
                   source_files_unchanged=True,environment=environment(),scientific_verdict=None)
    dump(root/'package_receipt.json',receipt)
    host = Path('/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_regionfig_v2/PHD-MAIN-REGIONFIG-v2/handover')
    lines=['# 영역 표본 그림 v2 전달 파일','',
           '그림별 압축 파일 8개다. 모두 같은 폴더에 풀면 보고서와 모든 그림 링크가 연결된다. 각 파일은 25 MB 미만이다. 공통 파일은 같은 바이트로 중복 수록했다.','',
           '| 그림 | 전달 파일 | 크기 |','|---|---|---:|']
    for row in parts:
        lines.append(f'| {row["part"]} | [{row["file"]}]({host/row["file"]}) | {row["bytes"]/1e6:.2f} MB |')
    lines += ['',f'[전체 해시·무결성 확인 기록]({host/"package_receipt.json"})',
              f'[파일별 해시 목록]({host/"SHA256SUMS"})','',
              '수치·사진 검증 192개 통과. 압축 무결성, 내부 파일 해시, 전체 파일 포함 여부를 확인했다. 과학적 판정은 보류한다.','']
    (root/'전달파일_목록.md').write_text('\n'.join(lines))
    print('PACKAGE PASS',len(sources),'files',len(report),'report characters')


if __name__ == '__main__':
    main()
