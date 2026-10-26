"""Development-only GT joins and area summaries. Never imported by photo selection/scoring."""
import argparse,csv,collections
from common import *
from prepare import components

def write_table(name,rows,stage):
    folder=D/'tables'/stage;folder.mkdir(parents=True,exist_ok=True)
    dump(folder/f'{name}.json',dict(rows=rows,source='[이 발주에서 냄]',population=f'development {stage}; roof only',generator=str(Path(__file__)),generator_sha256=sha(__file__),config_sha256=sha(C/'photocheck_v1.json'),point_source=str(O/'work'/stage),patch_source=str(W/'patch_values'),scientific_verdict=None))
    if rows:
        keys=list(dict.fromkeys(k for r in rows for k in r));
        with (folder/f'{name}.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows([{k:clean(v) for k,v in r.items()} for r in rows])
        lines=['| '+' | '.join(keys)+' |','| '+' | '.join(['---']*len(keys))+' |']
        for r in rows:
            vals=[clean(r.get(k)) for k in keys];lines.append('| '+' | '.join('확인 불가' if v is None else str(v) for v in vals)+' |')
        (folder/f'{name}.md').write_text('\n'.join(lines)+'\n')
    else:
        (folder/f'{name}.csv').write_text('records\n0\n')
        (folder/f'{name}.md').write_text('해당 기록 0개. [이 발주에서 냄]\n')

def join(prior,stage):
    pieces=[];pointpieces=[]
    keys=['patch_id','centre','normal','tangent1','tangent2','building','kind','area','surf','roof_type','mvs_p','u_mvs','u_prior','gt_p','gt_status','cell','source_extra']
    for f in sorted((O/'work'/stage).glob(f'*__{prior}.npz')):
        points=npz(f);tile=f.stem.split('__')[0]
        raw=npz(W/'patch_values'/f'{tile}__{prior}__R1.5.npz');mapping=npz(O/'geometry'/f'{tile}__{prior}__mapping.npz')
        lookup=np.full(int(mapping['point_index'].max())+1,-1,np.int32);lookup[points['geometry_index']]=np.arange(len(points['point_id']))
        pos=lookup[mapping['point_index']];sel=pos>=0
        if stage=='pilot':sel&=np.isin(raw['building'][mapping['source_index']],EXAMPLES)
        source=mapping['source_index'][sel];pos=pos[sel]
        d={k:raw[k][source] for k in keys};assert np.array_equal(d['patch_id'],mapping['patch_id'][sel])
        sp,sm=sigmas(d,prior);d['sigma']=sp;d['sigma_mvs']=sm;d['point_id']=points['point_id'][pos]
        d['gt_valid']=(d['gt_status']==0)&np.isfinite(d['gt_p'])&np.isfinite(sp)
        d['prior_right']=d['gt_valid']&(abs(d['gt_p'])<=3*sp)
        d['unexplained']=np.isfinite(d['mvs_p'])&np.isfinite(sp)&np.isfinite(sm)&(abs(d['mvs_p'])>3*np.sqrt(sp**2+sm**2))
        for k in ['judgment','s0','s_in','h_in','s_out','h_out','s_max','h_max','difference','texture','parallax','selected_count','eligible_images']:d[k]=points[k][pos]
        d['tile']=np.full(len(source),tile);pieces.append(d);pointpieces.append(points)
    assert pieces,prior
    return {k:np.concatenate([x[k] for x in pieces]) for k in pieces[0]},{k:np.concatenate([x[k] for x in pointpieces]) for k in pointpieces[0]}

def metric(d,mask,k):
    a=d['area'];valid=mask&d['gt_valid'];total=a[mask].sum();den=a[valid].sum();out=dict(patches=int(mask.sum()),area_m2=total,gt_patches=int(valid.sum()),gt_area_m2=den,missing_gt_or_sigma_area_m2=total-den)
    for j,label in enumerate(['support','refute','ambiguous','textureless','few_photos']):
        sel=mask&(d['judgment'][:,k]==j);evaluated=sel&d['gt_valid'];A=a[sel].sum();E=a[evaluated].sum()
        out[label+'_patches']=int(sel.sum());out[label+'_area_m2']=A;out[label+'_area_fraction']=A/total if total else None
        out[label+'_gt_area_m2']=E;out[label+'_prior_right_area_m2']=a[evaluated&d['prior_right']].sum();out[label+'_prior_right_fraction']=out[label+'_prior_right_area_m2']/E if E else None
    out['decided_area_fraction']=(out['support_area_m2']+out['refute_area_m2'])/total if total else None
    return clean(out)

def make_components(d,prior,stage):
    area=d['area'];valid=(d['kind']==1)&d['gt_valid'];j=d['judgment'][:,4]
    masks=dict(false_refute=valid&(j==1)&d['prior_right'],missed_refute=valid&(j==0)&~d['prior_right'],support_mvs_diff=valid&(j==0)&d['unexplained'])
    rows=[];small=[];labels={}
    for name,m in masks.items():
        ids=np.flatnonzero(m);lab=components(d['centre'][ids]);sizes=np.bincount(lab,weights=area[ids]) if len(ids) else np.empty(0)
        labs=np.full(len(d['area']),-1,np.int32);labs[ids]=lab;labels[name]=labs
        small.append(dict(prior=prior,group=name,components=int((sizes<1).sum()),area_m2=float(sizes[sizes<1].sum())))
        for k in np.flatnonzero(sizes>=1):
            ix=ids[lab==k];bn,inv=np.unique(d['building'][ix],return_inverse=True);ba=np.bincount(inv,weights=area[ix]);b=bn[np.argmax(ba)]
            def median(key):v=d[key][ix];return np.nanmedian(v) if np.isfinite(v).any() else None
            vals,counts=np.unique(d['roof_type'][ix],return_counts=True)
            rows.append(dict(prior=prior,group=name,component_id=int(k),building=b,building_ids=';'.join(bn),patches=len(ix),area_m2=sizes[k],roof_type=vals[np.argmax(counts)],h_out_median_m=median('h_out'),texture_median=median('texture'),parallax_median=median('parallax'),selected_images_median=median('selected_count')))
    folder=O/'evaluation'/stage;folder.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(folder/f'{prior}_components.npz',patch_id=d['patch_id'],**labels)
    write_table(f'{prior}_components',rows,stage);write_table(f'{prior}_components_below_1m2',small,stage)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pilot','full']);a=ap.parse_args();cfg=load(C/'photocheck_v1.json')
    for prior in ['LoD2','ALS']:
        d,p=join(prior,a.stage);roof=d['kind']==1;summary=[];cross=[];expect=[];groups=[]
        for scope,m in [('all_roof',roof),('unexplained_all_roof',roof&d['unexplained']),('gt_known',roof&d['gt_valid']),('unexplained_gt_known',roof&d['gt_valid']&d['unexplained'])]:
            for k,candidate in enumerate(cfg['judgments']['candidates']):
                summary.append(dict(prior=prior,scope=scope,combination=k,**candidate,**metric(d,m,k)))
                for cell,j,label in [(1,1,'prior_wrong_refuted'),(2,0,'image_wrong_supported'),(0,1,'both_right_refuted')]:
                    target=(roof&(d['cell']==cell)) if cell==0 else (roof&d['unexplained']&(d['cell']==cell))
                    denominator=d['area'][target].sum();numerator=d['area'][target&(d['judgment'][:,k]==j)].sum()
                    if scope=='all_roof':expect.append(dict(prior=prior,combination=k,**candidate,measure=label,patches=int(target.sum()),numerator_area_m2=numerator,denominator_area_m2=denominator,fraction=numerator/denominator if denominator else None))
            for j in range(5):
                for cell in range(7):
                    m2=m&(d['judgment'][:,4]==j)&(d['cell']==cell);cross.append(dict(prior=prior,scope=scope,judgment=j,cell=cell,patches=int(m2.sum()),area_m2=d['area'][m2].sum()))
        groupdefs=[]
        if prior=='LoD2':groupdefs += [('roof_type',str(v),d['roof_type']==v) for v in np.unique(d['roof_type'][roof])]
        else:groupdefs += [('raw_u_prior_cm','<1',(d['u_prior']>=0)&(d['u_prior']<.01)),('raw_u_prior_cm','1-3',(d['u_prior']>=.01)&(d['u_prior']<=.03)),('raw_u_prior_cm','>3',d['u_prior']>.03)]
        groupdefs += [('parallax','<0.2',(d['parallax']>=0)&(d['parallax']<.2)),('parallax','0.2-0.5',(d['parallax']>=.2)&(d['parallax']<=.5)),('parallax','0.5-1',(d['parallax']>.5)&(d['parallax']<=1)),('parallax','>1',d['parallax']>1)]
        groupdefs += [('selected_images',lab,(d['selected_count']>=lo)&(d['selected_count']<=hi)) for lab,lo,hi in [('0-2',0,2),('3-5',3,5),('6-9',6,9),('10',10,10)]]
        groupdefs += [('texture','<5',(d['texture']>=0)&(d['texture']<5)),('texture','5-10',(d['texture']>=5)&(d['texture']<=10)),('texture','10-20',(d['texture']>10)&(d['texture']<=20)),('texture','>20',d['texture']>20)]
        groupdefs += [('missing_MVS',str(v),d['cell']==v) for v in [4,5]]
        groupdefs += [('building',str(b),d['building']==b) for b in np.unique(d['building'][roof])]
        for dimension,label,m in groupdefs:
            for scope,population in [('all_roof',roof),('gt_known',roof&d['gt_valid'])]:
                groups.append(dict(prior=prior,scope=scope,dimension=dimension,label=label,unexplained_area_m2=d['area'][population&m&d['unexplained']].sum(),**metric(d,population&m,4)))
        mvsmask=roof&(d['judgment'][:,4]==0)&d['unexplained'];mvsrows=[]
        for dimension,label,m in [('all','all',np.ones(len(roof),bool))]+[('building',str(b),d['building']==b) for b in np.unique(d['building'][roof])]+[('raw_u_mvs_cm',lab,((d['u_mvs']>=lo) if lo==0 else (d['u_mvs']>lo))&(d['u_mvs']<=hi)) for lab,lo,hi in [('0-3',0,.03),('3-5',.03,.05),('5-10',.05,.1),('10-20',.1,.2),('20-40',.2,.4),('>40',.4,np.inf)]]:
            allm=m&mvsmask;known=allm&d['gt_valid'];A=d['area'][known].sum();E=d['area'][known&(d['cell']==2)].sum();mvsrows.append(dict(prior=prior,dimension=dimension,label=label,scope='gt_known',patches=int(known.sum()),area_m2=A,all_roof_patches=int(allm.sum()),all_roof_area_m2=d['area'][allm].sum(),excluded_missing_gt_area_m2=d['area'][allm&~d['gt_valid']].sum(),image_wrong_area_m2=E,image_wrong_fraction=E/A if A else None))
        for name,rows in [('summary_15',summary),('cell_cross',cross),('expectations_15',expect),('groups',groups),('mvs_evidence',mvsrows)]:write_table(prior+'_'+name,rows,a.stage)
        make_components(d,prior,a.stage)
        folder=O/'evaluation'/a.stage;np.savez_compressed(folder/f'{prior}_patches.npz',**d)
        print('evaluation complete',a.stage,prior,int(roof.sum()),flush=True)
if __name__=='__main__':main()
