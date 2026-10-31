"""Freeze experimental targets; truth fields are read only after target output."""
import sys
import numpy as np
from scipy.spatial import cKDTree
from scipy import ndimage
from common import *
from target_rules import detection,targets
from photo_derivation import derive
from judgment_census import lookup,accuracy_rows,PC,WP,W

CODE_TO_CELL={-1:6,0:6,2:0,3:2,4:4,5:4,11:1,12:3,13:5,14:5}


def photo_geometry(prior):
    parts=[];manifest=[]
    for f in sorted((W/'patch_values').glob(f'*__{prior}__R1.5.npz')):
        with np.load(f) as z:
            d={k:z[k] for k in ['centre','normal','kind','patch_id']}
        d['tile']=np.full(len(d['kind']),f.stem.split('__')[0])
        parts.append(d);manifest.append({'path':str(f),'sha256':sha(f)})
    d={k:np.concatenate([p[k] for p in parts]) for k in parts[0]}
    return d,cKDTree(d['centre']),manifest


def experimental_photo(d,DL,DLa,prior,source,tree):
    distance,ix=tree.query(d['centre'],k=2,workers=1);nearest=ix[:,0]
    matched=(distance[:,0]<=1e-8)&(distance[:,1]>1e-8)
    matched&=source['kind'][nearest]==d['kind']
    matched&=np.linalg.norm(source['normal'][nearest]-d['normal'],axis=1)<=1e-6
    photos=np.full(len(DL),2,np.int8);photosa=photos.copy();available=np.zeros(len(DL),bool)
    ids=np.full(len(DL),'',dtype='<U100');bindings=[]
    for tile in np.unique(source['tile'][nearest[matched]]):
        for kind,base in [(1,PC),(2,WP)]:
            if prior=='ALS' and kind==2:continue
            mask=matched&(source['tile'][nearest]==tile)&(d['kind']==kind)
            target=np.flatnonzero(mask)
            if not len(target):continue
            pp=base/'points'/f'{tile}__{prior}.npz';mp=base/'patches'/f'{tile}__{prior}.npz'
            if not pp.exists() or not mp.exists():continue
            with np.load(mp) as z:
                patch=lookup(z['patch_id'],source['patch_id'][nearest[target]])
                has=patch>=0;target=target[has];patch=patch[has];owners=z['point_id'][patch]
            with np.load(pp) as z:
                p={key:z[key] for key in ['point_id','heights','curve','peak_mask','texture','selected_count']}
            owner=lookup(p['point_id'],owners);assert (owner>=0).all()
            for inputDL,output in [(DL,photos),(DLa,photosa)]:
                finite=np.isfinite(inputDL[target]);count=np.bincount(owner[finite],minlength=len(p['point_id']))
                bound=np.full(len(count),np.nan);nonempty=np.flatnonzero(count)
                if len(nonempty):bound[nonempty]=ndimage.median(inputDL[target[finite]],labels=owner[finite]+1,index=nonempty+1)
                output[target]=derive(p,bound)['judgment'][owner,4]
            available[target]=True;ids[target]=owners
            bindings.extend([{'path':str(f),'sha256':sha(f)} for f in [pp,mp]])
    return photos,photosa,available,ids,matched,bindings


