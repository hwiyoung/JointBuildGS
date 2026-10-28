"""Inventory and unchanged reference grouping for kind=2 LoD2, split sealed."""
import collections,time,csv
from common import *
from prepare import group

@locked_public
def table(name,rows):
    folder=D/'tables';folder.mkdir(parents=True,exist_ok=True)
    dump(folder/(name+'.json'),dict(rows=rows,at=now(),source='[이 발주에서 냄]',scientific_verdict=None))
    if not rows:return
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with (folder/(name+'.csv')).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows([{k:clean(v) for k,v in r.items()} for r in rows])
    lines=['| '+' | '.join(keys)+' |','| '+' | '.join(['---']*len(keys))+' |']
    lines += ['| '+' | '.join('확인 불가' if clean(r.get(k)) is None else str(clean(r.get(k))) for k in keys)+' |' for r in rows]
    (folder/(name+'.md')).write_text('\n'.join(lines)+'\n')

def main():
    cfg=load(C/'wallphoto_v1.json');assert sha(C/'wallphoto_v1.json')==load(C/'wallphoto_v1.lock.json')['sha256']
    ref=load('/repo/configs/phd/main_photocheck_v1/photocheck_v1.json')
    for key in ['points','heights','photos','score','judgments','uncertainty','projection_gate']:
        if key in ref:assert cfg[key]==ref[key],key
    stats=collections.defaultdict(lambda:dict(patches=0,points=0,area_m2=0.,significant_area_m2=0.))
    tiles=[];hold=dict(patches=0,area_m2=0.,buildings=set(),files=[]);start=time.monotonic()
    for f in sorted((W/'patch_values').glob('*__LoD2__R1.5.npz')):
        tile=f.stem.split('__')[0];raw=npz(f);take=raw['kind']==2
        assert not raw['holdout'].any()
        d={k:v[take] for k,v in raw.items()};n=len(d['patch_id'])
        if not n:continue
        g,owner,audit=group(d,'LoD2',tile);base=paths(False);dest=base/'geometry'/f'{tile}__LoD2.npz'
        _,first=np.unique(owner,return_index=True)
        g['face_ext']=d['face_ext'][first] if 'face_ext' in d else g['surf'].copy()
        # Source grouping supplies the face tangent frame for roof and wall alike.
        if not dest.exists():np.savez_compressed(dest,**g)
        mapping=base/'geometry'/f'{tile}__LoD2__mapping.npz'
        if not mapping.exists():np.savez_compressed(mapping,patch_id=d['patch_id'],point_index=owner,source_index=np.flatnonzero(take),kind=d['kind'])
        sp,sm=sigmas(d,'LoD2');sig=abs(d['mvs_p'])>3*np.sqrt(sp**2+sm**2)
        row=dict(tile=tile,patches=n,points=len(g['point_id']),area_m2=float(d['area'].sum()),significant_area_m2=float(d['area'][sig].sum()),source_sha256=sha(f))
        dump(dest.with_suffix('.json'),dict(**row,config_sha256=sha(C/'wallphoto_v1.json'),surface_audit=audit,scientific_verdict=None))
        tiles.append(row)
        for b in np.unique(d['building']):
            m=d['building']==b;r=stats[str(b)];r['patches']+=int(m.sum());r['points']+=int((g['building']==b).sum());r['area_m2']+=float(d['area'][m].sum());r['significant_area_m2']+=float(d['area'][m&sig].sum())
        print('geometry',tile,n,len(g['point_id']),flush=True)
    for f in sorted((W/'holdout/patch_values').glob('*__LoD2__R1.5.npz')):
        raw=npz(f);m=raw['kind']==2;assert raw['holdout'].all()
        hold['patches']+=int(m.sum());hold['area_m2']+=float(raw['area'][m].sum());hold['buildings'].update(raw['building'][m].tolist());hold['files'].append(dict(sha256=sha(f)))
    assert not (set(EXAMPLES)&hold['buildings'])
    hold['buildings']=len(hold['buildings'])
    pilot=[dict(building=b,**stats[b],order_patches=cfg['wall_task']['expected_patches'][i],difference_patches=stats[b]['patches']-cfg['wall_task']['expected_patches'][i],sample_fraction=1.) for i,b in enumerate(EXAMPLES)]
    table('pilot_inventory',pilot);table('development_tiles',sorted(tiles,key=lambda r:(-r['significant_area_m2'],r['tile'])))
    summary=dict(at=now(),pilot=pilot,development=dict(patches=sum(r['patches'] for r in tiles),points=sum(r['points'] for r in tiles),area_m2=sum(r['area_m2'] for r in tiles),buildings=len(stats)),holdout=hold,seconds=time.monotonic()-start,config_sha256=sha(C/'wallphoto_v1.json'),scientific_verdict=None,environment=env())
    dump(O/'inventory.json',summary);dump(D/'tables/inventory.json',summary)
    print(json.dumps(clean({k:v for k,v in summary.items() if k!='environment'}),ensure_ascii=False),flush=True)
if __name__=='__main__':main()
