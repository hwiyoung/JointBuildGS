"""Correct only the wall-plane frame of unowned rows, preserving every building."""
from common import *
from prepare import grid_area,unassigned_wall_frame
receipt=[]
for site in cfg()['sites']:
    stem=site+'__LoD2';p=O/'data'/f'{stem}.npz';d=loadz(p);core=loadz(JA/'core_points'/p.name,['kind','surf','tangent1','tangent2','normal'])
    old=d['area'].copy();before=sha(p);d=grid_area(unassigned_wall_frame(d,core,site))
    assert np.array_equal(old[d['building']!=''],d['area'][d['building']!=''])
    rows=[]
    for cc in np.unique(d['case']):
        m=d['case']==cc;total=float(d['area'][m].sum());assigned=float(d['area'][m&(d['building']!='')].sum());unassigned=float(d['area'][m&(d['building']=='')].sum());assert total==assigned+unassigned
        rows.append(dict(scene=stem,case=int(cc),scene_area_m2=total,assigned_building_area_m2=assigned,unassigned_area_m2=unassigned,difference_m2=0.,reference_rows=int(m.sum())))
    savez(p,**d);table('reconciliation_'+stem,rows);receipt.append(dict(scene=stem,previous_sha256=before,sha256=sha(p),building_areas_unchanged=True,old_unassigned_area_m2=float(old[d['building']==''].sum()),new_unassigned_area_m2=float(d['area'][d['building']==''].sum())))
    for meta in (D/'figures').glob('*.json'):
        v=json.loads(meta.read_text());changed=False
        for s in v['sources']:
            if s['path']==str(p):s['sha256']=sha(p);changed=True
        if changed:v['unassigned_projection_correction']='unowned reference rows only; all building data and displayed marks identical';dump(meta,v)
dump(D/'provenance/unassigned_projection_correction.json',dict(at=now(),rows=receipt,scientific_verdict=None));print(json.dumps(receipt))
