"""Read one existing public photo-check record, without rerunning its algorithm."""
from rfcore import *

def main():
    rev='representative_v1';design=load(CFG/rev/'design.json')
    row=next(x for x in design['examples'] if x['id']=='7');pid=row['focus_patch_id']
    base=PH/'main_photocheck_v1/PHD-MAIN-PHOTOCHECK-v1';tile=pid.split(':')[1]
    patch=base/'patches'/f'{tile}__LoD2.npz';points=base/'work/full'/f'{tile}__LoD2.npz'
    with np.load(patch,allow_pickle=False) as z:
        ix=np.flatnonzero(z['patch_id']==pid);assert len(ix)==1
        point_id=z['point_id'][ix[0]];judgment=z['judgment'][ix[0],0]
    with np.load(points,allow_pickle=False) as z:
        ix=np.flatnonzero(z['point_id']==point_id);assert len(ix)==1;ix=int(ix[0])
        assert not z['holdout'][ix]
        values={k:z[k][ix] for k in ['selected_count','eligible_images','selected_images','judgment']}
    assert judgment==4 and values['judgment'][0]==4 and values['selected_count']<3
    record=dict(at=now(),patch_id=pid,point_id=point_id,values=values,
      sources=[dict(path=str(p),sha256=sha(p)) for p in [patch,points]],
      definition='features.py derive: selected_count < 3 -> judgment 4 for every candidate. The shortage may reflect selection/eligibility; physical occlusion is not established.',
      source_code='/repo/scripts/phd/main_photocheck_v1/features.py',source_code_sha256=sha('/repo/scripts/phd/main_photocheck_v1/features.py'),
      no_new_photo_check=True,scientific_verdict=None)
    dump(DOC/rev/'photo_shortage_trace.json',record);print(record,flush=True)

if __name__=='__main__':main()
