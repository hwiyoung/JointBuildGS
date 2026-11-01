from common import *
a=read(PH/'main_design_realchange_survey_v1/PHD-MAIN-DESIGN-REALCHANGE-SURVEY-v1/s1/lod2_buildings.json')
b=read(W/'inputs/lod2_context_buildings.json')
print('original_schema',type(a).__name__,len(a),'context',len(b))
for name,src in [('survey',a),('widen',b)]:
    found=[v for v in src if v['id']=='DEBY_LOD2_4959322']
    print(name,'building_matches',len(found))
    for v in found:
        print('fields',list(v))
        print('face_sample',[(t,[(x['id'],len(x['ext'])) for x in v['surfaces'][t]][:3]) for t in ['roof','wall','ground']])
        print('wanted_faces',[x for t in ['roof','wall'] for x in v['surfaces'][t] if x['id']=='DEBY_LOD2_4959322_08a4f0b5-2b75-4c58-9463-bab9d1f165aa_2'])
