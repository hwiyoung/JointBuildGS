"""Independent exact-source-row/code audit; no new labels are calculated."""
from mesh_common import *
from column_store import unpack_npz
rows=[]
for prior in ['ALS','LoD2']:
    z=unpack_npz(O/'patch_table'/f'{prior}_patch_table.npz',O/'cache/validation_columns'/prior)
    for site in ['B0_b10','B173nb_b10','B173_b0','R1rep_b10']:
        ref=np.load(S1/'regions_v3'/f'regions_ext_v3_{site}_{prior}.npz');ix=z['region_source_row_'+site];m=ix>=0;q=ix[m]
        assert len(np.unique(q))==len(q)
        assert ref['in_eval'][q].all()
        assert np.all(np.linalg.norm(z['raw_centre'][m]-(ref['centre'][q]-ref['frame_shift']),axis=1)<1e-6)
        assert np.allclose(z['area'][m],ref['area'][q],rtol=1e-8,atol=1e-9)
        assert np.array_equal(z['kind'][m],ref['kind'][q])
        code=z['region_code_'+site];assigned=code>=0
        assert np.array_equal(code[assigned],ref['code_ext_v3'][ix[assigned]])
        ineval=np.array([site in str(x).split(';') for x in z['eval_region']])
        missing=ineval&~assigned
        rows.append(dict(prior=prior,site=site,status='PASS',joined_patches=int(m.sum()),assigned_patches=int(assigned.sum()),
            no_code_patches=int(missing.sum()),no_code_area_m2=float(z['area'][missing].sum()),
            reason_counts={str(k):int((missing&(z['region_unavailable_reason']==k)).sum()) for k in np.unique(z['region_unavailable_reason'][missing])}))
    conflicts=z['region_unavailable_reason_code']==4
    print(prior,'conflict rows',int(conflicts.sum()),'area',float(z['area'][conflicts].sum()))
dump(D/'tables/patch_region_join_validation.json',dict(status='PASS',rows=rows,checked_at=now(),scientific_verdict=None))
print('existing region-row/code join verification PASS')
