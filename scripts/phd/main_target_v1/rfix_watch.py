"""Read-only compact progress; no retries, state changes or notification service."""
import json,re
from pathlib import Path
from r8_screen_prepare import O
def read(p):return json.loads(p.read_text())
root=O/'rfix_continue';run=root/'attempt2';model=run/'runs/r8_LoD2_rfix/model'
p=run/'runs/r8_LoD2_rfix/train_receipt.json'
if p.exists():print('TRAIN_PROCESS_EXIT',read(p))
p=run/'runs/r8_LoD2_rfix/train.log'
if p.exists():
 with p.open('rb') as f:f.seek(max(0,p.stat().st_size-65536));tail=f.read().decode(errors='replace')
 progress=re.findall(r'Training progress:[^\r\n]*?([0-9]+)/15000',tail)
 if progress:print('progress_display',15000+int(progress[-1]))
p=model/'target_monitor/curve.jsonl'
if p.exists():
 v=json.loads(p.read_text().splitlines()[-1]);print('health',v['iteration'],v['gaussians'],'opacity',round(v['target_opacity_median'],6),'normal_m',v['max_normal_excess_m'])
p=model/'recording/rfix_100.jsonl'
if p.exists():
 v=json.loads(p.read_text().splitlines()[-1]);print('record',v['iteration'],'sec_per_iter',round(v['seconds_per_iteration'],3),'max_buffer_GiB',round(v['maximum_binning_bytes']/2**30,4))
print('complete_saves',[p.parent.name for p in sorted((model/'jbgs_complete').glob('*/receipt.json'))])
for name in ['STOP_LoD2.json','STOP_SAVE_FAILURE.json','TRAINING_COMPLETE.json']:
 if (run/name).exists():print(name,read(run/name))
speed=O/'rfix_speed'
for sub in ['states','gradients','addends']:
 rows=[]
 for p in sorted((speed/sub).glob('*/result.json')):rows.append(p.parent.name+':'+read(p).get('status','unknown'))
 print('speed_'+sub,str(len(rows))+' completed, validation PASS' if (speed/'VALIDATION.json').exists() else rows)
for e in ['endpoint','final_endpoint']:
 p=root/e;print(e,'tiles',len(list((p/'execution').glob('tile*.receipt.json'))),'scored',(p/'cpu_receipt.json').exists(),'verified',(p/'verification.json').exists())
 for receipt in (p/'execution').glob('*.receipt.json'):
  value=read(receipt)
  if value.get('exit_code',0)!=0:print('ENDPOINT_EXECUTION_FAILURE',str(receipt),value)
for pattern in ['measure_*_receipt.json','gradient_*_receipt.json']:
 for receipt in (speed/'execution').glob(pattern):
  value=read(receipt)
  if value.get('exit_code',0)!=0:print('SPEED_EXECUTION_FAILURE',str(receipt),value)
for p in [O/'rfix_speed/REJECTED_ADDENDS.json',root/'STOP_REQUEST.json',run/'STOP_REQUEST.json']:
 if p.exists():print('ALERT',str(p),read(p))
refine=speed/'rank_refinement'
for p in sorted((refine/'gradients').glob('*/progress.json')):
 v=read(p);print('speed_rank_progress',p.parent.name,v['completed'],v['pass_so_far'])
for p in sorted((refine/'addends').glob('*/result.json')):print('speed_rank_addends',p.parent.name,read(p)['status'])
for p in sorted((refine/'execution').glob('*receipt.json')):
 v=read(p)
 if v.get('exit_code',0)!=0:print('SPEED_RANK_FAILURE',str(p),v)
end=root/'final_endpoint'
p=end/'states/r8_LoD2_rfix/current/progress.json'
if p.exists():print('final_render_views',read(p)['completed'])
for p in sorted((end/'execution').glob('*.receipt.json')):print('final_job',p.name,read(p).get('exit_code'))
for p in [root/'released/30000_r2/result.json',root/'final_report_receipt.json',root/'validation/post15000.json']:
 if p.exists():print('post_result',p.name,read(p).get('status'))
