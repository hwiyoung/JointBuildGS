"""Add explicit denominators and aggregate island counts; no decision changes."""
import json
import re
import subprocess
import sys
from pathlib import Path
import numpy as np
from figures import data
import analyse as a
from supplement_tables import rows
from lock_config import dump,sha,stamp
O=Path('/out');D=Path('/docs');C=Path('/cfg');S=Path(__file__).parent

def main():
    cfg=json.loads((C/'judgenum_v1.json').read_text());islands=rows('small_same_islands');sums=[];ranges=[];denominators=[]
    for prior in ['LoD2','ALS']:
        for name,*_ in a.SCENARIOS:
            for cell in range(7):
                rr=[r for r in islands if r['prior']==prior and r['scenario']==name and r['cell']==cell]
                sums.append({'prior':prior,'scenario':name,'cell':cell,'component_count':len({r['component'] for r in rr}),
                  'patch_count':sum(r['patch_count'] for r in rr),'area_m2':sum(r['area_m2'] for r in rr)})
        d,_=data(prior);raw,where=a.load(prior);counts=a.read_counts(where,0)
        for kind in [1,2]:
            scope=d['kind']==kind
            if not scope.any():continue
            for i,radius in enumerate(cfg['cylinder']['radii_m']):
                valid=scope&(counts[:,i]>=0);eligible=scope&(counts[:,-1]>0);lt4=(counts[:,i]>=0)&(counts[:,i]<4)
                denominators.append({'prior':prior,'kind':kind,'radius_m':radius,'all_cores':int(scope.sum()),
                  'defined_axis_cores':int(valid.sum()),'max_radius_positive_cores':int(eligible.sum()),
                  'n_lt4_count_all':int((scope&lt4).sum()),'n_lt4_fraction_all':float((scope&lt4).sum()/scope.sum()),
                  'n_lt4_fraction_defined_axis':float((valid&lt4).sum()/valid.sum()) if valid.any() else None,
                  'n_lt4_fraction_selection_subset':float((eligible&lt4).sum()/eligible.sum()) if eligible.any() else None,
                  'undefined_axis_count':int((scope&~valid).sum())})
            valid=scope&np.isin(d['judgment_before'],[0,1]);absolute=np.abs(d['d_mean_cm'])
            old=(absolute>np.maximum(d['DL_cm'],cfg['detection']['old_comparison_tau_m'][prior]*100)).astype(np.int8)
            changed=valid&(old!=d['judgment_before']);values=absolute[changed]
            ranges.append({'prior':prior,'kind':kind,'changed_cores':int(changed.sum()),'changed_area_m2':float(d['area'][changed].sum()),
              'min_changed_abs_d_cm':float(values.min()) if len(values) else None,'max_changed_abs_d_cm':float(values.max()) if len(values) else None})
    a.save('small_same_island_summary',sums);a.save('old_rule_distance_range',ranges);a.save('radius_sample_denominators',denominators)
    subprocess.run([sys.executable,'-B','-u',str(S/'report.py')],check=True)
    report=D/'판단숫자셈_보고_v1.md';text=report.read_text();assert len(text)<20000
    for word in ['판정','견주다','재다','언저리','가르다','갈래','가져온다','계승','새로움','우리','꼴','층']:assert word not in text
    for link in re.findall(r'\]\(([^)]+)\)',text):assert (D/link).exists(),link
    # Check the tables/report contain no sealed building identifiers.
    held=json.loads((O/'holdout/scope_membership.json').read_text())['buildings']
    for p in [report]+[p for stem in ['small_same_island_summary','old_rule_distance_range','radius_sample_denominators'] for p in (D/'tables').glob(stem+'.*')]:
        assert not any(b in p.read_text() for b in held),p
    runtime=json.loads((D/'tables/runtime_receipt.json').read_text());runtime['presentation_updated_at']=stamp()
    runtime['source_sha256']={p.name:sha(p) for p in S.iterdir() if p.is_file()};dump(D/'tables/runtime_receipt.json',runtime)
    dump(D/'tables/presentation_validation.json',{'status':'PASS','at':stamp(),'report_characters':len(text),
      'extra_tables':['small_same_island_summary','old_rule_distance_range','radius_sample_denominators'],
      'decision_values_changed':False,'report_links_present':True,'public_holdout_ids_absent':True,'scientific_verdict':None})
    ready=json.loads((O/'ready_for_handover.json').read_text());ready.update({'at':stamp(),'report_sha256':sha(report),'characters':len(text)})
    dump(O/'ready_for_handover.json',ready)
    print('PRESENTATION_CHECKS_PASS',len(text),flush=True)

if __name__=='__main__':main()
