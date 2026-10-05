"""Seal stable deliverables; mutable live logs/status/receipts remain unsealed."""
import datetime,hashlib,json,subprocess
from pathlib import Path
from PIL import Image
T=Path('/task');state=json.loads((T/'status.json').read_text());names=['N','B+0.25','B+0.5','B+1.0','B-1.0'];records=[];missing=[]
required=[T/'report.md']+list((T/'tables').glob('*.csv'))+list((T/'figures').glob('*.png'))+list((T/'scripts').glob('*.py'))+list((T/'scripts').glob('*.sh'))+[T/'provenance/experiment.json',T/'provenance/original_mesh.npz',T/'provenance/reference_frame.json']
required += [p for p in [T/'report_ko.md',T/'provenance/paper_page16.txt',T/'provenance/paper_page16.png',T/'provenance/prior_roof_measurement.json',T/'provenance/checkpoint_finite_audit.json'] if p.exists()] + list((T/'assets').glob('*'))
for name in names:
 for it in [8000,30000]:
  p=T/'conditions'/name/f'model/point_cloud/iteration_{it}/point_cloud.ply'
  if p.exists():required.append(p)
  else:missing.append(str(p.relative_to(T)))
for p in required:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
 row={'path':str(p.relative_to(T)),'bytes':p.stat().st_size,'sha256':h.hexdigest()}
 if p.suffix=='.png':
  with Image.open(p) as im:im.verify()
  with Image.open(p) as im:row['pixels']=list(im.size)
 if p.suffix=='.ply':
  with p.open('rb') as f:
   while True:
    line=f.readline()
    if line.startswith(b'element vertex '):row['vertices']=int(line.split()[-1])
    if line.strip()==b'end_header':break
    if not line:raise RuntimeError('invalid PLY header '+str(p))
 records.append(row)
diff=subprocess.check_output(['git','-C',str(T/'sources/GeoGS'),'diff'],text=True);assert diff=='','Official method code changed'
manifest={'task_id':state.get('task_id',T.name),'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'execution_status':state['status'],'scientific_verdict':None,'method_source_diff_empty':True,'missing_required_checkpoints':missing,'stable_payloads':records,'unsealed_mutable_files':['status.json','runtime_status.json','logs/','condition logs and receipts'],'visual_review':'Automated PNG decode/dimension check only here; human/agent rendered inspection is separate','lineage_limitation':'Recovered CityGML is not author-OBJ byte identity; B initialization resampling differs from provided N'}
(T/'delivery_manifest.json').write_text(json.dumps(manifest,indent=2));print('Sealed',len(records),'stable files; missing checkpoints',len(missing))
