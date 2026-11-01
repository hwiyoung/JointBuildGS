"""Promote the compact requested diagnostic tables beside their existing figures."""
import difflib
from common import *
from report_stage0 import csvout

def main():
 root=OUT/'r7_continue/diagnostics/ALS';cross=json.loads((root/'floating_cross.json').read_text());dump(DOC/'tables/continue_r7_ALS_floating_cross.json',cross);csvout('continue_r7_ALS_floating_cross',cross['rows']);changes=json.loads((root/'changes_summary.json').read_text());dump(DOC/'tables/continue_r7_ALS_changes.json',changes);cf=[]
 for row in changes['config_differences']:cf.append({k:(json.dumps(v,ensure_ascii=False) if k in ['r6','r7'] else v) for k,v in row.items()})
 csvout('continue_r7_ALS_config_changes',cf);files=[]
 for r in changes['code_differences']:
  p=r['path'];a=REPO/'src/phd/forks/GeoGS-conf-guided-v1-r20'/p;b=REPO/'src/phd/forks/GeoGS-conf-guided-v1-r21'/p;x=a.read_text().splitlines() if a.exists() else [];y=b.read_text().splitlines() if b.exists() else [];blocks=[]
  for op,i,j,k,l in difflib.SequenceMatcher(None,x,y,autojunk=False).get_opcodes():
   if op!='equal':blocks.append(dict(kind=op,r6_start=i+1,r6_end=j,r7_start=k+1,r7_end=l))
  files.append(dict(**r,r6_lines=len(x),r7_lines=len(y),changed_blocks=blocks))
 dump(DOC/'tables/continue_r7_ALS_code_changes.json',dict(files=files,scientific_verdict=None));dump(DOC/'tables/continue_r7_ALS_counterfactual_full.json',json.loads((root/'full_pixel_enumeration_r1/summary.json').read_text()));print('DIAGNOSTIC_TABLES_PROMOTED',len(cross['rows']),len(files),flush=True)
if __name__=='__main__':main()