def main():
    cfg,lock=locked();t2=json.loads((OUT/'stage0_r1/T2.json').read_text())
    assert t2['status']=='PASS_T2_MIXTURE'
    deferred='--deferred' in sys.argv;sites=cfg['deferred_sites'] if deferred else cfg['sites']
    gate=OUT/'stage0_r1'/('input_gate_deferred.json' if deferred else 'input_gate.json')
    assert json.loads(gate.read_text())['status']=='PASS_STAGE0_INPUTS_R1'
    stem='experimental_deferred_r1' if deferred else 'experimental_r1'
    root=OUT/'targets';root.mkdir(exist_ok=True)
    evaluation=OUT/'stage0_r1/evaluation';evaluation.mkdir(exist_ok=True)
    spec={'at':stamp(),'config_sha256':lock['config_sha256'],'T2_sha256':sha(OUT/'stage0_r1/T2.json'),
        'photo_join':'unique identical registered centre <=1e-8m, same kind, outward normal <=1e-6; no coordinate shift or neighbour transfer; missing => unknown',
        'photo_bound':'median finite DL of matched experimental patches owned by each saved photo point, separately per unit',
        'evaluation_source':'exact S1 regions_ext_v3 code, mapped by the existing code meanings to seven truth cells; never used in targets',
        'code_to_cell':CODE_TO_CELL,'band_truth':'S1 code -1 means evaluation unavailable, not a truth class',
        'implementation_sha256':sha(__file__),'scientific_verdict':None}
    specpath=CFG/f'{stem}.lock.json'
    assert not specpath.exists(),'refuse to overwrite preregistration'
    dump(specpath,spec)
    rows=[];areas=[];joins=[]
    for prior in cfg['priors']:
        source,tree,bindings=photo_geometry(prior)
        for site in sites:
            f=OUT/'stage0_r1/inputs'/f'{site}_{prior}.npz'
            with np.load(f) as z:d={k:z[k] for k in z.files}
            cf=OUT/'stage0_r1/cylinders'/f'{site}_{prior}.selected.npz'
            with np.load(cf) as z:stats=z['stats'];noradius=z['unavailable_radius']
            count,dist,sd=stats[:,0],stats[:,1],stats[:,3]
            DL=detection(count,sd,d['u'],d['sigma_p']);DLa=detection(count,sd,d['a_sensitivity'],d['sigma_p'])
            photo,photosa,available,point_ids,matched,pbindings=experimental_photo(d,DL,DLa,prior,source,tree)
            label,h,sigma=targets(count,dist,DL,d['u'],d['sigma_p'],d['normal'],t2['fits']['main_u']['T2_m'],photo)
            label[d['unavailable']|noradius]=-1;h[label<0]=np.nan;sigma[label<0]=np.nan
            point=d['centre']+h[:,None]*d['normal']
            output={key:d[key] for key in ['centre','normal','kind','area','in_eval','surf','building','u','sigma_p','u_replaced','sigma_p_replaced','any_replaced']}
            output.update(target=point,h=h,sigma=sigma,region=label,DL=DL,DL_a=DLa,n=count,d=dist,s_sample=sd,
                photo=photo,photo_available=available,photo_point_id=point_ids,photo_geometry_matched=matched)
            dest=root/f'{site}_{prior}.npz';assert not dest.exists(),'immutable target output'
            np.savez_compressed(dest,**output)
            dump(dest.with_suffix('.json'),{'at':stamp(),'target_sha256':sha(dest),'config_sha256':lock['config_sha256'],
                'input_sha256':sha(f),'cylinder_sha256':sha(cf),'spec_sha256':sha(specpath),'photo_sources':bindings+pbindings,
                'GT_loaded_before_target':False,'scientific_verdict':None})
            for range_name,scope in [('eval',d['in_eval']),('band',~d['in_eval'])]:
                for kind in [1,2]:
                    for replacement,subset in [('all',np.ones(len(label),bool)),('original',~d['any_replaced']),('replaced',d['any_replaced'])]:
                        mask=scope&(d['kind']==kind)&subset
                        row={'site':site,'prior':prior,'range':range_name,'kind':kind,'replacement':replacement,'patches':int(mask.sum()),'area_m2':float(d['area'][mask].sum())}
                        for lab,name in [(-1,'unavailable'),(0,'unobserved'),(1,'agreement'),(2,'preservation'),(3,'correction')]:
                            row[name+'_area_m2']=float(d['area'][mask&(label==lab)].sum())
                        areas.append(row)
                joins.append({'site':site,'prior':prior,'range':range_name,'area_m2':float(d['area'][scope].sum()),
                    'exact_geometry_area_m2':float(d['area'][scope&matched].sum()),'photo_curve_area_m2':float(d['area'][scope&available].sum()),
                    'photo_unknown_area_m2':float(d['area'][scope&np.isin(photo,[2,3,4])].sum())})
            # Target bytes are already frozen before opening the truth fields.
            rp=S1/'regions_v3'/f'regions_ext_v3_{site}_{prior}.npz'
            with np.load(rp) as z:
                code=z['code_ext_v3'];assert set(np.unique(code))<=set(CODE_TO_CELL)
                cell=np.array([CODE_TO_CELL[int(v)] for v in code],np.int8)
                ev={key:z[key] for key in ['gt_med','tau','mvs_minus_prior','in_eval','area','centre','kind','mvs_minus_gt_at_gt','n_mvs_at_gt']}
            ev.update(cell=cell,source_code=code,normal=d['normal'],any_replaced=d['any_replaced'])
            np.savez_compressed(evaluation/f'{site}_{prior}.npz',**ev)
            d['cell']=cell;variants={'main':label};different=np.isin(label,[2,3])
            for name,value in [('prior_only',2),('mvs_only',3)]:
                lab=label.copy();lab[different]=value;variants[name]=lab
            for name,condition in [('T2_only',np.abs(dist)>t2['fits']['main_u']['T2_m']),('photo_only',photo==1)]:
                lab=label.copy();lab[different]=np.where(condition[different],3,2);variants[name]=lab
            aT=t2['fits']['sensitivity_a']['T2_m']
            if aT is not None:variants['sensitivity_a']=targets(count,dist,DLa,d['a_sensitivity'],d['sigma_p'],d['normal'],aT,photosa)[0]
            for name,lab in variants.items():
                for r in accuracy_rows(d,lab,name,'experiment',prior,scope=d['in_eval']):rows.append(dict(r,site=site))
            fraction=float(d['area'][d['in_eval']&(label<0)].sum()/d['area'][d['in_eval']].sum())
            assert fraction<=.1,f'STOP_STAGE0_UNAVAILABLE_AREA {site} {prior} {fraction}'
            print('TARGET_FROZEN',site,prior,'unavailable_fraction',fraction,'photo_area',float(d['area'][available].sum()),flush=True)
    result={'at':stamp(),'status':'PASS_STAGE0_TARGETS','areas':areas,'accuracy':rows,'photo_join':joins,
        'config_sha256':lock['config_sha256'],'spec_sha256':sha(specpath),'source_tag':'[이 발주에서 냄]','scientific_verdict':None}
    dump(DOC/'tables'/f'{stem}.json',result);dump(OUT/'stage0_r1'/f'{stem}.complete.json',result)

if __name__=='__main__':main()
