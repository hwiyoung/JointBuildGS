"""Preserve previous products; unknown lineage is null, never an observed zero."""
import json
import shutil
from common import *
from reduce_diagnostics import table
history=OUT/'history/missing_lineage_display';history.mkdir(parents=True,exist_ok=False)
changed=[]
for p in sorted((DOC/'tables').glob('*.json')):
    data=json.loads(p.read_text());rows=data.get('rows',[]) if isinstance(data,dict) else []
    if not rows or not isinstance(rows[0],dict):continue
    edits=0
    for r in rows:
        if r.get('result')=='nojudge_ALS_s0':
            for key in ['densified_opacity_fraction','initial_prior_opacity_fraction','initial_image_opacity_fraction']:
                if key in r and r[key] is not None:r[key]=None;edits+=1
    if not edits:continue
    for ext in ['.json','.csv','.md']:
        old=p.with_suffix(ext)
        if old.exists():shutil.move(old,history/old.name)
    table(p.with_suffix(''),rows,data.get('caption','계보 기록 없음은 null로 표시'))
    # Retain all original source provenance, not just tabular rows.
    if 'inputs' in data:
        new=json.loads(p.read_text());new['inputs']=data['inputs'];p.write_text(json.dumps(new,ensure_ascii=False,indent=2)+'\n')
    changed.append(dict(file=str(p),fields=edits))
for p in list((DOC/'figures').glob('*_plate_A2.*'))+list((DOC/'보기/img').glob('*_plate_A2.jpg'))+list((DOC/'보기').glob('A2_*.json')):
    target=history/str(p.relative_to(DOC));target.parent.mkdir(parents=True,exist_ok=True);shutil.move(p,target)
save(DOC/'provenance/missing_lineage_display_repair.json',dict(at=now(),changed=changed,reason='Original lineage membership unrecorded=1; known categories must be null, not zero. Counts and geometry unchanged; prior tables preserved.',scientific_verdict=None))
print('unknown lineage display repaired',len(changed),'tables; prior A2 plates preserved')
