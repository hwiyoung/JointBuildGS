"""Reproduce one historical raw registration before the fixed search-region override."""
import json
from pathlib import Path
import numpy as np
import prior_registration as PR
from preflight import PH,PREP,dump,sha

def main():
    site='R1rep_b10';prior='ALS'
    dr=PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1'
    s0=PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1'
    v=json.loads((PREP/'step06/box_views.json').read_text())['views'][site]['train']
    PR.RNG=np.random.default_rng(0)
    p,reg,t=PR.run(site,prior,v,PREP/'mvs'/('box_'+site),dr/'s02_box'/site,
        Path('/out/verification/registration_replay'))
    old=json.loads((s0/'s61/box'/site/prior/'summary.json').read_text())['fixed']['registration_box']
    diff=float(np.max(np.abs(np.array(reg['shift_applied'])-old['shift_applied'])))
    result=dict(site=site,prior=prior,reference='S0/s61/box/R1rep_b10/ALS/summary.json fixed.registration_box',
        old_shift_m=old['shift_applied'],new_shift_m=reg['shift_applied'],max_difference_m=diff,
        accepted_equal=reg['accepted']==old['accepted'],timings=t,scientific_verdict=None)
    result['status']='PASS' if diff<1e-9 and result['accepted_equal'] else 'DIFFERENT'
    dump(Path('/docs/tables/registration_replay.json'),result)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
