"""Own B173 inputs and unchanged UNCERT core; no GT input or neighbour value transfer."""
import importlib.util
import sys
import os
import numpy as np
from common import *


def module(name,path):
    sp=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(sp)
    sys.modules[name]=m;sp.loader.exec_module(m);return m


def setup():
    cfg,lock=locked();site='B173_b0';root=OUT/'b173_uncert_r1'
    assert cfg['b173_uncertainty']['use_gt'] is False
    sys.path.insert(0,str(REPO/'scripts/phd/main_uncert_v1'))
    import uc_common as U
    U.OUT=root;U.PTS=root/'points';U.WORK=root/'work';U.PV=root/'patch_values'
    U.TAB=root/'tables';U.FIG=root/'figures';U.LOG=root/'logs';U.SITE_ID[site]=3
    for p in [U.PTS,U.WORK,U.PV,U.TAB,U.FIG,U.LOG]:p.mkdir(parents=True,exist_ok=True)
    sources=['uc_common.py','u_core.py','u1_mvs_points.py','u1_other_points.py','u1_patches.py','u2_run.py']
    provenance={'at':stamp(),'config_sha256':lock['config_sha256'],
        'sources':{x:sha(REPO/'scripts/phd/main_uncert_v1'/x) for x in sources},
        'seed_site_id':3,'GT_loaded':False,'neighbour_values_loaded':False,'scientific_verdict':None}
    dump(root/f'implementation_{sys.argv[1]}.lock.json',provenance)
    return cfg,site,root,U,provenance


def prepare_patches(U,site):
    patchmod=module('target_uc_patch_geometry',REPO/'scripts/phd/main_uncert_v1/u1_patches.py')
    from matplotlib.path import Path as MPath
    DR=PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1'
    faces=json.loads((DR/'s02_box'/site/'lod2_surfaces.json').read_text())['surfaces']
    tab={t['ext']:t for t in faces}
    roof_types=patchmod.roof_types(sorted({t['building'] for t in faces}))
    fp=json.loads((DR/'s02_box'/site/'footprints.json').read_text())['footprints'];rings={}
    for r in fp:rings.setdefault(r['building'],[]).append(MPath(np.asarray(r['ring_local'])))
    for prior in ['ALS','LoD2']:
        dest=U.WORK/f'patches_{site}_{prior}.npz'
        if dest.exists():continue
        with np.load(S1/'regions_v3'/f'regions_ext_v3_{site}_{prior}.npz') as z:
            data={k:z[k] for k in ['centre','area','kind','in_eval']}
        with np.load(S0/'s61/box'/site/prior/'units.npz') as z:
            assert np.array_equal(data['centre'],z['loc_center'])
            n=np.cross(z['loc_t1'],z['loc_t2']);n/=np.maximum(np.linalg.norm(n,axis=1,keepdims=True),1e-12)
            n*=np.where(n[:,2:3]<0,-1.,1.);surf=z['surf_ext'][z['loc_surface']]
        building=np.full(len(n),'',dtype='<U80');rt=np.full(len(n),'',dtype='<U20')
        if prior=='LoD2':
            wall=data['kind']==2;n[wall]=np.array([tab[int(e)]['normal'] for e in surf[wall]])
            building=np.array([tab[int(e)]['building'] for e in surf])
            hz=n[:,:2]/np.maximum(np.linalg.norm(n[:,:2],axis=1,keepdims=True),1e-12)
            for e in np.unique(surf[wall]):
                ix=np.flatnonzero(wall&(surf==e));b=tab[int(e)]['building']
                po=data['centre'][ix,:2]+.5*hz[ix];pi=data['centre'][ix,:2]-.5*hz[ix]
                ino=np.zeros(len(ix),bool);ini=np.zeros(len(ix),bool)
                for r in rings.get(b,[]):ino|=r.contains_points(po);ini|=r.contains_points(pi)
                if (ino&~ini).sum()>(~ino&ini).sum():n[ix]*=-1
            for b,v in roof_types.items():
                rt[building==b]=v['code'] or (v['parts'][0] if v['parts'] and len(set(v['parts']))==1 else '')
        np.savez_compressed(dest,**data,normal=n,roof_like=np.abs(n[:,2])>=np.cos(np.radians(45)),
            surf=surf,building=building,roof_type=rt)


def main():
    cfg,site,root,U,provenance=setup();step=sys.argv[1]
    if step=='patches':
        prepare_patches(U,site);return
    if step=='mvs':
        mvs=module('target_uc_mvs',REPO/'scripts/phd/main_uncert_v1/u1_mvs_points.py')
        if not (U.PTS/site/'mvs_a.json').exists():mvs.main(site,'a')
        return
    if step=='als':
        alsmod=module('target_uc_als',REPO/'scripts/phd/main_uncert_v1/u1_other_points.py')
        if not (U.PTS/site/'als.json').exists():
            X,cls,multi,info=alsmod.als_all([site])[site]
            np.save(U.PTS/site/'als_xyz.npy',X.astype(np.float64));np.save(U.PTS/site/'als_cls.npy',cls)
            np.save(U.PTS/site/'als_multi.npy',multi)
            U.jdump(U.PTS/site/'als.json',dict(site=site,n_points=len(X),**info,scientific_verdict=None))
        return
    assert step=='rings'
    run=module('target_uc_run',REPO/'scripts/phd/main_uncert_v1/u2_run.py')
    for prior,datas in [('ALS',['mvs_a','als']),('LoD2',['mvs_a'])]:
        assert not (U.WORK/f'gt_{site}_{prior}.npz').exists()
        for data in datas:
            if not (U.WORK/f'val_{site}_{prior}_{data}_R1.5.npz').exists():
                run.run(site,prior,data,[1.5],cfg['b173_uncertainty']['workers'])
        with np.load(U.WORK/f'patches_{site}_{prior}.npz') as z:d={k:z[k] for k in z.files}
        for data in datas:
            with np.load(U.WORK/f'val_{site}_{prior}_{data}_R1.5.npz') as z:
                d.update({data+'_'+k:z[k] for k in z.files if k not in ['e_bias','e_spread','e','qe','f']})
        d['u_prior']=np.where(d['als_status']==0,d['als_u'],np.nan) if prior=='ALS' else np.full(len(d['area']),np.nan)
        np.savez_compressed(U.PV/f'{site}__{prior}__R1.5.npz',**d)
    dump(root/'complete.json',dict(provenance,status='COMPLETE_OWN_B173_UNCERTAINTY',finished_at=stamp()))
    print('COMPLETE_OWN_B173_UNCERTAINTY',flush=True)


if __name__=='__main__':main()
