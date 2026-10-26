"""Correct ALS surface-grid grouping, retaining invalid outputs and original receipts."""
from common import *
def main():
    cfg=load(C/'photocheck_v1.json')
    if any(x.get('id')=='als_surface_origin' for x in cfg['amendments']):return
    previous=sha(C/'photocheck_v1.json');dump(C/'photocheck_v1_r1.json',cfg);dump(C/'photocheck_v1_r1.lock.json',load(C/'photocheck_v1.lock.json'))
    cfg['amendments'].append(dict(id='als_surface_origin',at=now(),previous_sha256=previous,reason='Code audit found 105 development ALS faces spanning buildings. Correct grouping to the requested same-surface grid instead of restarting its origin per building. No GT or curve outcome was used to choose this correction. Existing ALS group outputs invalidated. LoD2 faces each belong to one building, so its computed geometry and curves are unchanged.',previous_points=cfg['points'].copy()))
    cfg['points']['group']='same tile, surface and kind, within each sealed split; ALS origin shared across all buildings and both splits of that surface'
    cfg['points']['grid']='LoD2 normalized source tangents and face minimum; ALS XY minimum of all regular inherited patches on that tile/surface/kind; floor((coord-origin)/0.5+1e-7)'
    cfg['points']['building']='largest contributing area as primary building; ALS building_ids records every contributor; patch-level tables retain each original building; shared-cell split at development/holdout boundary only'
    cfg['points']['grid_check']=cfg['points']['grid_check'].replace('same surface/building/kind','same surface/kind/split')
    dump(C/'photocheck_v1.json',cfg);new=sha(C/'photocheck_v1.json');dump(C/'photocheck_v1.lock.json',dict(at=now(),sha256=new,previous_sha256=previous,amendment='als_surface_origin',before_corrected_ALS_curves=True,environment=env()))
    for sealed in [False,True]:
        base=paths(sealed);invalid=base/'invalidated_building_groups';invalid.mkdir(exist_ok=True)
        for sub in ['geometry','work/pilot']:
            root=base/sub
            if not root.exists():continue
            dest=invalid/sub;dest.mkdir(parents=True,exist_ok=True)
            for p in root.glob('*__ALS*'):p.rename(dest/p.name)
        if not sealed:
            for p in (base/'work/pilot').glob('*__LoD2.json'):
                r=load(p);r['compatible_configuration_sha256']=[new];r['compatibility_reason']='ALS-only grid correction; this LoD2 computation has identical geometry, uncertainty, photographs, score and decision rules';dump(p,r)
    dump(O/'gates/surface_group_correction.json',dict(previous_sha256=previous,corrected_sha256=new,at=now(),LoD2_geometry_unchanged=True,ALS_outputs_invalidated=True,scientific_verdict=None))
    print('surface grouping correction locked',new)
if __name__=='__main__':main()
