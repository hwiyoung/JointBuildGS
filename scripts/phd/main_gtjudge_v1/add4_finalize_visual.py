"""Explicit MVS filenames and a non-delivery inspection sheet."""
from add4_common import *
import shutil
# Metadata clarification only: virtual-camera elevation is its optical axis toward the context centre.
for c in AC['cases'][:3]:
 cp=AW/'cases'/f"{c['id']}.json";rec=json.loads(cp.read_text());rec['camera']['angle_definition']='synthetic_optical_axis_elevation_frozen_gravity';dump(cp,rec)
 files=sorted(AF.glob(c['id']+'*.json'))+sorted((AF/c['id']).glob('*.json'))
 files=sorted(files,key=lambda p:p.name.endswith('_section.json'))
 for p in files:
  meta=json.loads(p.read_text())
  if 'camera' in meta:meta['camera']=rec['camera']
  if 'sources' in meta:meta['sources']=[proof(x['path']) for x in meta['sources']]
  dump(p,meta)
 projection=AW/'cameras'/f"{c['id']}_projection.json";j=json.loads(projection.read_text());j['camera']=rec['camera'];dump(projection,j)
for p in AF.glob('site_*.json'):
 j=json.loads(p.read_text());j['sources']=[proof(x['path']) for x in j['sources']];dump(p,j)
for c in AC['cases'][:3]:
 p=AF/f"{c['id']}_oblique.png";out=AF/f"{c['id']}_context_MVS.png";meta=json.loads(p.with_suffix('.json').read_text());assert meta['photograph'] is False
 shutil.copyfile(p,out);meta['delivery_role']='primary context view: colored MVS, not a photograph';dump(out.with_suffix('.json'),meta)
 if c['id'].startswith('c3'):
  cut=AF/f"{c['id']}_context_MVS_cutaway.png";shutil.copyfile(out,cut);meta['delivery_role']='local MVS cutaway; surrounding geometry outside camera.display_clip is omitted; not a photograph';dump(cut.with_suffix('.json'),meta)
canvas=Image.new('RGB',(1800,1440),'white')
for row,c in enumerate(AC['cases'][:3]):
 for col,tag in enumerate(['context_MVS','wrong_gray','wrong_dist']):
  im=Image.open(AF/f"{c['id']}_{tag}.png").convert('RGB');im.thumbnail((600,480),Image.Resampling.LANCZOS);canvas.paste(im,(col*600+(600-im.width)//2,row*480+(480-im.height)//2))
p=AW/'verification/context_repair_preview.png';canvas.save(p,icc_profile=ICC);print(str(p),flush=True)
