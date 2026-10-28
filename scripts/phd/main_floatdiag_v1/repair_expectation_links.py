"""Correct lineage-value figure links without changing measurements or plates."""
import json
import shutil
from common import *

mapping={'B173nb_b10':'B173-뜬면-1','B0_b10':'B0-뜬면-1','R1rep_b10':'R1-뜬면-1'}
history=OUT/'history/A2_before_lineage_link_fix';history.mkdir(exist_ok=False)
paths=[DOC/'tables'/('expectations'+s) for s in ['.json','.md','.csv']]
paths += [DOC/'보기'/s for s in ['index.html','data.json','data.js']]
paths += [DOC/'provenance'/s for s in ['viewer_final_assets.json','completion_checks.json','A2_browser_QA.json']]
for p in paths:
    target=history/p.relative_to(DOC);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
for suffix in ['.json','.md','.csv']:
    p=DOC/'tables'/('expectations'+suffix)
    if suffix=='.json':
        data=json.loads(p.read_text())
        for r in data['rows']:
            if r['expectation']=='가':r['figure']='보기/img/'+mapping[r['site']]+'_plate_A2.jpg'
        p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    else:
        lines=p.read_text().splitlines()
        for i,line in enumerate(lines):
            if line.startswith('가,') or line.startswith('| 가 |'):
                for site,case in mapping.items():line=line.replace(site+'_gradients_A2_v2.jpg',case+'_plate_A2.jpg')
                lines[i]=line
        p.write_text('\n'.join(lines)+'\n')
state=json.loads((DOC/'보기/data.json').read_text())
state['expectations']=json.loads((DOC/'tables/expectations.json').read_text())['rows']
(DOC/'보기/data.json').write_text(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
(DOC/'보기/data.js').write_text('window.FLOATDIAG_DATA='+json.dumps(state,ensure_ascii=False,separators=(',',':'),allow_nan=False)+';\n')
p=DOC/'보기/index.html';lines=p.read_text().splitlines();count=0
for i,line in enumerate(lines):
    if line.startswith('<tr><td>가</td>'):
        for site,case in mapping.items():line=line.replace(site+'_gradients_A2_v2.jpg',case+'_plate_A2.jpg')
        lines[i]=line;count+=1
assert count==6
p.write_text('\n'.join(lines)+'\n')
# Preserve the undelivered first package and prior checks; make a final package.
for p in (OUT/'packages').glob('PHD-MAIN-FLOATDIAG-v1_가_셈.zip*'):shutil.move(p,history/p.name)
shutil.move(OUT/'packages/A2_package_verified.json',history/'A2_package_verified.json')
shutil.move(OUT/'qa/A2',history/'qa')
for name in ['viewer_final_assets.json','completion_checks.json','A2_browser_QA.json']:(DOC/'provenance'/name).unlink()
save(DOC/'provenance/lineage_link_revision.json',dict(at=now(),links_corrected=count,
    mapping=mapping,measurement_values_unchanged=True,plate_bytes_unchanged=True,previous_version=str(history),scientific_verdict=None))
with (DOC/'issues.md').open('a') as f:f.write('\nFD024: 최종 전달 점검에서 기대 가의 계보 비율 고리가 기울기 그림을 가리킨 것을 발견. 단위 계보 비율을 적은 사례 판으로 고쳤다. 앞 ZIP·보기·표는 history/A2_before_lineage_link_fix에 보존했고 숫자는 바꾸지 않았다.\n')
print('Six lineage links corrected; measurements and case plates unchanged')
