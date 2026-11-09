from common import *
paths=[FT/'targets'/f'{STEM}.npz',FT/'stage1'/STEM/'seeds.npz',MODEL/'target_monitor/snapshot_7000.npz',GT/'scenes'/STEM/'rows.npz',GT/'scenes'/STEM/'stage1_cells.npz',S1/'defs'/SITE/'prior_ALS.npz']
result={}
for p in paths:
 with np.load(p) as z:result[str(p)]={k:dict(shape=list(z[k].shape),dtype=str(z[k].dtype)) for k in z.files}
outline=R/'docs/experiments/phd/main_gtjudge_v1/tables/addendum10/c1_outline.geojson'
result['outline']=json.loads(outline.read_text())
for label,p in [('case',GT/'addendum4/cases'/f'{CASE}.json'),('selection',GT/'addendum6/selected'/f'{CASE}.json'),('section',R/'docs/experiments/phd/main_gtjudge_v1/figures/addendum6'/f'{CASE}_section_data.json')]:
 v=json.loads(p.read_text());result[label]={k:v[k] for k in v if k in ['section','line','box_corners_xy','selection','line_xyz']}
dump(O/'work/probe.json',result)
print('PROBE_SAVED')
