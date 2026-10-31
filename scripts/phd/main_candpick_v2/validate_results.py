"""Delivery gates: exact initial state, frozen background, bounds, area and sealing."""
import re
from scipy.spatial import cKDTree
from PIL import Image
from cp2_common import *

def main():
    cfg=config();results=[];complete=0;stopped=0
    for unit in UNITS:
        d=arrays(CP1/'places'/(unit+'.npz'));original=arrays(CP1/'scenes'/unit/'candidate_geometry.npz')
        for variant in 'abcd':
            for start in ['equal','right']:
                arm=f'cp2_{variant}_{start}_{unit}';root=OUT/'runs'/arm
                if (root/'stopped.json').exists():
                    assert variant=='c' and unit=='B173_ALS'
                    assert not (root/'candidate_0.npz').exists();stopped+=1
                    results.append(dict(arm=arm,status='STOP_UNIT_CHECK',reason='43 points missing prior uncertainty'));continue
                receipt=json.loads((root/'complete.json').read_text());assert receipt['status']=='COMPLETE'
                assert receipt['config_sha256']==sha(CFG/'candpick_v2.json')
                assert receipt['frozen_before']==receipt['frozen_after'] and receipt['frozen_unchanged']
                assert not receipt['truth_used_in_loss'] and not receipt['depth_loss_used']
                end=cfg['arms'][variant]['iterations'];assert receipt['iterations']==end
                assert sha(root/f'candidate_{end}.npz')==receipt['final_candidate_sha256']
                log=[json.loads(x) for x in (root/'metrics.jsonl').read_text().splitlines()]
                assert [r['iteration'] for r in log]==list(range(0,end+1,100))
                baseline=arrays(CP1/'runs'/f'cp_{start}_sh3_{unit}/candidate_0.npz')
                initial=arrays(root/'candidate_0.npz');latest=arrays(root/f'candidate_{end}.npz')
                ids=initial['original_ids']
                assert np.array_equal(initial['opacity'],baseline['opacity_logits'][ids])
                assert np.array_equal(initial['dc'],baseline['color_dc'][ids]) and np.array_equal(initial['rest'],baseline['color_sh'][ids])
                for k in ['means','quats','scales']:assert np.allclose(initial['geometry_'+k],original[k][ids],atol=1e-7,rtol=0)
                for step in [0,500,1000,end]:assert (root/f'candidate_{step}.npz').exists()
                if variant=='a':
                    assert len(ids)==len(d['point_id'])*4
                    front=(d['mvs_p']>0).astype(int)
                    assert np.array_equal(ids.reshape(-1,4)//4%2,np.repeat(front[:,None],4,1))
                if variant=='b':
                    warm=arrays(root/'candidate_1000.npz');assert np.array_equal(warm['opacity'],initial['opacity'])
                    assert not np.array_equal(warm['dc'],initial['dc'])
                    assert not np.array_equal(latest['opacity'],initial['opacity'])
                if variant=='c':
                    bounds=arrays(OUT/'bounds'/(unit+'.npz'))
                    delta=latest['geometry_means'].reshape(-1,2,4,3).astype(float)-d['centre'][:,None,None,:]
                    u=(delta*d['tangent1'][:,None,None,:]).sum(-1);v=(delta*d['tangent2'][:,None,None,:]).sum(-1)
                    h=(delta*d['normal'][:,None,None,:]).sum(-1)
                    heights=np.stack([np.zeros(len(u)),d['mvs_p']],1)
                    limits=1.96*np.stack([bounds['prior_sigma_m'],bounds['image_sigma_m']],1)
                    assert np.max(np.abs(u))<=.25003 and np.max(np.abs(v))<=.25003
                    assert np.all(np.abs(h-heights[:,:,None])<=limits[:,:,None]+3e-5)
                initial_error=json.loads((root/'photo_error_0.json').read_text())
                if variant!='a':
                    old_error=json.loads((CP1/'runs'/f'cp_{start}_sh3_{unit}/photo_error_0.json').read_text())
                    assert abs(initial_error['candidate_l1']-old_error['candidate_l1'])<1e-7
                complete+=1;results.append(dict(arm=arm,status='PASS',iterations=end,source=SOURCE))
    assert complete==22 and stopped==2,(complete,stopped)
    depths=list((OUT/'depth').glob('*/complete.json'));assert len(depths)==28,len(depths)
    for p in depths:
        rec=json.loads(p.read_text());data=arrays(p.parent/'points.npz')
        assert rec['depth_amendment_sha256']==sha(CFG/'depth_readout_amendment_r1.json')
        assert sha(p.parent/'points.npz')==rec['point_values']['sha256']
        assert set(np.unique(data['outcome']))<=set(['right','wrong','between_outside','unavailable'])
        for r in rec['rows']:
            assert abs(sum(r[k+'_area_m2'] for k in ['right','wrong','between_outside','unavailable'])-r['area_m2'])<1e-8
    # Public files must not contain a sealed building identity or detailed sealed judgments.
    held=set()
    for p in (JN/'holdout/core_points').glob('*.npz'):
        with np.load(p) as z:held.update(z['building'].tolist())
    leaks=[]
    for folder in [DOC,CFG,Path('/repo/scripts/phd/main_candpick_v2')]:
        for p in folder.rglob('*'):
            if p.is_file() and p.suffix in ['.json','.md','.txt','.csv','.py','.sh']:
                content=p.read_text(errors='replace')
                if any(b in content for b in held):leaks.append(str(p))
    assert not leaks,'SEALED_ID_IN_PUBLIC_FILE'
    photo_validation=json.loads((DOC/'tables/photo_validation.json').read_text())
    assert photo_validation['status']=='PASS_WITH_REPORTED_FLOAT16_LIMITATION'
    assert all(r['original_judgment_after_unchanged'] and r['new_selection_reproduced'] for r in photo_validation['rows'])
    implementation=json.loads((CFG/'photo_implementation.lock.json').read_text())
    for key in ['implementation','inherited_select']:
        b=implementation[key];assert sha(b['path'])==b['sha256'],b['path']
    b=json.loads((CFG/'photo_patch_export.lock.json').read_text())['script']
    assert sha(b['path'])==b['sha256']
    for lane in [0,1]:
        lock=json.loads((CFG/f'depth_implementation_lane{lane}.lock.json').read_text())
        for key in ['script','depth_rule']:
            b=lock[key];assert sha(b['path'])==b['sha256'],b['path']
        corrected=json.loads((CFG/f'depth_implementation_r1_lane{lane}.lock.json').read_text())
        for key in ['script','depth_rule','cuda']:
            b=corrected[key];assert sha(b['path'])==b['sha256'],b['path']
    assert json.loads((OUT/'preflight/depth_r1.json').read_text())['status']=='PASS'
    held_manifest=json.loads((DOC/'tables/holdout_counts_and_hashes.json').read_text())
    for entry in held_manifest['files']:
        assert sha(OUT/'holdout'/entry['file'])==entry['sha256'],'SEALED_FILE_HASH_CHANGED'
    figures=list((DOC/'figures').glob('*.png'));assert len(figures)>=15,len(figures)
    for p in figures:
        with Image.open(p) as im:im.verify()
        assert p.with_suffix('.json').exists()
    # Inputs and inherited implementations remain bound to their original bytes.
    for binding in cfg['input_bindings']:assert sha(binding['path'])==binding['sha256'],binding['path']
    inherited=json.loads(Path(cfg['inherited_config']['path']).read_text())
    for p,h in inherited['implementation_sha256'].items():assert sha(Path('/repo')/p)==h,p
    for p,h in cfg['training_implementation_sha256'].items():assert sha(p)==h,p
    report=dict(status='PASS_WITH_2_STOPPED_ARMS',at=now(),training_complete=complete,training_stopped=stopped,
        depth_complete=28,baseline_depth_complete=6,figures=len(figures),holdout_detail_excluded=True,
        photo_validation=photo_validation['status'],photo_implementation_unchanged=True,sealed_hashes_verified=True,
        depth_rule='corrected GeoGS readout r1; initial attempt preserved',
        source=SOURCE,scientific_verdict=None,arms=results)
    save(DOC/'tables/final_validation.json',report,replace=True);print({k:v for k,v in report.items() if k!='arms'},flush=True)

if __name__=='__main__':main()
