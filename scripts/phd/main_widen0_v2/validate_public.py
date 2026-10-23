"""Numeric/packaging checks complement the required visual inspection."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from analysis_common import O,DOC,CELLS
from preflight import dump
def main():
    report=DOC/'본실험_넓히기0단계_보고_v2.md';text=report.read_text();assert len(text)<=20000
    held=set(json.loads((O/'building_split.json').read_text())['holdout'])
    for f in DOC.rglob('*'):
        if f.suffix in ['.md','.json','.csv']:
            public=f.read_text(encoding='utf-8-sig');assert not any(b in public for b in held),f
    assert text.splitlines()[0].startswith('범위:') and text.splitlines()[1].startswith('나눔:') and text.splitlines()[2].startswith('확인 불가:')
    required=['범위와_건물나눔']+[f'{stem}_{p}' for stem in ['차의크기','차의부호크기','사전정보_틀린곳_지도'] for p in ['LoD2','ALS']]+[f'모음사진_{c}' for c in ['prior_wrong','image_wrong','both_wrong']]
    figures=[]
    for name in required:
        for ext in ['png','pdf','json']:assert (DOC/'figures'/f'{name}.{ext}').is_file(),name
        with Image.open(DOC/'figures'/f'{name}.png') as im:
            im.verify()
        with Image.open(DOC/'figures'/f'{name}.png') as im:
            assert min(im.size)>500 and all(abs(v-300)<1 for v in im.info.get('dpi',[0,0]));figures.append(dict(name=name,size=list(im.size),dpi=im.info['dpi']))
    for p in ['LoD2','ALS']:
        j=json.loads((DOC/'figures'/f'차의크기_{p}.json').read_text())['data']
        for r in j:
            if r['valid_area_m2']:
                total=sum(r['fraction_per_bin'])+(r['under_axis_area_m2']+r['over_axis_area_m2'])/r['valid_area_m2']
                assert np.isclose(total,1,atol=1e-10),(p,total)
            assert np.isclose(r['valid_area_m2']+r['missing_difference_area_m2'],r['cell_area_m2'])
    rows=json.loads((DOC/'tables/대표자리_선정.json').read_text())['rows']
    all_ids=[b for r in rows for b in r['building_ids']]
    assert all(all_ids.count(b)<=3 for b in set(all_ids))
    for cell in ['prior_wrong','image_wrong','both_wrong']:
        rr=[r for r in rows if r['cell']==cell];assert len(rr)<=20
        ids=[b for r in rr for b in r['building_ids']]
        assert all(ids.count(b)<=3 for b in set(ids))
    # Confirm every per-row actual-error field was kept in both exports, without
    # exposing sealed values or their cell frequencies.
    required_keys=['gt_p','gt_n_col','gt_n_inner','mvs_a_p','mvs_a_a','mvs_a_s','mvs_a_u','mvs_a_q','mvs_a_e','mvs_a_f','mvs_a_status','mvs_a_n_inner_all','mvs_a_n_ring','mvs_a_views','mvs_a_quadrants','mvs_a_support_lmeds','mvs_a_support_final','mvs_a_thinned_inner','mvs_a_thinned_ring']
    for root in [O/'patch_values',O/'holdout/patch_values']:
        for f in root.glob('*.npz'):
            with np.load(f) as z:
                assert set(required_keys+['source_extra','normal_defined','signed_difference_over_uncertainty'])<=set(z.files)
                if '__ALS__' in f.name:assert {'als_u','als_e','als_status'}<=set(z.files)
    result=dict(status='PASS',report_characters=len(text),required_figures=figures,checks=['required files','300 dpi images','histogram mass including overflow','difference availability denominators','representative building caps','all inherited observation fields retained'],visual_review='required separately before delivery',scientific_verdict=None)
    dump(O/'gates/public_artifacts.json',result);dump(DOC/'tables/public_validation.json',result)
    print('public artifact numeric checks PASS')
if __name__=='__main__':main()
