"""Frozen-case raw versus depth-normal plane photometry, Docker CPU only."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from scripts.phd.local_complementary_refinement_v1 import photometric_walkthrough_v3_2 as old
from src.phd.local_normal_photometry_v3_7 import crop, estimate_normal, plane_depth, eligibility, summarize


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for k in ('parent', 'inputs', 'config', 'output'):
        ap.add_argument('--'+k, type=Path, required=True)
    a = ap.parse_args()
    old.require(Path('/.dockerenv').exists(), 'Docker required')
    started = time.time(); out = a.output; inputs = {}; checks = []
    def bind(p, expected=None):
        h = old.sha(p)
        old.require(expected is None or h == expected, 'Input hash mismatch: '+str(p))
        inputs[str(p)] = dict(path=str(p), sha256=h, bytes=p.stat().st_size)
        return p
    def url(p): return str(p.relative_to(out))
    try:
        cfg = old.read(bind(a.config))
        old.require(cfg['scientific_verdict'] is None and not cfg['gt_input'] and not cfg['weights_computed'], 'Scope mismatch')
        receipt = old.read(bind(a.parent/'receipt.json', cfg['parent_receipt_sha256']))
        old.require(receipt['status']=='PASS_INTERNAL_FIT_DIAGNOSTIC','Parent not passed')
        for row in receipt['outputs']:
            bind(a.parent/row['path'], row['sha256'])
        for p in [a.config, Path(__file__), Path(old.__file__),
                  Path('/repo/src/phd/local_normal_photometry_v3_7.py'),
                  Path('/repo/tests/phd/local_complementary_refinement_v1/test_normal_photometry_v3_7.py'),
                  Path('/repo/scripts/phd/local_complementary_refinement_v1/run_normal_photometry_v3_7.sh')]:
            bind(p); shutil.copy2(p,out/p.name)
        tests = subprocess.run([sys.executable,'-m','unittest','tests.phd.local_complementary_refinement_v1.test_normal_photometry_v3_7','-v'],capture_output=True,text=True)
        (out/'unit_tests.log').write_text(tests.stdout+tests.stderr)
        old.require(tests.returncode==0,'Independent geometric unit tests failed')
        manifest = old.read(a.parent/'manifest.json')
        photo_cache = {}; photo_seals = {}
        def photo(region, name):
            key = (region,name)
            if key not in photo_cache:
                if region not in photo_seals:
                    mp = a.inputs/region/'input_manifest.json'
                    # Parent receipt binds the same exact regional manifest.
                    expected = next(r['sha256'] for r in receipt['inputs'] if r['path']==f'/inputs/{region}/input_manifest.json')
                    photo_seals[region] = {x['path']:x['sha256'] for x in old.read(bind(mp,expected))['files']}
                relative = 'scene/images/'+name
                p = bind(a.inputs/region/relative,photo_seals[region][relative])
                photo_cache[key] = np.asarray(Image.open(p).convert('RGB'))/255.
            return photo_cache[key]
        cases=[]; rows=[]
        for item in manifest['cases']:
            parent_case = old.read(a.parent/item['path'])
            cid=parent_case['case_id']; folder=out/'cases'/cid;folder.mkdir(parents=True)
            ref=parent_case['reference_camera_model']; K=np.asarray(ref['K'])
            first=parent_case['neighbors'][0]
            with np.load(a.parent/first['numeric_arrays_url'],allow_pickle=False) as z:
                uv=z['reference_uv'].copy(); ref_rgb=z['reference_rgb'].copy()
                depth={s:z[s+'_depth'].copy() for s in ('prior','da3','mvs')}
                mask={s:z[s+'_raw_valid'].copy() for s in depth}
                native={s:z[s+'_native_query_uv'].copy() for s in depth}
            normals={s:estimate_normal(uv,depth[s],mask[s],K,cfg['normal_fit_size'],cfg['normal_fit_minimum_fraction']) for s in depth}
            planes={s:plane_depth(uv,depth[s],mask[s],K,normals[s]) for s in depth}
            for s,n in normals.items():
                q=crop(native[s],cfg['normal_fit_size']); m=crop(mask[s],cfg['normal_fit_size'])
                # Native nearest centers show duplicated MVS samples explicitly.
                key=np.floor(q[m]+.5).astype(int) if s=='mvs' else q[m]
                n['unique_native_queries']=len(np.unique(key,axis=0))
                if n['normal_camera'] is not None:
                    r=len(uv)//2
                    old.require(abs(planes[s][0][r,r]-depth[s][r,r])<1e-8,'Plane changed center depth')
                    old.require(not np.any(planes[s][1]&~mask[s]),'Plane filled source hole')
                    checks.append(dict(case_id=cid,source=s,check='center_depth_and_hole_preservation',status='PASS'))
            case={k:parent_case[k] for k in ('case_id','region','center_uv','ref_camera','depths','reference_camera_model','selection')}
            case.update(normal_sources=normals,neighbors=[],summary={},stability={},scientific_verdict=None,
                        visibility_status='unknown',weights_computed=False,scope=cfg['scope'])
            for field in ('ref_full_overlay_url','ref_context_url'):
                dest=folder/Path(parent_case[field]).name
                shutil.copy2(a.parent/parent_case[field],dest);case[field]=url(dest)
            # Same scale for raw and plane per source; offsets are camera Z, not world height.
            fig, ax = plt.subplots(3,3,figsize=(11,9),constrained_layout=True)
            for row,s in enumerate(depth):
                d=crop(depth[s],33); pd=crop(planes[s][0],33)
                vv=d[np.isfinite(d)&(d>0)]; vmin=float(vv.min()) if len(vv) else 0;vmax=float(vv.max()) if len(vv) else 1
                if vmax-vmin<1e-6:vmax=vmin+1e-6
                for col,dd in enumerate((d,pd)):
                    im=ax[row,col].imshow(dd,vmin=vmin,vmax=vmax,cmap='viridis');fig.colorbar(im,ax=ax[row,col],label='camera Z (m)')
                    ax[row,col].set_title(s+(' raw depth' if col==0 else ' center-anchored plane'))
                ax[row,2].plot(d[16],label='raw');ax[row,2].plot(pd[16],label='plane');ax[row,2].legend();ax[row,2].set_title('Center row; holes stay missing');ax[row,2].set_ylabel('camera Z (m)')
            fig.suptitle(cid+' | same-depth normal; center depth unchanged; no GT')
            fig.savefig(folder/'normal_geometry.png',dpi=110);plt.close(fig)
            case['normal_geometry_url']=url(folder/'normal_geometry.png')
            for ni, prev in enumerate(parent_case['neighbors']):
                nf=folder/f'neighbor_{ni+1:02d}';nf.mkdir()
                nb=prev['neighbor_camera_model']; img=photo(case['region'],nb['name'])
                entry=dict(camera_id=nb['name'],index=ni,patches={},visibility_status='unknown')
                cached={};numeric=dict(reference_uv=uv,reference_rgb=ref_rgb)
                for s in depth:
                    cached[s]={}
                    for mode, dd, mm in [('raw',depth[s],mask[s]),('plane',planes[s][0],planes[s][1])]:
                        target,z,_=old.project(uv,dd,ref,nb)
                        warped,inside=old.bilinear(img,target)
                        good=mm&inside&np.isfinite(z)&(z>0)
                        warped[~good]=np.nan
                        cached[s][mode]=(warped,good)
                        numeric[s+'_'+mode+'_depth']=dd;numeric[s+'_'+mode+'_valid']=mm
                        numeric[s+'_'+mode+'_uv']=target;numeric[s+'_'+mode+'_rgb']=warped;numeric[s+'_'+mode+'_projectable']=good
                        old.overlay((img*255).round().astype('uint8'),nf/(s+'_'+mode+'_full.png'),[(old.perimeter(target),cfg.get('colors',manifest['colors'])[s]),(old.perimeter(crop(target,9)), '#ff2060')])
                        if mode=='plane' and normals[s]['normal_camera'] is not None and good.any():
                            n=np.asarray(normals[s]['normal_camera']);r=len(uv)//2
                            center_ray=np.linalg.solve(K,np.r_[case['center_uv'],1.])
                            offset=n@(center_ray*depth[s][r,r])
                            A=np.asarray(nb['R'])@np.asarray(ref['R']).T
                            b=np.asarray(nb['t'])-A@np.asarray(ref['t'])
                            H=np.asarray(nb['K'])@(A+np.outer(b,n)/offset)@np.linalg.inv(K)
                            hom=np.concatenate([uv,np.ones(uv.shape[:-1]+(1,))],-1)@H.T
                            hq=hom[...,:2]/hom[...,2:]
                            error=float(np.max(np.abs(hq[good]-target[good])))
                            old.require(error<1e-7,'Independent plane homography mismatch')
                            checks.append(dict(case_id=cid,source=s,neighbor=ni,check='independent_homography',max_error_px=error))
                # Reproduce original pairwise raw 9x9 scores BEFORE restricting to plane support.
                for image_source in ('da3','mvs'):
                    pair='prior_'+image_source
                    common=crop(cached['prior']['raw'][1]&cached[image_source]['raw'][1],9)
                    for s in ('prior',image_source):
                        sc,_=old.score(crop(ref_rgb,9),crop(cached[s]['raw'][0],9),common,1e-12)
                        original=prev['comparisons'][pair]['scores'][s]
                        old.require(sc['common_count']==original['common_count'],'Parent raw support mismatch')
                        if sc['cost'] is None:old.require(original['cost'] is None,'Parent undefined mismatch')
                        else:old.require(abs(sc['cost']-original['cost'])<1e-11,'Parent raw cost mismatch')
                        checks.append(dict(case_id=cid,neighbor=ni,source=s,pair=pair,check='exact_parent_raw9_reproduction',cost=sc['cost']))
                for size in cfg['patch_sizes']:
                    sd=nf/str(size);sd.mkdir();reference=crop(ref_rgb,size)
                    old.save_rgb(sd/'reference.png',reference)
                    patch=dict(reference_url=url(sd/'reference.png'),sources={},comparisons={})
                    for s in depth:
                        source={}
                        for mode in ('raw','plane'):
                            rgb,good=cached[s][mode];rr,mm=crop(rgb,size),crop(good,size)
                            old.save_rgb(sd/(s+'_'+mode+'.png'),rr,mm);old.save_mask(sd/(s+'_'+mode+'_mask.png'),mm)
                            source[mode+'_url']=url(sd/(s+'_'+mode+'.png'))
                            source[mode+'_mask_url']=url(sd/(s+'_'+mode+'_mask.png'))
                            source[mode+'_full_overlay_url']=url(nf/(s+'_'+mode+'_full.png'))
                            source[mode+'_own_support_score']=old.score(reference,rr,mm,1e-12)[0]
                        patch['sources'][s]=source
                    for image_source in ('da3','mvs'):
                        pair='prior_'+image_source
                        common=np.ones((size,size),bool)
                        for s in ('prior',image_source):
                            for mode in ('raw','plane'):common &= crop(cached[s][mode][1],size)
                        old.save_mask(sd/(pair+'_common.png'),common)
                        comp=dict(common_count=int(common.sum()),mask_url=url(sd/(pair+'_common.png')),raw={},plane={})
                        for mode in ('raw','plane'):
                            for s in ('prior',image_source):
                                rgb=crop(cached[s][mode][0],size)
                                sc,res=old.score(reference,rgb,common,1e-12)
                                comp[mode][s]=sc
                                if sc['cost'] is not None:
                                    err=abs(old.independent_score(reference,rgb,common)-sc['zncc'])
                                    old.require(err<1e-10,'Independent ZNCC mismatch')
                                    checks.append(dict(case_id=cid,neighbor=ni,size=size,source=s,mode=mode,check='independent_zncc',error=err))
                        scores=[comp[m][s] for m in ('raw','plane') for s in ('prior',image_source)]
                        gates=cfg['diagnostic_gates']
                        comp['eligibility']=eligibility(scores,int(common.sum()),size,gates['minimum_fraction'],gates['texture_std'])
                        comp['texture_sensitivity']={str(t):eligibility(scores,int(common.sum()),size,gates['minimum_fraction'],t) for t in gates['texture_sensitivity']}
                        patch['comparisons'][pair]=comp
                        rows.append(dict(case_id=cid,neighbor=ni,patch_size=size,pair=pair,**comp))
                    entry['patches'][str(size)]=patch
                np.savez_compressed(nf/'numeric_arrays.npz',**numeric)
                entry['numeric_arrays_url']=url(nf/'numeric_arrays.npz');case['neighbors'].append(entry)
            for image_source in ('da3','mvs'):
                pair='prior_'+image_source;case['summary'][pair]={}
                for size in cfg['patch_sizes']:
                    comps=[n['patches'][str(size)]['comparisons'][pair] for n in case['neighbors']]
                    case['summary'][pair][str(size)]={mode:summarize(comps,mode,image_source,cfg['diagnostic_gates']) for mode in ('raw','plane')}
                readings=[case['summary'][pair][str(size)]['plane']['reading'] for size in cfg['patch_sizes']]
                case['stability'][pair]=dict(reading=readings[0] if len(set(readings))==1 else 'PATCH_SIZE_DEPENDENT',per_size_readings=readings,
                    interpretation='Relative photo preference only; unknown visibility and no weights/accuracy decision.')
            old.write(folder/'case.json',case);cases.append(dict(case_id=cid,label=item['label'],path=url(folder/'case.json')))
            print(json.dumps(dict(case=cid,status='SCORED',stability=case['stability'])),flush=True)
        old.write(out/'scores.json',rows)
        old.write(out/'validation.json',dict(status='PASS',checks=checks,scientific_verdict=None))
        old.write(out/'manifest.json',dict(schema='jbgs.normal_photometry.manifest.v3.7',scope=cfg['scope'],cases=cases,config=cfg,
            scientific_verdict=None,weights_computed=False,context_used_for_score=False,winner_selection=False,q_computed=False,
            limitations=['Eight historical development locations, no population inference.',
                'Unknown visibility; image projection and texture support do not certify same-surface correspondence.',
                'Normal is derived from the same depth, not an independent observation.',
                '9x9 plane orientation may smooth edges; center remains unchanged and holes stay missing.',
                'MVS duplicate native queries and prior half-pixel interpolation retain inherited sampling limitations.',
                'Internal photo fit may favor depths generated from those photos; no calibrated correctness or supervision weights.']))
        for row in inputs.values():old.require(old.sha(Path(row['path']))==row['sha256'],'Input changed during run')
        outputs=[dict(path=str(p.relative_to(out)),sha256=old.sha(p),bytes=p.stat().st_size) for p in sorted(out.rglob('*')) if p.is_file() and p.name not in ('execute.log','receipt.json')]
        old.write(out/'receipt.json',dict(status='PASS_INTERNAL_FIT_DIAGNOSTIC',scientific_verdict=None,scope=cfg['scope'],
            inputs=list(inputs.values()),outputs=outputs,actual_numeric_checks=len(checks),case_count=len(cases),score_rows=len(rows),
            elapsed_seconds=time.time()-started,config=cfg,command=sys.argv,runtime_image=os.environ.get('JBGS_RUNTIME_IMAGE_ID'),
            python=platform.python_version(),numpy=np.__version__,created_utc=datetime.now(timezone.utc).isoformat()))
    except Exception as e:
        old.write(out/'receipt.json',dict(status='FAIL',error=repr(e),scientific_verdict=None))
        raise


if __name__=='__main__':main()
