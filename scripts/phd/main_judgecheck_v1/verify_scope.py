"""Verify the stop using independent patch membership, not point summaries."""
import json
import zipfile
import numpy as np
from preflight import C,D,O,Path,dump,sha,now
from prepare import array


def main():
    cfg=json.loads((C/'judgecheck_v1.json').read_text());wanted=set(cfg['scope']['development'])
    audit=json.loads((O/'photo_scope_audit.json').read_text())
    rows=audit['rows'];verified=[];bytile={}
    for r in rows:bytile.setdefault((r['tile'],r['prior']),[]).append(r)
    for (tile,prior),items in bytile.items():
        p=Path(cfg['sources']['widen'])/'patch_values'/f'{tile}__{prior}__R1.5.npz'
        with zipfile.ZipFile(p) as z:
            pid=array(z,'patch_id');bid=array(z,'building')
        lookup=dict(zip(pid,bid))
        p=Path(cfg['sources']['roof_photo'])/'geometry'/f'{tile}__{prior}__mapping.npz'
        with zipfile.ZipFile(p) as z:pid=array(z,'patch_id');owner=array(z,'point_index')
        with np.load(Path(cfg['sources']['judgenum'])/'inputs'/f'{tile}__{prior}.npz') as z:
            assert set(z['building'])<=wanted
            dev_area=dict(zip(z['patch_id'],z['area']))
        for r in items:
            members=pid[owner==r['geometry_index']]
            buildings={str(lookup[p]) for p in members}
            assert buildings==set(r['member_buildings'])
            eligible={str(p) for p in members if lookup[p] in wanted}
            assert eligible==set(r['selected_patch_ids'])
            assert len(eligible)==r['selected_core_count']
            area=sum(float(dev_area[p]) for p in sorted(eligible))
            assert np.isclose(area,r['selected_core_area_m2'],atol=1e-12,rtol=0)
            verified.append(r['point_id'])
    assert len(verified)==42 and len(set(verified))==42
    assert sum(r['selected_core_count'] for r in rows)==73
    assert sha(C/'judgecheck_v1.json')==json.loads((C/'judgecheck_v1.initial.lock.json').read_text())['config_sha256']
    initial=O/'source_snapshots/initial_join/prepare.py'
    assert sha(initial)==json.loads((C/'prepare.implementation.lock.json').read_text())['sources']['prepare.py']
    result=dict(at=now(),status='PASS_STOP_EVIDENCE_VERIFICATION',
        point_groups=len(verified),core_points=73,
        area_m2=sum(r['selected_core_area_m2'] for r in rows),
        direct_member_identity_matches=True,config_lock_unchanged=True,
        initial_executed_source_hash_matches=True,
        inherited_reads='public patch_id/building and photo mapping IDs only; no photo curves',
        scientific_verdict=None)
    dump(O/'stop_verification.json',result);dump(D/'tables/stop_verification.json',result)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
