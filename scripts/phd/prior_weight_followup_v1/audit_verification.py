"""Validate reference identities, published model lineage, and comparison controls."""
import hashlib,json
from pathlib import Path
import numpy as np
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=Path('/payload');out=Path('/out');cfg=read(out/'config.json');m=read(out/'metrics.json')
original=read(p/cfg['viewer']/'manifest.json');controls={}
assert m['status']=='PASS_EXISTING_RESULT_DIAGNOSTIC'
for region,r in m['regions'].items():
    expected=next(c['source']['identity']['reference_sha256'] for x in original['regions'] if x['id']==region for c in x['candidates'] if c['id']=='gt')
    ref=p/cfg['reference_root']/region/'reference.npz';assert sha(ref)==expected
    raw=np.load(ref);a=np.load(out/(region+'_paired_surface.npz'));idx=a['reference_array_indices']
    assert np.array_equal(a['reference_raw_rows'],raw['uas_raw_rows'][idx])
    assert np.array_equal(a['reference_points'],raw['uas_xyz'][idx])
    for role in ['global_0005','regional_0005','regional_005']:
        d=a[role+'_distance'];assert len(d)==r['reference_count'] and np.isfinite(d).all() and (d>=0).all()
        for name,roi in r['rois'].items():
            s=a['roi_'+name];assert int(s.sum())==roi['reference_count']
            assert abs(float(d[s].mean(dtype=np.float64))-roi['surface'][role]['mean_abs'])<1e-10
    if region=='P1':
        assert np.array_equal(a['roi_roof_tip_west'].astype(int)+a['roi_roof_middle']+a['roi_roof_tip_east'],a['roi_roof_strip'].astype(int))
    er=read(p/cfg['global_extractions']/(region+'.mvs.D0005_Pnative')/'receipt.json')
    run=p/cfg['global_root']/er['job']['training_relative'];restore=read(run/'model/jbgs_restore.json')
    current=read(p/cfg['bundle']/region/'config.json');assert restore['checkpoint_sha256']==current['anchor_sha256']
    rows=[json.loads(s) for s in (run/'model/mvs_pgsr_trace.jsonl').read_text().splitlines()]
    controls[region]=dict(same_anchor=True,anchor_sha256=current['anchor_sha256'],native_protection=not restore['release'],
        global_prior_weights=sorted({x['prior_weight'] for x in rows}),global_observed_mvs_weights=sorted({x['mvs_weight'] for x in rows}),
        global_trace_rows=len(rows),regional_prior_weight=current['prior_weight'],regional_mvs_weight=current['visual_weight'],
        regional_dynamic_weight=current['dynamic_visual_weight'],global_trace_sha256=sha(run/'model/mvs_pgsr_trace.jsonl'),
        global_restore_sha256=sha(run/'model/jbgs_restore.json'),regional_config_sha256=sha(p/cfg['bundle']/region/'config.json'))
receipt=dict(status='PASS_REFERENCE_IDS_METRICS_AND_CONTROLS',scientific_verdict=None,controls=controls,
    helpers={name:sha('/repo/'+name) for name in ['scripts/phd/geogs_p1p2p3_v1/evaluation/geometry.py','src/phd/geogs_mvs_pgsr_v1/mvs_depth.py']},
    artifacts={x.name:sha(x) for x in out.glob('*.npz')},metrics_sha256=sha(out/'metrics.json'))
(out/'validation.json').write_text(json.dumps(receipt,indent=2));print(receipt['status'])
