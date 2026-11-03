"""Host byte-integrity audit, no project dependencies or modifications."""
from r8_screen_prepare import *
import datetime
root=O/'rfix_continue';files={}
for name in ['rfix.lock.json','rfix_continue.lock.json']:
 d=j(C/name)
 for p,h in d.get('files',{}).items():
  assert sha(local(p))==h,p;files[p]=h
for label in ['target','imageonly','geogs']:
 d=j(C/('rfix_build_'+label+'.lock.json'))
 for p,h in d['files'].items():assert sha(local(p))==h,p;files[p]=h
sealed=O/'handover/PHD-MAIN-TARGET-v1_렌더러상자고침_1103-1211.zip';assert sha(sealed)=='0d785ed5917b1c2fb4f0927ae7bfe1f8b92be8c138d1f290c4bfb7604f1a6f0c'
dump(root/'validation/immutable_inputs.json',dict(at=datetime.datetime.now().astimezone().isoformat(),status='PASS',files=len(files),files_sha256=files,previous_zip_sha256=sha(sealed),scientific_verdict=None));print('IMMUTABLE_PASS',len(files))
