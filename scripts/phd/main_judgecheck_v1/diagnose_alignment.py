"""Trace only unmatched development core IDs; no new photo calculation."""
import json
import zipfile
import numpy as np
from preflight import C,D,O,Path,dump,now
from prepare import array
from selected_npz import selected


def main():
    cfg=json.loads((C/'judgecheck_v1.json').read_text())
    gate=json.loads((O/'input_join.json').read_text());rows=[]
    for failure in gate['failures']:
        name=Path(failure['file']).name;tile,prior=Path(name).stem.split('__')
        with np.load(O/'inputs'/name) as z:
            mask=z['photo_point_id']=='';d={k:z[k][mask] for k in ['patch_id','building','kind','area','centre','normal','surf']}
        root=Path(cfg['sources']['roof_photo'])
        with zipfile.ZipFile(root/'geometry'/f'{tile}__{prior}__mapping.npz') as z:
            ids=array(z,'patch_id');m=np.isin(ids,d['patch_id']);mapping=dict(zip(ids[m],selected(z,'point_index',m)))
        # Read the public point identity index only; never decode another
        # building's measurements in order to diagnose an unmatched point.
        with zipfile.ZipFile(root/'points'/name) as z:
            gi=array(z,'geometry_index');bid=array(z,'building');pi=array(z,'point_id')
            matched={int(g):(str(b),str(p)) for g,b,p in zip(gi,bid,pi)}
        for i,pid in enumerate(d['patch_id']):
            owner=int(mapping.get(pid,-1));point=matched.get(owner)
            rows.append(dict(patch_id=str(pid),building=str(d['building'][i]),tile=tile,prior=prior,
                kind=int(d['kind'][i]),area_m2=float(d['area'][i]),centre=d['centre'][i].tolist(),
                normal=d['normal'][i].tolist(),surf=int(d['surf'][i]),geometry_owner_index=owner,
                mapped_point_identity=point,reason='mapping=-1' if owner<0 else ('point index absent' if point is None else 'mapped to other building ID')))
    out=dict(at=now(),status='STOP_INPUT_ALIGNMENT_UNDER_REVIEW',rows=rows,
        count=len(rows),area_m2=sum(r['area_m2'] for r in rows),scientific_verdict=None)
    dump(O/'alignment_diagnosis.json',out);dump(D/'tables/alignment_diagnosis.json',out)
    print(json.dumps(out,ensure_ascii=False))


if __name__=='__main__':main()
