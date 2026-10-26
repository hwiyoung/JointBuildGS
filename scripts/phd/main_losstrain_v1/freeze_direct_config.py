"""Freeze amended rules and an outcome-free B173 camera before any training."""
import importlib.util
import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
import shutil
import numpy as np
from inputs import OUT,PH,S0,save,sha
from direct_rules import RULES

def main():
    I=S0/'fork_inputs/s61/B173nb_b10';scene=I/'scene_LoD2'
    path=Path('/repo/src/phd/forks/GeoGS-conf-guided-v1-r16/scene/colmap_loader.py')
    spec=importlib.util.spec_from_file_location('lt_colmap',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    ext=mod.read_extrinsics_binary(str(scene/'sparse/0/images.bin'));by={Path(e.name).stem:e for e in ext.values()}
    split=json.loads((I/'split.json').read_text());cal=json.loads((scene/'jbgs_calibration.json').read_text())['images']
    a=np.array([146.68,96.32]);b=np.array([136.63,99.34]);mid=(a+b)/2
    with np.load(I/'store_LoD2.npz') as st:
        c=st['loc_center'];exts=st['surf_ext'][st['loc_surface']]
        m=np.isin(exts,[33,38])&(np.linalg.norm(c[:,:2]-mid,axis=1)<7)
        assert m.any();h=float(np.median(c[m,2]))
    target=np.r_[mid,h];box=np.array([[mid[0]+x,mid[1]+y,h+z] for x in [-10,10] for y in [-6,6] for z in [-7,2]])
    candidates=[]
    for name in split['train']:
        e=by[name];R=mod.qvec2rotmat(e.qvec);T=e.tvec;C=-R.T@T
        q=(box@R.T+T);pixels=q@np.asarray(cal[name]['K']).T;pixels=pixels[:,:2]/pixels[:,2:]
        view=C-target;theta=float(np.degrees(np.arccos(view[2]/np.linalg.norm(view))))
        valid=(q[:,2]>0).all() and (pixels[:,0]>=20).all() and (pixels[:,0]<1004).all() and (pixels[:,1]>=20).all() and (pixels[:,1]<721).all()
        if not valid:continue
        projected=float(np.prod(np.ptp(pixels,axis=0)))
        candidates.append(dict(name=name,angle_from_vertical_deg=theta,projected_bbox_area_px2=projected,
            camera_centre=C.tolist(),R=R.tolist(),t=T.tolist(),K=cal[name]['K'],width=1024,height=741,
            crop_xyxy_px=[float(pixels[:,0].min()),float(pixels[:,1].min()),float(pixels[:,0].max()),float(pixels[:,1].max())]))
    assert candidates
    oblique=[r for r in candidates if 20<=r['angle_from_vertical_deg']<=60]
    selected=max(oblique or candidates,key=lambda r:(r['projected_bbox_area_px2'],r['name']))
    camera=dict(selected=selected,candidates=candidates,target_prior_only_xyz=target.tolist(),box_prior_only_xyz=box.tolist(),
        rule='training camera; all prior-only ROI box corners in frame with 20 px margin; prefer 20..60 deg from vertical; maximize projected ROI box area, name breaks ties',
        photo='same training camera as render; exact same pose for every variant',GT_used=False,scientific_verdict=None)
    save('/config/figure_camera_v1.json',camera)
    p=Path('/config/losstrain_v1.json');old=Path('/config/losstrain_v1.pre_direct.json');assert not old.exists()
    shutil.copyfile(p,old);shutil.copyfile(p.with_suffix('.lock.json'),Path('/config/losstrain_v1.pre_direct.lock.json'))
    cfg=json.loads(p.read_text());cfg['saved_at']=datetime.now(timezone(timedelta(hours=9))).isoformat()
    cfg['status']='DIRECT_RULES_PASS_AWAITING_REMAINING_GPU_CHECKS_AND_CALIBRATION'
    cfg['correspondence_history']=cfg.pop('join')
    cfg['direct_stage1']=dict(revision=RULES['revision'],rules_sha256=sha(Path('/config')/(RULES['revision']+'.json')),
        gates_sha256=sha(OUT/RULES['revision']/'gates.json'),training_values_root=f'/o/{RULES["revision"]}',
        values='UNCERT R1.5 mvs_a on exact stage-1 rows; no WIDEN association in training or scoring')
    cfg['scoring']['scored']='stage-1 in_eval; finite p_G; no missing-ALS or outside-UNCERT median fallback; MVS available for cells 0..3; cells 4/5 separate'
    cfg['scoring']['patch_source']='direct_stage1_v2/<unit>/evaluation.npz'
    cfg['figures']['render_camera']=dict(file='figure_camera_v1.json',sha256=sha('/config/figure_camera_v1.json'),image_name=selected['name'])
    cfg['lambda_selection']['gradient_statistic']='median of 100 iteration-wise medians of per-Gaussian xyz L2 norm, all Gaussians including zeros; visible median supplementary only; depth includes lambda'
    cfg['lambda_selection']['undefined_rgb_median']='report ratio unavailable if RGB median is zero; compare depth_median < 0.1 * RGB_median directly'
    cfg['amendments']=[dict(at=cfg['saved_at'],source='user 2026-10-26 17:00 rule reply',
        previous_config=old.name,previous_sha256=sha(old),reason='direct stage-1 values and scoring replace WIDEN nearest-patch transfer; new 95% area and 90% LoD2 gates')]
    save(p,cfg);save('/config/losstrain_v1.lock.json',dict(sha256=sha(p),saved_at=cfg['saved_at'],training_started=False,scientific_verdict=None))
    print('amended config frozen',sha(p),'camera',selected['name'],'angle',selected['angle_from_vertical_deg'],flush=True)

if __name__=='__main__':main()
