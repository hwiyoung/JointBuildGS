"""Small Git-owned delivery manifest for large external ZIPs."""
import json
from common import *
host=Path('/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_floatdiag_v1/PHD-MAIN-FLOATDIAG-v1')
repo=Path('/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp')
rows=[]
for stage in ['A1','A2']:
    r=json.loads((OUT/'packages'/(stage+'_package_verified.json')).read_text());p=OUT/'packages'/Path(r['file']).name
    assert sha(p)==r['sha256'] and p.stat().st_size<400000000
    rows.append(dict(group=stage,file=p.name,bytes=p.stat().st_size,sha256=r['sha256'],CRC=r['CRC'],all_member_sha256=r['all_member_sha256']))
for kind in ['geometry','arrays']:
    r=json.loads((OUT/'packages'/('payload_packages_'+kind+'.json')).read_text())
    for x in r['parts']:
        p=OUT/'packages'/x['file'];assert sha(p)==x['sha256'] and p.stat().st_size<400000000
        rows.append(dict(group=kind,file=p.name,bytes=p.stat().st_size,sha256=x['sha256'],CRC=x['CRC'],all_member_sha256='PASS'))
save(DOC/'provenance/delivery_manifest.json',dict(at=now(),external_root=str(host),archives=rows,scientific_verdict=None))
lines=['# 단계 가 전달 목록','',
    '묶음 ①을 먼저 전달했고, 묶음 ②에는 완성 진단과 두 번의 추가 확인을 담았다. 단계 나는 실행하지 않았다. 모든 ZIP은 400 MB 미만이며 CRC와 내부 파일 SHA-256을 다시 읽어 검증했다.','',
    f'[보고서]({repo}/docs/experiments/phd/main_floatdiag_v1/뜬면진단_보고_v1.md) · [인터넷 없이 여는 보기]({repo}/docs/experiments/phd/main_floatdiag_v1/보기/index.html)','',
    '| 파일 | MB | 내용 |','|---|---:|---|']
labels={'A1':'먼저 전달한 ① · 3차원 보기·캡처·영상','A2':'② · 완성 사례 판·표·보고서·코드·추가 확인','geometry':'줄이지 않은 3차원 PLY 등','arrays':'생성 과정·주 시점 힘·깊이·사진별 분류·가우시안 배열'}
for r in rows:lines.append(f"| [{r['file']}]({host}/packages/{r['file']}) | {r['bytes']/1e6:.2f} | {labels[r['group']]} |")
lines+=['','각 ZIP 옆의 `.zip.sha256`과 내부 `SHA256SUMS`로 확인할 수 있다. [전체 해시 명세](provenance/delivery_manifest.json).','',
    '기존 손실 첫 실행은 3,100회에서 건강 기준으로 멈춘 그대로 보존했다. 사용자가 승인한 재시도 한 번은 불투명도 기준만 기록 전용으로 두었으며 별도 이름으로 남겼다. R1 보존 띠의 기준을 통과하는 주 시점·빗각 실사는 확인 불가다.','',
    '단계 나의 r18, 고친 판 학습·성능 채점·묶음 ③④는 이번 범위에 없다. scientific_verdict: null.','']
(DOC/'전달_목록.md').write_text('\n'.join(lines))
print('delivery index',len(rows),'verified ZIPs')
