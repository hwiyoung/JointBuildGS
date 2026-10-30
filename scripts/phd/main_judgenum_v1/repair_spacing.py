"""Replay only the affected 0.5m sensitivity; preserve every prior result."""
import json
import shutil
from pathlib import Path
import numpy as np
import analyse as a
from lock_config import dump,sha,stamp
O=Path('/out');C=Path('/cfg');D=Path('/docs');S=Path(__file__).parent

def main():
    assert (O/'analysis_complete.json').exists()
    assert not (O/'spacing_repair_complete.json').exists()
    history=O/'revisions/spacing_r2';history.mkdir(parents=True,exist_ok=True)
    for dirname,src in [('core_points',O/'core_points'),('tables',D/'tables'),('analysis',O/'analysis')]:
        assert not (history/dirname).exists()
        shutil.copytree(src,history/dirname)
    shutil.copy2(O/'calibration.json',history/'calibration.json')
    shutil.copy2(O/'analysis_complete.json',history/'analysis_complete.json')
    dump(C/'analysis_implementation.r3.lock.json',{'at':stamp(),
      'reason':'Namespace inherited 0.5m point IDs by roof/wall photo task; no rule or base-measurement change',
      'previous_lock_sha256':sha(C/'analysis_implementation.r2.lock.json'),
      'sources':{p.name:sha(p) for p in [S/'analysis_core.py',S/'analyse.py',S/'repair_spacing.py']},
      'config_sha256':sha(C/'judgenum_v1.json'),'scientific_verdict':None})
    old_save=a.save;old_dump=a.dump;old_np_save=np.savez_compressed
    previous=json.loads((O/'calibration.json').read_text());audit=[]
    def save(name,rows,meta=None):
        if not rows:return
        p=D/'tables'/f'{name}.json'
        if p.exists() and all('scenario' in r for r in rows):
            old=json.loads(p.read_text())['rows'];rows=[r for r in old if r.get('scenario')!='spacing050']+rows
        old_save(name,rows,meta)
    def write(path,obj):
        path=Path(path)
        if path==O/'calibration.json':
            for prior,v in obj['values'].items():previous['values'][prior].update(v)
            previous['spacing_repaired_at']=stamp();old_dump(path,previous)
        elif path==O/'analysis_complete.json':old_dump(O/'spacing_replay_receipt.json',obj)
        else:old_dump(path,obj)
    def export(path,**values):
        path=Path(path)
        assert path.parent==O/'core_points'
        with np.load(path) as z:old={k:z[k] for k in z.files}
        changed={k:v for k,v in values.items() if k.startswith('spacing050_')}
        assert set(changed)=={'spacing050_judgment_after','spacing050_initial_choice','spacing050_retained','spacing050_area_m2'}
        for k,v in values.items():
            if k not in changed:
                if np.issubdtype(v.dtype,np.number):assert np.array_equal(old[k],v,equal_nan=True),k
                else:assert np.array_equal(old[k],v),k
        old.update(changed);old_np_save(path,**old)
    original_spaced=a.spaced
    def spaced(d,where,prior,cfg):
        reduced,ix=original_spaced(d,where,prior,cfg)
        for kind in [1,2]:
            before=float(d['area'][d['kind']==kind].sum());after=float(reduced['area'][reduced['kind']==kind].sum())
            assert np.isclose(before,after,rtol=0,atol=1e-7),(prior,kind,before,after)
            audit.append({'prior':prior,'kind':kind,'source_area_m2':before,'retained_area_m2':after,
              'source_cores':int((d['kind']==kind).sum()),'retained_cores':int((reduced['kind']==kind).sum())})
        return reduced,ix
    a.SCENARIOS=[s for s in a.SCENARIOS if s[0]=='spacing050'];a.save=save;a.dump=write
    a.spaced=spaced;np.savez_compressed=export
    a.main()
    np.savez_compressed=old_np_save
    old_save('spacing_group_audit',audit)
    dump(O/'spacing_repair_complete.json',{'status':'PASS','at':stamp(),'rows':audit,
      'unaffected_core_columns_identical':True,'previous_result_path':str(history),'scientific_verdict':None})
    print('SPACING_NAMESPACE_REPAIR_PASS',flush=True)

if __name__=='__main__':main()
