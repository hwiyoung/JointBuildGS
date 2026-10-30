"""Complete presentation tables from finished values, without reselecting parameters."""
import json
from pathlib import Path
import numpy as np
from figures import data,O,C,D
from analyse import save,SCENARIOS
from lock_config import dump,sha,stamp

def rows(name):return json.loads((D/'tables'/f'{name}.json').read_text())['rows']

def main():
    cfg=json.loads((C/'judgenum_v1.json').read_text());selected=rows('selected_values')
    candidates=cfg['initial_choice']['photo_candidates'];basecal=json.loads((O/'calibration.json').read_text())['values']
    save('photo_candidates',[dict(photo_index=i,**v) for i,v in enumerate(candidates)])
    top=[];missing=[];summary=[];chosen_all=[];component_unknown=[]
    for prior in ['LoD2','ALS']:
        d,sources=data(prior)
        for kind in [1,2]:
            m=d['kind']==kind
            if not m.any():continue
            for key,mm in [('normal',~d['normal_defined']),('sigma_p',~np.isfinite(d['sigma_p'])),
              ('a',d['a_missing']),('photo',d['photo_missing']),('judgment_before',d['judgment_before']<0),
              ('judgment_after',d['judgment_after']<0),('mixed_cutoff',d['mixed_cutoff_unavailable'])]:
                missing.append({'prior':prior,'kind':kind,'value':key,'patch_count':int((m&mm).sum()),'area_m2':float(d['area'][m&mm].sum())})
            for cell in range(7):
                mm=m&(d['cell']==cell)&d['mixed_cutoff_unavailable']
                component_unknown.append({'prior':prior,'kind':kind,'cell':cell,'patch_count':int(mm.sum()),'area_m2':float(d['area'][mm].sum())})
        # Top fifteen uses the actual separately chosen roof/wall settings.
        wrong=(d['judgment_after']==1)&(((d['cell']==1)&(d['initial_choice']==0))|((d['cell']==2)&(d['initial_choice']==1)))
        ev=(d['judgment_after']==1)&np.isin(d['cell'],[0,1,2]);br=[]
        for bid in sorted(set(d['building'])):
            b=d['building']==bid;den=float(d['area'][b&ev].sum());err=float(d['area'][b&wrong].sum())
            br.append({'prior':prior,'building':bid,'different_area_m2':float(d['area'][b&(d['judgment_after']==1)].sum()),
              'evaluated_area_m2':den,'wrong_area_m2':err,'wrong_fraction':err/den if den else None})
        br.sort(key=lambda r:(-r['wrong_area_m2'],r['building']));chosen_all+=br
        top+=[dict(rank=i+1,**r) for i,r in enumerate(br[:15])]
        for name,_,_,half in SCENARIOS:
            area=d['spacing050_area_m2'] if half else d['area'];ret=d['spacing050_retained'] if half else np.ones(len(area),bool)
            after=d[f'{name}_judgment_after']
            for group,mask in [('roof',d['kind']==1),('wall',d['kind']==2),('combined',np.ones(len(area),bool))]:
                if not mask.any():continue
                eligible=mask&ret&(after==1)&np.isin(d['cell'],[0,1,2])
                meta={'eligible_building_count':len(set(d['building'][eligible])),
                  'evaluated_core_point_count':int(eligible.sum()),'evaluated_area_m2':float(area[eligible].sum()),
                  'scope_core_point_count':int((mask&ret).sum()),'sources':sources}
                for suffix in ['grid','leave_one_out','cross','buildings']:
                    file=f'{prior}_{name}_{group}_{suffix}';save(file,rows(file),meta)
                for row in selected:
                    if (row['prior'],row['scenario'],row['group'])==(prior,name,group):
                        row.update({k:v for k,v in meta.items() if k!='sources'})
                        pi=row['photo_index'];row.update(candidates[pi])
                        alt=row['building_equal_choice_index'];row['building_equal_photo_index']=alt//9
                        row['building_equal_threshold2_m']=cfg['initial_choice']['threshold2_m'][alt%9]
                        row['building_equal_photo_candidate']=candidates[alt//9]
                if name!='base' or group=='combined':continue
                for label in ['chosen','no_photo','display_photo']:
                    stem=f'{prior}_base_{group}'+('' if label=='chosen' else '_'+label)
                    cross=rows(stem+'_cross')
                    photorows=[];choicerows=[]
                    for cell in range(7):
                        for photo in range(3):
                            items=[r for r in cross if r['cell']==cell and r['photo_judgment']==photo]
                            photorows.append({'cell':cell,'photo_judgment':photo,'patch_count':sum(r['patch_count'] for r in items),'area_m2':sum(r['area_m2'] for r in items)})
                        for choice in [0,1]:
                            items=[r for r in cross if r['cell']==cell and r['initial_choice']==choice]
                            choicerows.append({'cell':cell,'initial_choice':choice,'patch_count':sum(r['patch_count'] for r in items),'area_m2':sum(r['area_m2'] for r in items)})
                    save(stem+'_photo_by_cell',photorows,meta);save(stem+'_choice_by_cell',choicerows,meta)
                    row=next(r for r in selected if (r['prior'],r['scenario'],r['group'])==(prior,'base',group)) if label=='chosen' else rows(stem)[0]
                    summary.append({'prior':prior,'group':group,'variant':label,
                      'photo_index':row['photo_index'],'threshold2_m':row['threshold2_m'],
                      'different_area_m2':row['different_area_m2'],'evaluated_area_m2':row['evaluated_area_m2'],
                      'wrong_area_m2':row['wrong_area_m2'],'wrong_fraction':row['wrong_fraction'],
                      'cell1_wrong_area_m2':sum(r['area_m2'] for r in cross if r['cell']==1 and r['initial_choice']==0),
                      'cell2_wrong_area_m2':sum(r['area_m2'] for r in cross if r['cell']==2 and r['initial_choice']==1),
                      'photo_area_m2':row['photo_area_m2'],'wrong_by_photo_m2':row['wrong_by_photo_m2'],
                      'excluded_cells3456_area_m2':sum(r['area_m2'] for r in cross if r['cell']>=3),**{k:v for k,v in meta.items() if k!='sources'}})
    save('selected_values',selected);save('selection_comparison',summary)
    save('selected_all_buildings',chosen_all);save('selected_top15_buildings',top)
    save('missing_values',missing);save('mixed_cutoff_unavailable_by_cell',component_unknown)
    held=rows('holdout_counts_and_hashes')
    save('holdout_counts_and_hashes',held,{'public_fields':'building_count, core_point_count, area_m2, file sha256 only'})
    # All tabular JSON outputs also receive requested CSV/Markdown views.
    for p in sorted((D/'tables').glob('*.json')):
        obj=json.loads(p.read_text())
        if isinstance(obj.get('rows'),list) and obj['rows'] and all(isinstance(r,dict) for r in obj['rows']):
            if not p.with_suffix('.csv').exists() or not p.with_suffix('.md').exists():
                save(p.stem,obj['rows'],{k:v for k,v in obj.items() if k!='rows'})
    dump(O/'supplement_complete.json',{'at':stamp(),'scientific_verdict':None})
    print('SUPPLEMENT_TABLES_COMPLETE')

if __name__=='__main__':main()
