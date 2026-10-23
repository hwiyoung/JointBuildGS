"""Small schema/header inspection; no per-patch or prior-error values."""
import json
from pathlib import Path
import laspy
import numpy as np

P = Path('/art/phase-payloads/phd')
S = P / 'main_design_realchange_survey_v1/PHD-MAIN-DESIGN-REALCHANGE-SURVEY-v1'
for name in ['s1/rasters_als_mvs_uls.npz', 's1/rasters_lod2.npz', 'derived.npz']:
    with np.load(S / name) as z:
        print(name, z.files)
with laspy.open('/art/phase-payloads/p0-audit/data/raw/tum2twin/TUM_Downtown_ULS_20241217_nadir.laz') as f:
    print('nadir', f.header.point_count, f.header.mins.tolist(), f.header.maxs.tolist())
for p in [P/'main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1/step06/box_ranges.json',
          P/'main_stage1_v1/PHD-MAIN-STAGE1-v1/v3/align/common_shift.json']:
    obj=json.loads(p.read_text())
    print(p.name, list(obj))
    print(json.dumps(obj if 'shift' in p.name else next(iter(obj.values())), ensure_ascii=False)[:3500])
print('shapely', __import__('shapely').__version__)
