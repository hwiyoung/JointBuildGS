"""Seal completed continuation evidence and separately validated speed candidate."""
import datetime,zipfile,csv,subprocess
from r8_screen_prepare import *
ROOT=O/'rfix_continue';D=R/'docs/experiments/phd/main_target_v1/rfix_continue'
def main():
 for p in [ROOT/'validation/checkpoint_and_recording.json',ROOT/'validation/immutable_inputs.json',ROOT/'endpoint/verification.json',ROOT/'final_endpoint/verification.json',ROOT/'validation/post15000.json',ROOT/'released/15000/result.json',ROOT/'released/30000_r2/result.json',ROOT/'validation/snapshot_binding_30000.json',O/'rfix_speed/VALIDATION.json']:
  assert j(p)['status'].startswith('PASS'),p
 stop=j(ROOT/'STOP_LoD2.json') if (ROOT/'STOP_LoD2.json').exists() else None;cfg=j(C/'rfix_final.json');it=cfg['state']['iteration'];assert (D/'보고서.md').exists() and (D/'속도후보_검증.md').exists()
 files={};external={};verified={str(local(p)):v for p,v in j(ROOT/'validation/post15000.json')['verified_files'].items()}
 def digest(p):
  v=verified.get(str(p));st=p.stat()
  if v and st.st_size==v['bytes'] and st.st_mtime_ns==v['mtime_ns']:return v['sha256']
  return sha(p)
 def add(p,name):
  assert p.is_file(),p;assert name not in files,name;files[name]=p
 for p in D.rglob('*'):
  if p.is_file() and p.name!='delivery_receipt.json':add(p,'report/'+str(p.relative_to(D)))
 names=['rfix_continue','rfix_addends','rfix_speed','rfix_speed_addends','rfix_endpoint','rfix_finish','rfix_final','rfix_released','rfix_speed_rank_full','rfix_speed_rank_addends','rfix_snapshot_binding','rfix_snapshot_binding_r2','rfix_released30000_r2']
 for name in names:
  for suffix in ['.json','.lock.json']:p=C/(name+suffix);add(p,'configs/'+p.name)
 scripts=set()
 for pat in ['rfix_continue*.py','rfix_finish*.py','rfix_final*.py','rfix_released*.py','rfix_snapshot_binding*.py','rfix_post15000_audit.py','rfix_post_queue*.py','rfix_report15000.py','rfix_addends*.py','rfix_endpoint*.py','rfix_speed*.py','rfix_scope_audit.py','rfix_watch.py','rfix_verify_launch.py','rfix_ranking_audit.py','rfix_handover_continue.py']:
  scripts.update((R/'scripts/phd/main_target_v1').glob(pat))
 for p in scripts:add(p,'scripts/'+p.name)
 for p in sorted((O/'logs').glob('rfix-*.log')):
  if p.name.startswith(('rfix-report15000','rfix-checkpoint-audit','rfix-released','rfix-speed-report','rfix-rank-unit','rfix-snapshot-binding','rfix-finalreport','rfix-post15000-audit')):add(p,'cpu_logs/'+p.name)
 for root,label in [(ROOT,'continuation'),(O/'rfix_addends','approved_addends'),(O/'rfix_speed','speed_candidate')]:
  for p in sorted(root.rglob('*')):
   if not p.is_file() or '__pycache__' in p.parts:continue
   rel=p.relative_to(root);name=str(rel)
   # Native numerical metadata and compact traces travel in the ZIP; bulk arrays stay bound locally.
   selected=p.suffix in ['.json','.jsonl','.log','.patch'] and '/source/' not in '/'+name+'/'
   selected |= p.suffix=='.so' and 'builds' in rel.parts
   selected |= p.name in ['train_recorded.py','count_override.py']
   if selected and p.stat().st_size<30*1024**2:add(p,label+'/'+name)
   else:external[str(p)]=dict(bytes=p.stat().st_size,sha256=digest(p))
 # Make the preserved historical outcome visible next to the accepted amendment.
 add(O/'rfix/FINAL_STATUS.json','history/stage3_original_status.json')
 for family in ['target','imageonly','geogs']:
  for name in ['renderer.patch','receipt.json']:
   add(O/'rfix/builds'/family/name,'approved_renderer/'+family+'/'+name)
  for name in ['lock.json','result.json']:
   add(O/'rfix/units'/family/name,'approved_renderer/'+family+'/unit/'+name)
 for name in ['lock.json','result.json']:
  add(O/'rfix/extra_units/target'/name,'approved_renderer/target/near_plane_unit/'+name)
 for suffix in ['.json','.lock.json']:
  add(C/('rfix'+suffix),'history/configs/rfix'+suffix)
 previous=O/'handover/PHD-MAIN-TARGET-v1_렌더러상자고침_1103-1211.zip'
 assert sha(previous)=='0d785ed5917b1c2fb4f0927ae7bfe1f8b92be8c138d1f290c4bfb7604f1a6f0c'
 add(previous,'history/'+previous.name)
 payload=ROOT/'handover_metadata';payload.mkdir(exist_ok=False)
 dump(payload/'external_manifest.json',dict(at=datetime.datetime.now().astimezone().isoformat(),files=external,recomputation='All full states, meshes, per-pixel sparse addends and cached render arrays remain at these absolute local paths; ZIP contains controls, tables, figures and hashes, not all bulk payloads.',scientific_verdict=None));add(payload/'external_manifest.json','external_manifest.json')
 checkpoints=[]
 for run in [ROOT/'runs/r8_LoD2_rfix/model',ROOT/'attempt2/runs/r8_LoD2_rfix/model']:
  for p in run.glob('jbgs_complete/*/receipt.json'):checkpoints.append(dict(kind='scheduled_complete',path=str(p.parent),**j(p)))
 if stop:checkpoints.append(dict(kind='stop_complete',**stop))
 dump(payload/'checkpoints.json',dict(rows=checkpoints,scientific_verdict=None));add(payload/'checkpoints.json','checkpoints.json')
 hashes={name:sha(p) for name,p in files.items()};(payload/'SHA256SUMS').write_text(''.join(h+'  '+name+'\n' for name,h in sorted(hashes.items())));add(payload/'SHA256SUMS','SHA256SUMS')
 at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)));path=O/'handover'/('PHD-MAIN-TARGET-v1_r8LoD2이어학습_'+at.strftime('%m%d-%H%M')+'.zip');assert not path.exists()
 with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for name,p in sorted(files.items()):z.write(p,name)
 with zipfile.ZipFile(path) as z:
  assert z.testzip() is None
  for name,h in hashes.items():assert __import__('hashlib').sha256(z.read(name)).hexdigest()==h,name
 receipt=dict(at=at.isoformat(),task_id='PHD-MAIN-TARGET-v1',archive=str(path),archive_bytes=path.stat().st_size,archive_sha256=sha(path),crc='PASS',internal_hashes=len(hashes),external_files=len(external),completed_iteration=it,training_status=cfg['status'],speed_candidate='PASS_PREPARED_NOT_USED_IN_TRAINING',scientific_verdict=None)
 dump(D/'delivery_receipt.json',receipt);dump(ROOT/'DELIVERY.json',receipt)
 scope=sorted(set([str(p.relative_to(R)) for p in scripts]+[str(p.relative_to(R)) for p in D.rglob('*') if p.is_file()]+['configs/phd/main_target_v1/'+n+s for n in names for s in ['.json','.lock.json']]))
 dump(ROOT/'git_scope.json',dict(paths=scope,scientific_verdict=None));print('DELIVERY_SEALED',json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
