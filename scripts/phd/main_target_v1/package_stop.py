"""Seal the stopped-stage evidence, never label this as a completed training delivery."""
import os
import zipfile
import hashlib
from common import *


def main():
    _,lock=locked()
    audit=json.loads((OUT/'input_audit.json').read_text())
    verification=json.loads((OUT/'stop_verification.json').read_text())
    assert audit['status']=='STOP_STAGE0' and verification['status']=='PASS_STOP_EVIDENCE'
    assert not audit['training_started'] and not audit['holdout_accuracy_opened']
    visual={'at':stamp(),'status':'REVIEWED','review':'Three exported PNGs viewed by the agent; labels and missingness marks visible; no user visual acceptance claimed',
            'files':[{'path':p.name,'sha256':sha(p)} for p in sorted((DOC/'figures').glob('*.png'))],
            'scientific_verdict':None}
    dump(DOC/'tables/visual_review.json',visual)
    roots=[(CFG,'configs/phd/main_target_v1'),(Path(__file__).parent,'scripts/phd/main_target_v1'),(DOC,'docs/experiments/phd/main_target_v1')]
    members={}
    for root,prefix in roots:
        for p in sorted(root.rglob('*')):
            if p.is_file() and p.name!='delivery_receipt.json':
                assert '__pycache__' not in p.parts
                members[prefix+'/'+p.relative_to(root).as_posix()]=p
    for p in sorted((OUT/'input_audit').glob('*.npz')):
        members['payload/input_audit/'+p.name]=p
    for name in ['input_audit.json','stop_verification.json']:
        members['payload/'+name]=OUT/name
    assert not any('/holdout/' in name or '/runs/' in name for name in members)
    manifest={'task_id':'PHD-MAIN-TARGET-v1','status':'STOP_STAGE0','at':stamp(),
              'config_sha256':lock['config_sha256'],'source_commit_before_task':os.environ['TARGET_COMMIT'],
              'members':[{'path':n,'bytes':p.stat().st_size,'sha256':sha(p)} for n,p in members.items()],
              'recomputation_boundary':'Input audit only; requires read-only external UNCERT and stage0/stage1 payloads. No training, target, mesh or accuracy results.',
              'holdout_patch_details_included':False,'scientific_verdict':None}
    folder=OUT/'handover';folder.mkdir(exist_ok=True)
    name='PHD-MAIN-TARGET-v1_결과_'+dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%m%d-%H%M')+'.zip'
    dest=folder/name
    assert not dest.exists()
    hashes=''.join(f"{m['sha256']}  {m['path']}\n" for m in manifest['members'])
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for n,p in members.items():z.write(p,n)
        z.writestr('MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        z.writestr('SHA256SUMS',hashes)
        z.writestr('README.txt','STOP_STAGE0: 입력 조건 미충족으로 학습하지 않았습니다. 보고서·표·그림·검산과 재현 스크립트의 전달 묶음입니다. scientific_verdict: null.\n')
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        for m in manifest['members']:
            assert hashlib.sha256(z.read(m['path'])).hexdigest()==m['sha256']
    receipt={'task_id':'PHD-MAIN-TARGET-v1','at':stamp(),'status':'PASS_ARCHIVE_INTEGRITY',
             'experiment_status':'STOP_STAGE0','zip_path':str(dest),'zip_name':name,'bytes':dest.stat().st_size,
             'sha256':sha(dest),'crc':'PASS','member_sha256':'PASS','members_checked':len(members),
             'source_commit_before_task':os.environ['TARGET_COMMIT'],'scientific_verdict':None}
    dump(DOC/'delivery_receipt.json',receipt);dump(folder/'delivery_receipt.json',receipt)
    dest.with_suffix('.zip.sha256').write_text(f"{sha(dest)}  {dest.name}\n")
    print(json.dumps(receipt,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
