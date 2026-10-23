"""Assemble and verify the self-contained delivery; never include raw images or clouds."""
import sys
import zipfile
from common import *

def main():
    assert (PAY/'delivery_receipt.json').exists(),'Record commit/push outcome before packaging'
    target=PAY/'PHD-MAIN-REGIONFIG-v1_handover.zip'
    entries={}
    for root,prefix in [(DOC,'docs'),(CFG,'configs'),(Path('/repo/scripts/phd/main_regionfig_v1'),'scripts')]:
        for p in sorted(root.rglob('*')):
            if p.is_file():entries[prefix+'/'+p.relative_to(root).as_posix()]=p.read_bytes()
    for p in sorted((PAY/'logs').glob('*.log')):
        # The live package log receives its final message after this archive is sealed.
        if p.stat().st_size:entries['logs/'+p.name]=p.read_bytes()
    for name in ['delivery_receipt.json','config_lock.json','prepared.json','verification.json','render_receipt.json',
                 'candidates_a.json','candidates_b.json','base_commit.txt','image_id.txt']:
        entries['receipts/'+name]=(PAY/name).read_bytes()
    for d in ['pre_render_attempt1','revision_01','revision_02']:
        for p in (PAY/d).glob('*.json'):entries['receipts/history/'+d+'/'+p.name]=p.read_bytes()
    entries['README.txt']=('PHD-MAIN-REGIONFIG-v1\n'
        '그림: docs/figures/영역예시_보정.png 또는 PDF\n'
        '보고: docs/영역예시그림_보고_v1.md (두 번의 독립 검토 답 전문 포함)\n'
        '그림 제작·검증 PASS; B173 발주 값 대조 PARTIAL. 보고서의 차이 설명을 먼저 확인하십시오.\n'
        '사진 원본 조각은 docs/figures/crops/*_원본.png, 북쪽을 위로 돌린 표시는 *_표시.png.\n'
        'receipts/delivery_receipt.json에 커밋·푸시 결과가 있습니다.\n'
        '압축을 푼 폴더에서 sha256sum -c SHA256SUMS 로 검사할 수 있습니다.\n'
        '전체 원본 영상·점군·학습 결과는 포함하지 않았습니다. scientific_verdict: null\n').encode()
    sums=''.join(hashlib.sha256(blob).hexdigest()+'  '+name+'\n' for name,blob in sorted(entries.items()))
    entries['SHA256SUMS']=sums.encode();(PAY/'SHA256SUMS').write_text(sums)
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,blob in sorted(entries.items()):z.writestr(name,blob)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for line in z.read('SHA256SUMS').decode().splitlines():
            digest,name=line.split('  ',1);assert hashlib.sha256(z.read(name)).hexdigest()==digest,name
        assert not any(n.endswith(('.npz','.ply','.laz','.JPG','.jpg','.pth')) for n in z.namelist())
    rec=dict(packaged_at=now(),file=str(target),bytes=target.stat().st_size,sha256=sha(target),verified_files=len(entries)-1,
             archive_crc='PASS',member_sha256='PASS',scientific_verdict=None)
    dump(PAY/'package_receipt.json',rec)
    (PAY/(target.name+'.sha256')).write_text(rec['sha256']+'  '+target.name+'\n')
    print(json.dumps(rec,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
