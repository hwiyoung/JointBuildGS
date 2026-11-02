"""Audit photo-point membership using IDs only, without reading score curves."""
import json
import zipfile
import numpy as np
from preflight import C,D,O,R,Path,dump,sha,now
from prepare import array


def audit():
    cfg=json.loads((C/'judgecheck_v1.json').read_text())
    j=json.loads((R/'configs/phd/main_judgenum_v1/judgenum_v1.json').read_text())
    wanted=set(cfg['scope']['development']);excluded={r['building'] for r in j['scope']['excluded']}
    rows=[];counts=[]
    for p in sorted((Path(cfg['sources']['judgenum'])/'inputs').glob('*.npz')):
        tile,prior=p.stem.split('__')
        # Source is the isolated JUDGENUM development table. Check membership
        # before loading any field other than building IDs.
        with np.load(p) as z:
            assert set(z['building'])<=wanted
            core={k:z[k] for k in ['patch_id','building','area','kind']}
        if prior=='ALS':
            core={k:v[core['kind']==1] for k,v in core.items()}
        for kind,source in [(1,cfg['sources']['roof_photo']),(2,cfg['sources']['wall_photo'])]:
            target=np.flatnonzero(core['kind']==kind)
            if not len(target):continue
            root=Path(source)
            with zipfile.ZipFile(root/'geometry'/f'{tile}__{prior}__mapping.npz') as z:
                pid=array(z,'patch_id');owners=array(z,'point_index')
            owner_lookup=dict(zip(pid,owners));own=np.array([owner_lookup[x] for x in core['patch_id'][target]])
            with zipfile.ZipFile(root/'points'/p.name) as z:
                gi=array(z,'geometry_index');point_id=array(z,'point_id');representative=array(z,'building')
                members=array(z,'building_ids') if 'building_ids.npy' in z.namelist() else representative
            total=0
            for k in np.flatnonzero(np.isin(gi,own)):
                all_members=set(str(members[k]).split(';'));nondev=all_members-wanted
                if not nondev:continue
                ii=target[own==gi[k]];total+=len(ii)
                rows.append(dict(tile=tile,prior=prior,kind=kind,point_id=str(point_id[k]),
                    geometry_index=int(gi[k]),representative_building=str(representative[k]),
                    member_buildings=sorted(all_members),development_buildings=sorted(all_members&wanted),
                    excluded_experiment_buildings=sorted(all_members&excluded),
                    other_nondevelopment_buildings=sorted(nondev-excluded),
                    selected_core_count=len(ii),selected_core_area_m2=float(core['area'][ii].sum()),
                    selected_patch_ids=core['patch_id'][ii].tolist(),
                    curve_decoded_during_initial_join=bool(representative[k] in wanted)))
            counts.append(dict(tile=tile,prior=prior,kind=kind,cross_scope_core_count=total))
    out=dict(at=now(),status='STOP_PHOTO_POINT_SCOPE_CONFLICT' if rows else 'PASS_PHOTO_POINT_SCOPE',
        reason='Inherited surface-based photo groups cross the development/excluded-building boundary',
        photo_points=len(rows),core_points=sum(r['selected_core_count'] for r in rows),
        area_m2=sum(r['selected_core_area_m2'] for r in rows),
        groups_with_curve_already_decoded=sum(r['curve_decoded_during_initial_join'] for r in rows),
        groups_with_curve_not_decoded=sum(not r['curve_decoded_during_initial_join'] for r in rows),
        affected_development_buildings=len(set(b for r in rows for b in r['development_buildings'])),
        affected_excluded_buildings=len(set(b for r in rows for b in r['excluded_experiment_buildings'])),
        rows=rows,scientific_verdict=None,source_tag='[이 발주에서 냄]',
        audit_reads='point_id, geometry_index, building, building_ids, patch_id, point_index only from inherited photo payloads',
        new_photo_scores_computed=False,new_judgments_computed=False,
        holdout_payloads_opened=False,
        identity_source_code= 'scripts/phd/main_photocheck_v1/prepare.py: group by surf/kind and tangent grid; representative by largest member area',
        identity_source_sha256=sha(R/'scripts/phd/main_photocheck_v1/prepare.py'))
    return out


def main():
    out=audit()
    dump(O/'photo_scope_audit.json',out);dump(D/'tables/photo_scope_audit.json',out)
    print(json.dumps({k:v for k,v in out.items() if k!='rows'},ensure_ascii=False))


if __name__=='__main__':main()
