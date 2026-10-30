"""Self-verifying public delivery ZIPs. No holdout values or legacy revisions."""
import hashlib
import json
import os
from pathlib import Path
import zipfile
from lock_config import dump,sha,stamp
O=Path('/out');D=Path('/docs');C=Path('/cfg');S=Path(__file__).parent

def main():
    assert json.loads((O/'ready_for_handover.json').read_text())['status']=='VERIFIED_WITH_RECORDED_UNAVAILABLE_INPUTS'
    assert json.loads((O/'final_validation.json').read_text())['status']=='PASS'
    common=[]
    for root,prefix in [(D,'docs/experiments/phd/main_judgenum_v1'),(C,'configs/phd/main_judgenum_v1'),(S,'scripts/phd/main_judgenum_v1')]:
        for p in sorted(root.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:common.append((p,f'{prefix}/{p.relative_to(root)}'))
    for name in ['calibration.json','stage_a_verification.json','analysis_verification.json','spacing_repair_complete.json','final_validation.json']:
        common.append((O/name,'receipts/'+name))
    manifest={'task_id':'PHD-MAIN-JUDGENUM-v1','at':stamp(),'commit':os.environ.get('JUDGENUM_COMMIT'),
      'config_sha256':sha(C/'judgenum_v1.json'),'calibration_sha256':sha(O/'calibration.json'),
      'report_sha256':sha(D/'판단숫자셈_보고_v1.md'),
      'scope':'development only, evaluation buildings excluded; holdout only counts/area/hash in public tables',
      'recomputation_boundary':'Full ZIP core arrays support judgment/selection/error recomputation. Complete cylinder or photo projection replay additionally requires the exact locked external MVS/patch/photo sources; these raw sources are not bundled.',
      'scientific_verdict':None}
    dump(O/'handover_manifest.json',manifest);common.append((O/'handover_manifest.json','handover_manifest.json'))
    core=[(p,'core_points/'+p.name) for p in sorted((O/'core_points').glob('*.npz'))]
    receipts=[]
    for suffix,files in [('_light',common),('',common+core)]:
        output=O/f'PHD-MAIN-JUDGENUM-v1_handover{suffix}.zip'
        assert not output.exists(), 'Preserve previous archive; do not silently overwrite'
        assert all(not name.startswith('holdout/') for _,name in files)
        sums=''.join(sha(p)+'  '+name+'\n' for p,name in files)
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
            for p,name in files:z.write(p,name)
            z.writestr('SHA256SUMS',sums)
        assert output.stat().st_size<399000000, 'Archive exceeds locked limit; split into independently verified parts'
        with zipfile.ZipFile(output) as z:
            assert z.testzip() is None
            for line in z.read('SHA256SUMS').decode().splitlines():
                digest,name=line.split('  ',1);h=hashlib.sha256()
                with z.open(name) as f:
                    for chunk in iter(lambda:f.read(4<<20),b''):h.update(chunk)
                assert h.hexdigest()==digest,name
            count=len(z.namelist())
        receipts.append({'file':output.name,'bytes':output.stat().st_size,'sha256':sha(output),'members':count,'CRC':'PASS','internal_sha256':'PASS'})
        print('ARCHIVE_VERIFIED',output.name,output.stat().st_size,flush=True)
    (O/'SHA256SUMS').write_text(''.join(r['sha256']+'  '+r['file']+'\n' for r in receipts))
    dump(O/'delivery_receipt.json',{'task_id':'PHD-MAIN-JUDGENUM-v1','at':stamp(),'status':'PASS',
      'commit':os.environ.get('JUDGENUM_COMMIT'),'files':receipts,'holdout_payloads_included':False,
      'report_characters':len((D/'판단숫자셈_보고_v1.md').read_text()),'scientific_verdict':None})

if __name__=='__main__':main()
