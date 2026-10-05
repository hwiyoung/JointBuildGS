"""Atomically expose each finished prior comparison using the original masks."""
import copy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path

def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
bundle,viewer=Path('/bundle'),Path('/viewer')
value=read(bundle/'baseline_manifest.json');out=viewer/'prior_weights_v1'
newrole='prior_0005_alpha4';done=[];states={}
for region in ['P1','P2','P3']:
    root=bundle/region;status=(root/'status.txt').read_text().strip();states[region]=status
    file=out/region/'alpha_4/publication.json'
    publication=read(file) if file.exists() else None
    if publication:
        train=read(root/'train/alpha_4/receipt.json');extraction=read(out/region/'alpha_4/extraction/receipt.json')
        assert train['status']==extraction['status']=='PASS'
        assert publication['status']=='PASS_INDIVIDUAL_FINAL_DISPLAY'
        assert publication['provenance']['prior_weight']==.0005
        assert publication['provenance']['training_receipt_sha256']==sha(root/'train/alpha_4/receipt.json')
        assert publication['provenance']['extraction_receipt_sha256']==sha(out/region/'alpha_4/extraction/receipt.json')
        assert publication['provenance']['mask_sha256']==read(root/'config.json')['mask_sha256']
        done.append(region)
    for row in value['regions']:
        if row['id'].split('_')[0]!=region:continue
        old=next(c for c in row['conditions'] if c['id']=='alpha_4')
        old['label']='Prior 0.005 · R1=4'
        current=dict(id=newrole,label='Prior 0.0005 · R1=4',scientific_verdict=None)
        if publication:
            current.update(status='available',mesh=publication['regions'][row['id']]['mesh'],provenance=publication['provenance'])
        else:current.update(status='failed' if status.startswith('FAIL') else 'pending',reason=status)
        row['conditions']=[old,current]
        for view in row['views']:
            baseline=view['conditions']['alpha_4']
            new=publication['views'][view['id']] if publication else {k:current[k] for k in ['status','reason']}
            view['conditions']={'alpha_4':baseline,newrole:new}
value.update(schema='prior_weight_comparison_v1',scientific_verdict=None,generated_at=datetime.now(timezone.utc).isoformat(),
             run_status=dict(completed=len(done),total=3,regions=states,label=f'prior 0.0005 최종 결과 {len(done)}/3 등록 · 완료 순서대로 표시'),
             completion=[dict(region=r,prior=.0005,alpha=4,iteration=30000) for r in done])
tmp=out/f'manifest.{os.getpid()}.tmp';tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2));os.replace(tmp,out/'manifest.json')
print(json.dumps(value['run_status'],ensure_ascii=False))
