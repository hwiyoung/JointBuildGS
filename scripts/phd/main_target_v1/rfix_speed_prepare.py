"""Lock speed-candidate scope before any build or measurement."""
import datetime
from r8_screen_prepare import *
root=O/'rfix_speed';root.mkdir(exist_ok=False);cfg=j(C/'rfix.json')
c=dict(at=datetime.datetime.now().astimezone().isoformat(),authority='2026-11-03 user prepare speed build only',base_config='/cfg/rfix.json',base_config_sha256=sha(C/'rfix.json'),states=cfg['states'],views=cfg['views'],small_native_rectangle_max_tiles=16,coarse_tile_edge=4,renderer_fields='registration only; radii and arithmetic kernels unchanged',training_use=False,criteria=dict(render='all outputs and radii byte equal across8x203',gradient='relative L2 <=1e-4 across8x30x7 plus per-pixel addends for20 worst unique rows/state',timing='same original, approved fixed and speed candidate in same process'),scientific_verdict=None)
dump(C/'rfix_speed.json',c);dump(C/'rfix_speed.lock.json',dict(at=c['at'],files={docker(p):sha(p) for p in [C/'rfix_speed.json',R/'scripts/phd/main_target_v1/rfix_speed_build.py']},scientific_verdict=None));print('SPEED_LOCKED',sha(C/'rfix_speed.json'))
