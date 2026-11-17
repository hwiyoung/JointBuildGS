"""Order 2.2 table: per record run, signed gradients present, gradient iterations, states / scene dumps (CPU)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum5')
from a5_common import *
RUNS = ['sa1_R1_ALS_record6000', 'sb5_R1_ALS_record_signed', 'sb2_B0_ALS_record6000', 'ba3_B0_ALS_record', 'sb1_B0_LoD2_record6000', 'tl_B0_b10_LoD2_s0', 'tl_B173nb_b10_ALS_s0', 'sb3_R1_LoD2_record', 'sc1_B173_ALS_signed', 'sc2_R1_LoD2_signed', 'sc3_B0_ALS_signed', 'sc4_B0_LoD2_signed']
rows = []
for r in RUNS:
    m = RUNS4[r]['model']; t = m/'trainlog'; g = sorted((t/'grads').glob('*.npz'), key=lambda p: int(p.stem)) if (t/'grads').exists() else []
    gz = loadz(g[-1]) if g else None; si = json.loads((t/'start.json').read_text()) if (t/'start.json').exists() else {}
    rows.append(dict(run=r, stem=RUNS4[r]['stem'], region_file=si.get('region_file'), gradient_files=len(g), first_last=f'{g[0].stem}–{g[-1].stem}' if g else None,
                     signed=bool(gz is not None and 'photo_opacity_signed' in gz), terms=sorted({k.split('_')[0] for k in gz}) if gz is not None else [],
                     states=len(list((t/'states').glob('*.npz'))) if (t/'states').exists() else 0, scene_dumps=sorted(p.stem for p in (t/'scene').glob('*.pt')) if (t/'scene').exists() else [],
                     size_gradient='기록 없음'))
table5('rec_inventory', rows); print(json.dumps(rows, ensure_ascii=False)[:3000])
