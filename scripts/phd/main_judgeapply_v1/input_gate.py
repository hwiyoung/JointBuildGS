"""Bind requested regional patches/depths/images/poses/reference in their inherited frame."""
from common import *
from inherit import functions
import struct,zipfile,traceback
def main():
    c=cfg();scope=dict(np=np,struct=struct)
    poses,rotation=functions('photo_cameras.py',['poses','rotation'],scope)
    raw=Path('/art/phase-payloads/p0-audit/data')
    original=poses(raw/'work/mvs/colmap_dense/sparse/images.bin')
    inventory=json.loads((W/'inputs/image_inventory.json').read_text())['rows']
    members={Path(r['name']).stem:r['original_zip_member'] for r in inventory}
    photozip=raw/'raw/uav/Images.zip';rows=[];failures=[]
    with zipfile.ZipFile(photozip) as z:zipnames=set(z.namelist())
    for site in c['sites']:
        f=S0/'fork_inputs/s61'/site;split=json.loads((f/'split.json').read_text())
        local=poses(f/'scene_LoD2/sparse/0/images.bin');by={Path(k).stem:v for k,v in local.items()}
        orig={Path(k).stem:v for k,v in original.items()}
        mxq=mxt=0.;missing=[];found=0
        rec=json.loads((UN/'points'/site/'mvs_a.json').read_text())
        for n in sorted(split['train']):
            if n not in by or n not in orig or n not in members or members.get(n) not in zipnames:missing.append(n);continue
            q,t=by[n];oq,ot=orig[n]
            mxq=max(mxq,float(np.max(abs(rotation(q)-rotation(oq)))));mxt=max(mxt,float(np.max(abs(np.array(t)-ot))))
            dp=S0/'s61/export'/site/'LoD2/mvs'/f'{n}.npy';cp=dp.parent.parent/'conf'/dp.name
            if not dp.exists() or not cp.exists():missing.append(str(dp));continue
            a=np.load(dp,mmap_mode='r');b=np.load(cp,mmap_mode='r');assert a.shape==b.shape==(741,1024)
            found+=1
        row=dict(site=site,train_views=len(split['train']),depths=found,missing=missing,max_original_pose_rotation_difference=mxq,max_original_pose_translation_difference_m=mxt,
                 mvs_camera_names_match=rec['camera_names']==sorted(split['train']),patches=[],reference_path=str(UN/'points'/site/'gt_xyz.npy'))
        for prior in c['priors']:
            p=TG/'stage0_r1/inputs'/f'{site}_{prior}.npz';d=loadz(p,['centre','normal','area','kind','in_eval'])
            units=S0/'s61/box'/site/prior/'units.npz';u=loadz(units,['loc_center','loc_area'])
            assert np.array_equal(d['centre'],u['loc_center']) and np.array_equal(d['area'],u['loc_area'])
            rr=S1/'regions_v3'/f'regions_ext_v3_{site}_{prior}.npz'
            reg=loadz(rr,['centre','in_eval','frame_shift'])
            assert np.array_equal(reg['centre'],d['centre']) and np.array_equal(reg['in_eval'],d['in_eval'])
            row['patches'].append(dict(prior=prior,source=str(p),source_sha256=sha(p),source_units_sha256=sha(units),region_source_sha256=sha(rr),frame_shift=reg['frame_shift'].tolist(),eval_count=int((d['in_eval']&np.isin(d['kind'],c['priors'][prior])).sum())))
        gt=json.loads((UN/'points'/site/'gt.json').read_text());als=json.loads((UN/'points'/site/'als.json').read_text())
        row['gt_provenance']=gt['sources'];row['als_shift_equal']=als['shift_equal']
        if missing or mxq>1e-7 or mxt>1e-7 or not row['mvs_camera_names_match'] or not als['shift_equal']:failures.append(row)
        rows.append(row);print('INPUT_GATE',site,found,'pose_diffs',mxq,mxt,'missing',len(missing),flush=True)
    out=dict(at=now(),status='STOP_INPUT_ALIGNMENT' if failures else 'PASS_INPUT_ALIGNMENT',rows=rows,scientific_verdict=None,reference_values_read=False)
    dump(O/'input_gate.json',out);dump(D/'tables/input_gate.json',out)
    progress(out['status']+'; regional patch identities, depth shapes, original JPEG membership and camera frame checked.')
    if failures:
        issue('STOP_INPUT_ALIGNMENT: see tables/input_gate.json. No geometry/photo calculation started.');raise SystemExit(13)
if __name__=='__main__':main()
