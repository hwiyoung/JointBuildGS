"""Inspect inherited building identity before final roof-extent selection."""
from add6_common import *
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
raw={b['id']:b for b in json.loads((PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2/inputs/lod2_buildings.json').read_text())}

for c in AC['cases']:
 core=loadz(JA/'core_points'/f"{c['site']}__{c['prior']}.npz")
 row=loadz(root_of(c)/'rows.npz');lab=loadz(root_of(c)/'stage1_cells.npz')['case_id'];own=row['row_owner'];mask=(own>=0)&(lab==c['case_id'])
 b,n=np.unique(core['building'][own[mask]],return_counts=True)
 print(c['id'],'case buildings',list(zip(b.tolist(),n.tolist())),flush=True)
 s=selected(c)['section'];m=section_mask(row['xyz'],s)&mask;b,n=np.unique(core['building'][own[m]],return_counts=True)
 print('selected strip buildings',list(zip(b.tolist(),n.tolist())),flush=True)
 bid=selected(c)['selection']['building_identity'];poly=unary_union([Polygon(np.asarray(x['ext'])[:,:2]-SHIFT[:2],[np.asarray(h)[:,:2]-SHIFT[:2] for h in x['holes'] if len(h)>3]).buffer(0) for x in raw[bid]['surfaces']['ground']]);print('endpoint distance to own footprint',[poly.distance(Point(x)) for x in [s['start'],s['end']]],'footprint bounds',poly.bounds,flush=True)
 t=loadz(FT/'targets'/f"{c['site']}__{c['prior']}.npz");print('target keys',list(t),flush=True)
