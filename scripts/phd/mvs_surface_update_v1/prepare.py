"""Freeze 3D cases and render integrated evidence stages without evaluation GT."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from src.phd import mvs_evidence_v1 as core
from src.phd.mvs_surface_update_v1 import assess
from scripts.phd.mvs_evidence_v1.build import Builder, patch_uv, clean


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p, obj):
    Path(p).write_text(json.dumps(clean(obj), ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def main():
    if not Path('/.dockerenv').exists(): raise RuntimeError('Docker required')
    ap=argparse.ArgumentParser()
    for k in ('evidence','inputs','mvs','base','output','config'):
        ap.add_argument('--'+k,type=Path,required=True)
    a=ap.parse_args();cfg=json.loads(a.config.read_text());a.output.mkdir(exist_ok=False)
    parent=json.loads((a.evidence/'receipt.json').read_text())
    assert sha(a.evidence/'receipt.json')==cfg['parent_evidence_receipt_sha256']
    sealed={x['path']:x['sha256'] for x in parent['outputs']}
    bound=[]
    def check(p):
        digest=sha(p);assert digest==sealed[str(p.relative_to(a.evidence))]
        bound.append(dict(path=str(p),sha256=digest));return p
    loader=Builder(SimpleNamespace(output=a.output/'input_audit',inputs=a.inputs,mvs=a.mvs,
                                  config=Path('/repo/configs/phd/mvs_evidence_v1/diagnostic.json')))
    basecfg=json.loads((a.base/'contracts/execution_v1.json').read_text())
    anchorcfg=json.loads(Path('/repo/configs/phd/geogs_mvs_pgsr_v1/experiment_v2.json').read_text())
    result=dict(task_id=cfg['task_id'],scientific_verdict=None,crs=cfg['crs'],world_shift=cfg['world_shift'],
                intervention=cfg['intervention'],regions=[],created_at=datetime.now(timezone.utc).isoformat())
    inventory=[]
    for region in cfg['regions']:
        binding=loader.setup_region(region)
        assert loader.regional[region]['manifest']['config_sha256']==sha(a.base/'contracts/execution_v1.json')
        anchor=anchorcfg['anchors'][region]
        rr=dict(id=region,anchor_relative=anchor['relative'],
                anchor_receipt_sha256=sha(a.base/anchor['relative']/'receipt.json'),
                checkpoint_sha256=anchor['sha256'],cases=[])
        views={v['name']:v for v in binding['train']}
        domain=basecfg['regions'][region]['domain']
        cached={}
        def camdef(v):
            return dict(R=v['R'],t=v['t'],K=v['K'],width=v['width'],height=v['height'],
                        image_name=v['name'],image_path=f'{region}/scene/images/{v["name"]}',
                        image_sha256=v['sha256'],maps=v['maps'],local_depth=v['local_depth'])
        for folder in sorted((a.evidence/region).glob('view_*')):
            camera=json.loads(check(folder/'camera.json').read_text())
            with np.load(check(folder/'arrays.npz'),allow_pickle=False) as f: arr={k:f[k] for k in f.files}
            v=views[camera['name']]
            xp=core.project(arr['centers'],arr['point_prior_depth'],v,v)[2]
            xm=core.project(arr['centers'],arr['point_mvs_depth'],v,v)[2]
            center=-np.asarray(v['R']).T@np.asarray(v['t']);d0=center-xm
            angles=[]
            for name in camera['neighbors']:
                nv=views[name];nc=-np.asarray(nv['R']).T@np.asarray(nv['t']);d1=nc-xm
                co=np.sum(d0*d1,axis=1)/np.maximum(np.linalg.norm(d0,axis=1)*np.linalg.norm(d1,axis=1),1e-12)
                angles.append(np.degrees(np.arccos(np.clip(co,-1,1))))
            arr['per_neighbor_parallax_deg']=np.stack(angles)
            state=assess(arr,cfg)
            def inside(x):return (x[:,0]>=domain['x'][0])&(x[:,0]<domain['x'][1])&(x[:,1]>=domain['y'][0])&(x[:,1]<domain['y'][1])
            pin,min_=inside(xp),inside(xm)
            accepted=state['accepted']&pin&min_
            inventory.append(dict(camera=camera['id'],candidate_points=int((state['candidate']&(pin|min_)).sum()),
                                  admitted_probe_points=int(accepted.sum()),region_xy=domain,uses_z_gate=False))
            cached[camera['id']]=(camera,arr,state,xp,xm,pin,min_,accepted)
        for number,selection in enumerate(cfg['selected_cases'][region],1):
            camera,arr,state,xp,xm,pin,min_,accepted=cached[selection['camera']]
            i=selection['point'];uv=arr['centers'][i];u,vv=map(int,uv)
            assert pin[i] or min_[i]
            ref=loader.load(region,camera['name']);view=ref['view']
            neighbor_names=camera['neighbors'];neighbors=[loader.load(region,name) for name in neighbor_names]
            piarr=np.flatnonzero(arr['profile_point_indices']==i);pi=int(piarr[0]) if len(piarr) else None
            reasons=list(state['reasons'][i])
            if not(pin[i] and min_[i]):reasons.append('different_surface_or_outside_region_xy')
            role=selection['role'];decision=('AGREE_NO_UPDATE' if role=='agree_control' else
                    'IMAGE_SUPPORTED_LOCAL_PROBE' if accepted[i] else 'ABSTAIN')
            ncam=arr['profile_normal_mvs'][pi] if pi is not None else np.full(3,np.nan)
            nw=ncam@np.asarray(view['R'])
            caseid=f'{region}_{number:02d}';out=a.output/caseid;out.mkdir()
            radius=cfg['display_radius_px'];box=[max(0,u-radius),max(0,vv-radius),min(view['width'],u+radius),min(view['height'],vv+radius)]
            crop=np.s_[box[1]:box[3],box[0]:box[2]]
            frames=[ref['rgb'][crop],arr['prior_common_ray'][crop],arr['mvs_common_ray'][crop],arr['delta'][crop]]
            fig,axes=plt.subplots(2,2,figsize=(9,8))
            for ax,frame,title in zip(axes.ravel(),frames,['Current photo','Prior camera-Z','MVS camera-Z','Prior minus MVS']):
                if frame.ndim==3:ax.imshow(frame)
                else:
                    lo,hi=(-2,2) if title.startswith('Prior minus') else (0,150)
                    im=ax.imshow(frame,cmap='coolwarm' if lo<0 else 'viridis',vmin=lo,vmax=hi);fig.colorbar(im,ax=ax,fraction=.04)
                ax.add_patch(plt.Rectangle((u-box[0]-3,vv-box[1]-3),7,7,fill=False,edgecolor='lime',linewidth=1.5))
                ax.set_title(title);ax.axis('off')
            fig.suptitle(f'{caseid}: exact 7x7 evidence box; larger image is display context');fig.tight_layout();fig.savefig(out/'01_inputs.png',dpi=135);plt.close(fig)
            puv=patch_uv(uv[None],3)
            pd=core.sample_prior(ref['prior'],puv)[0];md=core.sample_mvs(ref['mvs'],puv,view)[0]
            wp=core.project(puv,pd,view,view)[2][0];wm=core.project(puv,md,view,view)[2][0]
            origin=xp[i]
            fig=plt.figure(figsize=(10,4));ax=fig.add_subplot(121,projection='3d')
            for pts,color,label in [(wp,'#2563eb','Prior'),(wm,'#d97706','MVS')]:
                q=pts-origin;ax.scatter(q[:,0],q[:,1],q[:,2],s=12,color=color,label=label)
            ax.set(xlabel='local X offset (m)',ylabel='local Y offset (m)',zlabel='local Z offset (m)');ax.legend()
            ax=fig.add_subplot(122)
            for pts,color,label in [(wp,'#2563eb','Prior'),(wm,'#d97706','MVS')]:
                q=pts-origin;ax.scatter(q[:,0],q[:,2],s=15,color=color,label=label)
            ax.set(xlabel='local X offset (m)',ylabel='local Z offset (m)',title='7x7 source points, X-Z projection');ax.legend()
            fig.suptitle('Competing raw surface hypotheses; no forced correspondence');fig.tight_layout();fig.savefig(out/'02_surfaces.png',dpi=140);plt.close(fig)
            status=np.stack([arr['prior_self_status'][:,i],arr['mvs_self_status'][:,i],arr['prior_to_mvs_status'][:,i]])
            fig,ax=plt.subplots(figsize=(10,3));ax.imshow(status,vmin=0,vmax=5,cmap='viridis',aspect='auto')
            ax.set_yticks(range(3),['Prior self','MVS self','Prior -> MVS']);ax.set_xticks(range(len(neighbors)),[str(k+1) for k in range(len(neighbors))]);ax.set_xlabel('Bound neighbor ID (camera names in case.json)')
            for yy in range(3):
                for xx in range(len(neighbors)):ax.text(xx,yy,str(status[yy,xx]),ha='center',va='center',color='white')
            fig.suptitle('0 missing / 1 outside / 2 neighbor missing / 3 compatible / 4 behind / 5 front');fig.tight_layout();fig.savefig(out/'03_visibility.png',dpi=135);plt.close(fig)
            fig,axes=plt.subplots(len(neighbors),3,figsize=(7,max(3,1.7*len(neighbors))),squeeze=False)
            for ni,nb in enumerate(neighbors):
                p=core._warped(uv[None],arr['point_prior_depth'][i:i+1],view,nb['view'],ref['gray'],nb['gray'],3,patch_depth=pd)
                m=core._warped(uv[None],arr['point_mvs_depth'][i:i+1],view,nb['view'],ref['gray'],nb['gray'],3,patch_depth=md)
                for ax,patch,title in zip(axes[ni],[p[0][0],p[1][0],m[1][0]],['Reference','Prior warp','MVS warp']):
                    ax.imshow(patch.reshape(7,7),cmap='gray',vmin=0,vmax=1,interpolation='nearest');ax.axis('off');ax.set_title(title,fontsize=9)
                axes[ni,0].set_ylabel(str(ni+1));axes[ni,0].text(-.1,.5,f'{ni+1}',transform=axes[ni,0].transAxes)
            fig.suptitle('Actual 7x7 patches: all neighbors, including rejected evidence');fig.tight_layout();fig.savefig(out/'04_patches.png',dpi=140);plt.close(fig)
            fig,ax=plt.subplots(figsize=(9,4))
            if pi is not None:
                z=arr['profile_depths'][pi]
                for ni in range(arr['profile_per_neighbor_costs'].shape[0]):
                    cc=np.min(arr['profile_per_neighbor_costs'][ni,pi],axis=0)
                    ax.plot(z,cc,alpha=.6,ls='-' if state['admitted'][ni,i] else '--',label=f'view {ni+1} '+('admitted' if state['admitted'][ni,i] else 'excluded'))
                ax.plot(z,state['curves'][pi],color='black',lw=2.5,label='recomputed admitted median')
            ax.axvline(arr['point_prior_depth'][i],color='#2563eb',ls=':',label='Prior');ax.axvline(arr['point_mvs_depth'][i],color='#d97706',ls=':',label='MVS')
            ax.set(xlabel='Hypothesis camera-Z (m)',ylabel='ZNCC cost',title='No interpolation of missing evidence; minimum alone is insufficient');ax.legend(fontsize=8);fig.tight_layout();fig.savefig(out/'05_profile.png',dpi=140);plt.close(fig)
            neighbor_rows=[dict(id=ni+1,image_name=nb['view']['name'],prior_self=int(status[0,ni]),mvs_self=int(status[1,ni]),prior_to_mvs=int(status[2,ni]),
                photo_prior=arr['photo_costs_per_neighbor'][ni,i,0],photo_mvs=arr['photo_costs_per_neighbor'][ni,i,1],parallax_degrees=arr['per_neighbor_parallax_deg'][ni,i],admitted=state['admitted'][ni,i],supports_mvs=state['joint'][ni,i],opposes_mvs=state['opposite'][ni,i]) for ni,nb in enumerate(neighbors)]
            case=dict(id=caseid,case_id=caseid,label=role,selection=selection,reference_camera=camdef(view),
                uv=uv,prior_depth=arr['point_prior_depth'][i],mvs_depth=arr['point_mvs_depth'][i],
                prior_xyz_world=xp[i],mvs_xyz_world=xm[i],target_xyz_world=xm[i],target_normal_world=nw,
                prior_patch_world=wp,mvs_patch_world=wm,decision=decision,reason_codes=reasons,
                bbox=[u-3,vv-3,u+4,vv+4],display_bbox=box,neighbors=[camdef(nb['view']) for nb in neighbors],
                neighbor_evidence=neighbor_rows,profile_stats={k:val[i] for k,val in state['profile_stats'].items()},
                checks={k:bool(mask[i]) for k,mask in state['checks'].items()},
                stage_images=['01_inputs.png','02_surfaces.png','03_visibility.png','04_patches.png','05_profile.png'],
                same_image_lineage=True,scientific_verdict=None)
            write(out/'case.json',case);rr['cases'].append(case)
            print(json.dumps(dict(case=caseid,selection=selection,decision=decision,reasons=reasons)),flush=True)
        result['regions'].append(rr)
        loader.cache.clear()
    write(a.output/'cases.json',result);write(a.output/'candidate_inventory.json',inventory)
    shutil.copy2(a.config,a.output/'config.json')
    snapshot=a.output/'source_snapshot';snapshot.mkdir()
    for p in (Path(__file__),Path('/repo/src/phd/mvs_surface_update_v1.py')):shutil.copy2(p,snapshot/p.name)
    write(a.output/'receipt.json',dict(task_id=cfg['task_id'],status='PASS_PREPARED_CASES',scientific_verdict=None,
          parent_receipt_sha256=cfg['parent_evidence_receipt_sha256'],config_sha256=sha(a.config),
          inputs=bound+list(loader.bound.values()),source_sha256=sha(__file__),policy_sha256=sha('/repo/src/phd/mvs_surface_update_v1.py'),
          cases_sha256=sha(a.output/'cases.json'),reference_accessed=False,
          outputs=[dict(path=str(p.relative_to(a.output)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(a.output.rglob('*')) if p.is_file()]))


if __name__=='__main__':main()
