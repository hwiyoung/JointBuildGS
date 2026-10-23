"""Correct inventory denominator to submitted MVS images; preserve the earlier estimate."""
import json
from pathlib import Path
from preflight import PREP,dump
O,D=Path('/out'),Path('/docs')
p=O/'input_preflight.json';audit=json.loads(p.read_text())
if 'previous_mvs_estimate' in audit:raise SystemExit('already revised')
audit['previous_mvs_estimate']=audit['mvs_estimate'].copy()
total=0
for row in audit['sites']:
    subset=PREP/'mvs'/('box_'+row['site'])/'subset.json'
    submitted=json.loads(subset.read_text())['n_views']
    row['mvs_submitted_images']=submitted
    row['mvs_subset_source']=str(subset)
    if row['receipt'] and row['receipt']['exit_code']==0:total+=submitted
rate=audit['mvs_estimate']['seconds']/total
audit['mvs_estimate'].update(selected_images=total,seconds_per_selected_image=rate,
    provisional_all_posed_images_single_gpu_hours=937*rate/3600,
    provisional_global_training_single_gpu_hours=819*rate/3600,
    provisional_global_training_two_gpu_ideal_hours=819*rate/7200,
    correction='Original denominator 919 counted Stage-1 available training depths. Submitted COLMAP inputs were 924: R1 338 inputs, 333 output depths. Earlier estimate retained.')
dump(p,audit);dump(D/'tables/input_preflight.json',audit)
ip=D/'tables/image_inventory.json';im=json.loads(ip.read_text());old=im['mvs_estimate'].copy()
im['previous_mvs_estimate']=old
im['mvs_estimate'].update(seconds_per_image=rate,single_gpu_hours=819*rate/3600,two_gpu_ideal_hours=819*rate/7200,
    source='four completed COLMAP runs; 924 submitted input images, 11205 seconds; subset.json verified',over_48_hours=False)
dump(ip,im)
print(json.dumps(dict(before=old,after=im['mvs_estimate']),indent=2))
