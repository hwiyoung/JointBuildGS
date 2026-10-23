"""Independent data/geometry/export checks. No source mutations or new selection tuning."""
import io
import os
import platform
import resource
import zipfile
from PIL import Image
import PIL
import scipy
import matplotlib
from common import *
from prepare import pixel_to_plane

def main():
    config=load(CFG/'regionfig_v1.json');data=load(PAY/'prepared.json');lock=load(CFG/'regionfig_v1.lock.json');render=load(PAY/'render_receipt.json')
    checks=[];diag=[]
    def check(name,passed,detail=None):
        checks.append(dict(name=name,passed=bool(passed),detail=detail))
        assert passed,(name,detail)
    check('original config bytes unchanged',sha(CFG/'regionfig_v1.json')==lock['config_sha256'])
    check('config lock precedes render',lock['locked_at']<render['rendered_at'])
    for path,digest in lock['inputs_sha256'].items():check('source unchanged: '+path,sha(path)==digest)
    for ex,rec in zip(config['examples'],data['examples']):
        z,src=pv(ex);x0,y0=ex['start_xy'];x1,y1=ex['end_xy'];dx=x1-x0;dy=y1-y0;length=np.hypot(dx,dy)
        xx=z['centre'][:,0]-x0;yy=z['centre'][:,1]-y0
        along=(xx*dx+yy*dy)/length;across=(xx*dy-yy*dx)/length
        keep=z['in_eval']&z['roof_like']&(along>=0)&(along<=length)&(abs(across)<=ex['half_width_m'])
        highlight=np.isin(z['cell'],[config['cell_order'].index(k) for k in ex['highlight_cells']])
        selected=keep&highlight;ids=np.flatnonzero(selected)
        check(ex['id']+' band membership independent formula',np.array_equal(np.flatnonzero(keep),rec['band_patch_indices']))
        check(ex['id']+' correction membership',np.array_equal(ids,rec['correction_patch_indices']))
        # Difference formula calculated independently of plotted absolute heights.
        dz_prior=-z['gt_p'][selected].astype(float)*z['normal'][selected,2]
        dz_mvs=(z['mvs_a_p'][selected].astype(float)-z['gt_p'][selected].astype(float))*z['normal'][selected,2]
        dz_mvs[z['mvs_a_status'][selected]!=0]=np.nan
        check(ex['id']+' prior median',abs(np.nanmedian(dz_prior)*100-rec['values']['prior_minus_gt_cm'])<1e-10)
        check(ex['id']+' MVS median',abs(np.nanmedian(dz_mvs)*100-rec['values']['mvs_minus_gt_cm'])<1e-10)
        p=rec['photo'];pose=dict(p['pose']);pose['R']=np.array(pose['R']);pose['t']=np.array(pose['t']);cam=dict(p['camera']);cam['p']=np.array(cam['p'])
        X=np.array(p['line_xyz']);uv,zz=project(X,pose,cam)
        check(ex['id']+' shared start XY',np.allclose(X[0,:2],ex['start_xy'],atol=1e-10))
        check(ex['id']+' shared end XY',np.allclose(X[-1,:2],ex['end_xy'],atol=1e-10))
        check(ex['id']+' photographic section projection',np.allclose(uv,p['line_pixels'],atol=1e-9))
        check(ex['id']+' full 4m crop',p['crop_world_box']['full_4m_margin_inside'])
        check(ex['id']+' crop native >=600',min(p['crop_size_px'])>=600)
        check(ex['id']+' nadir preferred',p['tilt_deg']<=20 and not p['expanded_to_oblique'])
        check(ex['id']+' unknown visibility reported',p['unknown_fraction']==0)
        with zipfile.ZipFile(RAW) as zzf:raw=zzf.read(p['original_member'])
        check(ex['id']+' native image hash',hashlib.sha256(raw).hexdigest()==p['original_sha256'])
        original=Image.open(io.BytesIO(raw)).crop(p['crop_box_px']).convert('RGB')
        saved=Image.open(DOC/f"figures/crops/{ex['id']}_원본.png")
        check(ex['id']+' crop exact original pixels',np.array_equal(np.asarray(original),np.asarray(saved)))
        # Roundtrip tests detect distortion/sign/frame errors at the displayed section.
        roundtrip=np.array([pixel_to_plane(v[None],point[2],pose,cam)[0] for v,point in zip(uv,X)])
        check(ex['id']+' native projection roundtrip',np.max(np.abs(roundtrip-X))<1e-7)
        foot=np.array(p['crop_footprint_xyz']);fuv,_=project(foot,pose,cam)
        a,b,d,e=p['crop_box_px'];target=np.array([[a,b],[d,b],[d,e],[a,e],[a,b]])
        check(ex['id']+' map photo bounds roundtrip',np.max(abs(fuv-target))<1e-6)
        near=z['in_eval']&z['roof_like']&(np.minimum(abs(along),abs(along-length))<.005)&(abs(across)<.61)
        near|=z['in_eval']&z['roof_like']&(along>=0)&(along<=length)&(abs(abs(across)-.6)<.005)
        diag.append(dict(id=ex['id'],normal_direction_prior_minus_gt_cm=float(np.nanmedian(-z['gt_p'][selected].astype(float))*100),
                         vertical_prior_minus_gt_cm=rec['values']['prior_minus_gt_cm'],
                         normal_z_quantiles=np.quantile(z['normal'][selected,2],[0,.25,.5,.75,1]),
                         near_boundary=[dict(patch=int(i),along_m=along[i],across_m=across[i],in_final=bool(keep[i])) for i in np.flatnonzero(near)],
                         diagnostic_extend_to_12m_roof_count=int((z['in_eval']&z['roof_like']&(along>=0)&(along<=12)&(abs(across)<=.6)).sum()),
                         training_pose_difference=p['pose_max_absolute_difference'],projection_roundtrip_error_m=float(abs(roundtrip-X).max())))
    im=Image.open(DOC/'figures/영역예시_보정.png')
    check('PNG 300 dpi',all(abs(v-300)<.01 for v in im.info['dpi']))
    check('PNG exact canvas',im.size==tuple(round(v*300) for v in config['layout']['figure_inches']))
    check('PDF exists',(DOC/'figures/영역예시_보정.pdf').stat().st_size>10000)
    check('CUDA disabled',os.getenv('CUDA_VISIBLE_DEVICES')=='')
    check('no GPU device exposed',not list(Path('/dev').glob('nvidia*')))
    check('nice 19',os.getpriority(os.PRIO_PROCESS,0)==19)
    cg=Path('/sys/fs/cgroup/memory.max');limit=cg.read_text().strip() if cg.exists() else Path('/sys/fs/cgroup/memory/memory.limit_in_bytes').read_text().strip()
    check('container memory below 8 GB',int(limit)<8_000_000_000)
    output=dict(checked_at=now(),status='PASS',checks=checks,diagnostics=diag,
                requested_numbers_status='PARTIAL: B173 count and prior-height mismatch retained',
                runtime=dict(python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,pillow=PIL.__version__,matplotlib=matplotlib.__version__,
                             memory_limit_bytes=int(limit),max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),scientific_verdict=None)
    dump(DOC/'tables/검증.json',output);dump(PAY/'verification.json',output)
    print('PASS',len(checks),'checks');print(json.dumps(clean(diag),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
