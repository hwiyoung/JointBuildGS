"""Export every original photo patch, separately from the unchanged JUDGENUM selection scope."""
from cp2_common import *
from photo_dl import lookup,derive

def main():
    save(CFG/'photo_patch_export.lock.json',dict(at=now(),script=bind(__file__),
        rule='Join all original PHOTOCHECK/WALLPHOTO patch IDs to already replayed point values. Outside JUDGENUM ownership DL stays unavailable. Selection scope/results remain unchanged.',
        config_sha256=sha(CFG/'candpick_v2.json'),scientific_verdict=None))
    totals={};coverage=[];holdout=[]
    for sealed in [False,True]:
        base=OUT/'holdout' if sealed else OUT/'photo_dl';inputs=[]
        for kind,source,groups in [(1,PC,['ALS','LoD2']),(2,WP,['LoD2'])]:
            source=source/'holdout' if sealed else source;group='roof' if kind==1 else 'wall'
            for prior in groups:
                points=0;patches=0;area_total=0.;missing_n=0;missing_a=0.
                for pp in sorted((source/'points').glob(f'*__{prior}.npz')):
                    p=arrays(pp);assert p['holdout'].all() if sealed else not p['holdout'].any()
                    mp=source/'patches'/pp.name;mapping=arrays(mp);tile=pp.stem.split('__')[0]
                    newpath=base/'points'/group/pp.name
                    if newpath.exists():new=arrays(newpath)
                    else:
                        # No JUDGENUM core file for this tile: every point lacks DL by definition.
                        assert not (JN/('holdout/core_points' if sealed else 'core_points')/pp.name).exists()
                        dl=np.full(len(p['point_id']),np.nan);values=derive(p,dl)
                        new=dict(point_id=p['point_id'],DL_m=dl,finite_DL_patch_count=np.zeros(len(dl),int),
                            total_joined_patch_count=np.zeros(len(dl),int),old_judgment=p['judgment'],**values)
                        newpath.parent.mkdir(parents=True,exist_ok=True);np.savez_compressed(newpath,**new)
                    assert np.array_equal(new['point_id'],p['point_id'])
                    own=lookup(new['point_id'],mapping['point_id']);assert (own>=0).all()
                    rawpath=W/('holdout/patch_values' if sealed else 'patch_values')/f'{tile}__{prior}__R1.5.npz'
                    with np.load(rawpath) as raw:
                        sourceidx=lookup(raw['patch_id'],mapping['patch_id']);assert (sourceidx>=0).all()
                        area=raw['area'][sourceidx];rawhold=raw['holdout'][sourceidx]
                    assert rawhold.all() if sealed else not rawhold.any()
                    assert abs(float(area.sum())-float(p['area'].sum()))<1e-6
                    path=base/'patches'/group/pp.name;path.parent.mkdir(parents=True,exist_ok=True)
                    np.savez_compressed(path,patch_id=mapping['patch_id'],point_id=mapping['point_id'],area=area,
                        DL_m=new['DL_m'][own],judgment=new['judgment'][own],old_judgment=mapping['judgment'])
                    n=len(own);points+=len(p['point_id']);patches+=n;area_total+=float(area.sum())
                    missing=~np.isfinite(new['DL_m'][own]);missing_n+=int(missing.sum());missing_a+=float(area[missing].sum())
                    if not sealed:
                        j=new['judgment'][own]
                        for pi in range(15):
                            for value in range(5):
                                key=(prior,group,pi,value);a,b=totals.get(key,(0,0.));m=j[:,pi]==value
                                totals[key]=(a+int(m.sum()),b+float(area[m].sum()))
                    inputs.extend([bind(pp),bind(mp),bind(rawpath),bind(newpath)])
                row=dict(prior=prior,group=group,points=points,patches=patches,area_m2=area_total)
                if sealed:holdout.append(row)
                else:coverage.append(dict(**row,unavailable_DL_patches=missing_n,unavailable_DL_area_m2=missing_a))
        save(base/'patch_export_inputs.json',dict(inputs=inputs,source=SOURCE,scientific_verdict=None))
    table('photo_census_judgment_areas',[dict(prior=k[0],group=k[1],photo_index=k[2],judgment=k[3],patches=v[0],area_m2=v[1]) for k,v in sorted(totals.items())])
    table('photo_census_coverage',coverage)
    h=OUT/'holdout';files=[dict(file=str(p.relative_to(h)),sha256=sha(p)) for p in sorted(h.rglob('*')) if p.is_file()]
    existing=json.loads((DOC/'tables/holdout_counts_and_hashes.json').read_text())
    existing.update(photo_census_counts=holdout,files=files)
    save(DOC/'tables/holdout_counts_and_hashes.json',existing,replace=True)
    save(OUT/'photo_dl/patch_export_complete.json',dict(at=now(),status='COMPLETE',source=SOURCE,scientific_verdict=None))
    print('FULL_PHOTO_PATCH_EXPORT',coverage,flush=True)

if __name__=='__main__':main()
