"""Keep the raw browser chart series in external storage; promote compact QA receipts."""
import shutil
import sys
sys.path.insert(0,'/repo/scripts/phd/main_uncert_view_v1')
from common import *

raw=OUT/'browser_details';raw.mkdir(exist_ok=True)
for name in ['browser_full.json','browser_smoke.json']:
    p=DOC/'tables'/name
    target=raw/name
    if not target.exists():shutil.copyfile(p,target)
    obj=load(p);removed=0
    for check in obj['checks']:
        for group in check.get('result',{}).get('chart',{}).get('groups',[]):
            if 'values' in group:
                values=group.pop('values');removed+=len(values)
                group.update(n=len(values),values_payload='browser_details/'+name)
    obj['raw_chart_values_external']=True
    dump(p,obj)
    print(name,removed,'display values retained outside Git')
