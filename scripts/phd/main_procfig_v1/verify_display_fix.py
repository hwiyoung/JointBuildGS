from common import *
from PIL import Image
c=cfg();assert c['rendering']['wrong_lineage_always_visible_in_threshold_selection'] is False;rows=[]
for it in c['iterations']:
 g=loadz(O/'gaussians'/f'{it}.npz');take=g['opacity']>=.1;p=O/'figures'/f'proc_{it}_1_d.png';m=json.loads(p.with_suffix('.json').read_text());a=json.loads((O/'figures'/f'proc_{it}_1_a.json').read_text());assert m['gaussians_drawn']==int(take.sum());assert m['wrong_lineage_gaussians']==int((take&(g['group33']==1)).sum());assert m['camera']==a['camera'];assert m['display_fix1_sha256']==c['display_fix1_sha256']
 with Image.open(p) as im:im.load();assert im.width>=1600 and im.info.get('icc_profile')
 rows.append(dict(iteration=it,gaussians_drawn=int(take.sum()),wrong_lineage_drawn=int((take&(g['group33']==1)).sum()),below_threshold_excluded=True,png_sha256=sha(p)))
v=json.loads((D/'verification.json').read_text());v['display_fix1']=dict(status='PASS',rows=rows,config_sha256=c['display_fix1_sha256']);dump(D/'verification.json',v)
visual=json.loads((D/'visual_check.json').read_text());visual['display_fix1']='Only d threshold selection changed after the single contact-sheet inspection; four regenerated PNGs decoded and exact included-row counts checked; no second visual inspection.';dump(D/'visual_check.json',visual)
print('DISPLAY_FIX_VERIFIED',len(rows))
