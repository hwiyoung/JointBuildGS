"""Read-only inherited numerical definitions; task-owned output paths."""
import json
from pathlib import Path
W=Path('/art/phase-payloads/phd/main_widen0_v2/PHD-MAIN-WIDEN0-v2')
CFG=json.loads(Path('/repo/configs/phd/main_widen0_v2/widen0_v2.json').read_text())
CFG['seed']=CFG['split']['seed'];D=CFG['definitions']
SITE_ID={t['id']:i for i,t in enumerate(json.loads((W/'inputs/tiles.json').read_text()))}
SET_ID={'LoD2':0,'ALS':1};DATA_ID={'mvs_a':0,'als':2,'gt':3};R_ID={1.5:1}
PTS=W/'holdout/internal/points'
WORK=Path('/out/r1/ring_recompute');WORK.mkdir(parents=True,exist_ok=True)
