"""Join eligible patches to existing photo judgments; never run photo scoring."""
import json
from pathlib import Path
import time
import zipfile
import numpy as np
from lock_config import dump, sha, stamp
from selected_npz import selected, building_ids
C=Path('/cfg'); O=Path('/out'); D=Path('/docs')

def read_array(z,key):
    with z.open(key+'.npy') as f:return np.lib.format.read_array(f,allow_pickle=False)

def main():
    t0=time.monotonic();cfg=json.loads((C/'judgenum_v1.json').read_text())
    assert json.loads((O/'sample_gate.json').read_text())['status']=='PASS_SAMPLE_GATE'
    assert sha(C/'judgenum_v1.json')==json.loads((C/'judgenum_v1.lock.json').read_text())['config_sha256']
    W=Path(cfg['sources']['widen']);wanted=cfg['scope']['development']
    (O/'inputs').mkdir(exist_ok=True);rows=[];fail=[]
    for p in sorted((O/'scope_selection').glob('*.npz')):
        tile,prior,_=p.stem.split('__');src=W/'patch_values'/p.name
        with np.load(p) as z:base={k:z[k] for k in z.files}
        if not len(base['patch_id']):continue
        with zipfile.ZipFile(src) as z:
            bids=building_ids(z);mask=np.isin(bids,wanted)
            keys=['normal','tangent1','tangent2','surf','roof_type','source_extra','normal_defined','u_prior','mvs_a_a','mvs_p','gt_p']
            data={**base,**{k:selected(z,k,mask) for k in keys}}
        assert np.isfinite(data['centre']).all()
        judgments=np.full((len(base['patch_id']),15),2,np.int8);missing=np.ones(len(judgments),bool)
        for kind,source in [(1,cfg['sources']['roof_photo']),(2,cfg['sources']['wall_photo'])]:
            target=np.flatnonzero(data['kind']==kind)
            if not len(target) or (kind==2 and prior=='ALS'):continue
            photo=Path(source)/'patches'/f'{tile}__{prior}.npz'
            if not photo.exists():
                fail.append({'tile':tile,'prior':prior,'kind':kind,'reason':'photo patch judgment file not found','path':str(photo)})
                continue
            with zipfile.ZipFile(photo) as z:
                ids=read_array(z,'patch_id');pm=np.isin(ids,data['patch_id'][target])
                picked=ids[pm];values=selected(z,'judgment',pm)
            assert len(set(picked))==len(picked) and values.shape==(len(picked),15)
            assert np.isin(values,[0,1,2,3,4]).all()
            lookup={q:i for i,q in enumerate(data['patch_id'])}
            dst=np.array([lookup[q] for q in picked],np.int64)
            judgments[dst]=values;missing[dst]=False
        data['photo_judgments']=judgments;data['photo_missing']=missing
        # Preserve inherited unavailable prior sigma. No value substitution.
        sigma=np.sqrt(np.asarray(data['u_prior'],float)**2+.0275**2)
        if prior=='LoD2':
            sigma=np.array([cfg['detection']['prior_sigma']['LoD2_roof'].get(str(rt),.11) for rt in data['roof_type']])
            sigma[data['kind']==2]=.144
        data['sigma_p']=sigma
        dest=O/'inputs'/f'{tile}__{prior}.npz';np.savez_compressed(dest,**data)
        mvs=W/'holdout/internal/points'/tile/'mvs_a_xyz.npy'
        if not mvs.exists():fail.append({'tile':tile,'prior':prior,'reason':'training MVS points missing','path':str(mvs)})
        else:
            mm=np.load(mvs,mmap_mode='r',allow_pickle=False)
            assert mm.ndim==2 and mm.shape[1]==3
        rows.append({'tile':tile,'prior':prior,'patches':len(judgments),
          'photo_missing_count':int(missing.sum()),'photo_missing_area_m2':float(data['area'][missing].sum()),
          'undefined_normal_count':int((~data['normal_defined']).sum()),
          'missing_prior_sigma_count':int((~np.isfinite(sigma)).sum()),
          'mvs_points':len(mm) if mvs.exists() else None,
          'source':str(src),'input_sha256':sha(dest)})
        print(tile,prior,'patches',len(judgments),'photo missing',int(missing.sum()),flush=True)
    dump(O/'input_join.json',{'status':'STOP_INPUT_ALIGNMENT' if fail else 'PASS_INPUT_JOIN',
      'at':stamp(),'rows':rows,'failures':fail,'seconds':time.monotonic()-t0,
      'scientific_verdict':None,'source':'[이 발주에서 냄]'})
    dump(D/'tables/input_join.json',json.loads((O/'input_join.json').read_text()))
    print('INPUT_JOIN', 'STOP' if fail else 'PASS', 'missing normal',sum(r['undefined_normal_count'] for r in rows),
          'missing sigma',sum(r['missing_prior_sigma_count'] for r in rows), 'failures',fail)

if __name__=='__main__':main()
