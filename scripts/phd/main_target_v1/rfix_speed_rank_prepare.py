"""Preserve incomplete ranking evidence and freeze the bounded refinement."""
import datetime
from r8_screen_prepare import *
root=O/'rfix_speed/rank_refinement';root.mkdir(exist_ok=False)
cfg=dict(at=datetime.datetime.now().astimezone().isoformat(),states=['r8_LoD2_stop','GeoGS_LoD2_30000'],reason='Old top8-per-chunk/top16 summaries cannot prove membership for two states; retain old results and repeat saved-state gradients with exact global64 per view and parameter.',selection='same30 frozen views and losses; select20 distinct rows by maximum absolute difference, then row, camera, parameter',ranking='65 rows per chunk; exact global64 and65th row; delta descending then row ascending',optimization_steps=0,training_use=False,scientific_verdict=None)
dump(C/'rfix_speed_rank_full.json',cfg)
paths=[C/'rfix_speed_rank_full.json',C/'rfix_speed.json',C/'rfix.json',R/'scripts/phd/main_target_v1/rfix_speed_rank_full.py',R/'scripts/phd/main_target_v1/rfix_gradient.py']
paths+=list((O/'rfix_speed/builds').glob('*/extension/*.so'))
dump(C/'rfix_speed_rank_full.lock.json',dict(at=cfg['at'],files={docker(p):sha(p) for p in paths},scientific_verdict=None))
dump(root/'previous_ranking_failure.json',dict(at=cfg['at'],status='INSUFFICIENT_RANKING_SUMMARY',rows=[dict(state='r8_LoD2_stop',selected20th_delta=5.960464477539063e-08,omitted_upper_bound=5.960464477539063e-08),dict(state='GeoGS_LoD2_30000',selected20th_delta=4.7497451305389404e-08,omitted_upper_bound=6.984919309616089e-08)],old_results_preserved=True,criterion_failure=False,scientific_verdict=None))
print('RANK_REFINEMENT_LOCKED',sha(C/'rfix_speed_rank_full.json'))
