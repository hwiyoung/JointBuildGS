from common import *
import sys
sys.path.append('/repo/scripts/phd/main_rescore_v1')
from figures import section_points
g=loadz(O/'stage1/R1rep_b10__ALS/gaussians.npz',['xyz'])
for cell in [2,4]:
 p=D/'figures/stage1'/f'cell{cell}_section.json';r=json.loads(p.read_text());q=section_points(g['xyz'],r['place']);lo,hi=r['y_range'];r['gaussian_centres_in_xy_section']=len(q);r['gaussian_centres_outside_displayed_z']=int(((q[:,1]<lo)|(q[:,1]>hi)).sum());r['z_extent_rule']='all plotted mesh intersections, GT and target intervals plus 0.5 m; centres beyond that range counted explicitly';r['gaussians_sha256']=sha(O/'stage1/R1rep_b10__ALS/gaussians.npz');r['target_sha256']=sha(FT/'targets/R1rep_b10__ALS.npz');r['visual_review']='PASS: readable axes and legend, data-backed surfaces and centres';dump(p,r)
for cell in [2,4]:
 p=D/'figures/stage1'/f'cell{cell}_map.json';r=json.loads(p.read_text());r['visual_review']='PASS: equal coordinate extents, legible two-panel legend, frozen section line';dump(p,r)
dump(O/'verification/visual_stage1.json',dict(at=now(),figures=4,status='PASS',reviewer='Codex image inspection',scientific_verdict=None))
