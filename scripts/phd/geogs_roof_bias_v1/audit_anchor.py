import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from analyze import xyz_ply
T=Path('/task');root=T/'conditions/N';p=root/'model/point_cloud/iteration_8000/point_cloud.ply';x=xyz_ply(p);prior=xyz_ply('/original_scene/lod2_pcd.ply');d,_=cKDTree(prior).query(x,workers=8);m=d<.2;r=np.load(root/'observations/actual_protection_registration.npz');native=r['mask'];rows=[json.loads(v) for v in (root/'observations/events.jsonl').read_text().splitlines()];saves=[v for v in rows if v.get('iteration')==8000];s=saves[0];assert len(x)==55413+s['added']-s['removed'];assert s['added']==s['clone_added']+s['split_added'];assert s['removed']==s['split_parents_removed']+s['culled']
receipt={'condition':'N','ply8000_total':len(x),'ply8000_proximity_protected':int(m.sum()),'actual_registration_total':len(native),'actual_registration_protected':int(native.sum()),'bookkeeping_initial_plus_added_minus_removed_matches_ply':True,'warning':'PLY precedes same-iteration densification and native mask registration','scientific_verdict':None}
(T/'provenance/anchor8000_audit.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt,indent=2))
