"""Check historical complete-state method identity against the bounded 7k rerun."""
import gc
import torch
from common import *
def main():
    cfg=json.loads((CFG/'baseline7k.r7.json').read_text());rows=[]
    for r in cfg['rows']:
        old=PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs/B173nb_b10'/f'nojudge_{r["prior"]}_s0/model'
        state=torch.load(old/'jbgs_complete/iteration_30000/checkpoint.pth',map_location='cpu',weights_only=False)
        current=REPO/'src/phd/forks/GeoGS-conf-guided-v1-r15'
        mismatch=[p for p,h in state['implementation_hashes'].items() if sha(current/p)!=h];assert not mismatch,mismatch
        new=OUT/'r7/baselines'/r['name']/'model'
        assert sha(new/'input.ply')==sha(old/'input.ply')
        rows.append(dict(prior=r['prior'],historical_python_files=len(state['implementation_hashes']),all_identical=True,input_ply_identical=True,stored_optimization=state['optimization'],scientific_verdict=None))
        del state;gc.collect()
    result=dict(at=stamp(),status='PASS_HISTORICAL_BASELINE_SOURCE_AND_SEED',rows=rows,scientific_verdict=None)
    dump(OUT/'r7/verification/baseline_source.json',result);dump(DOC/'tables/baseline_source_r7.json',result);print(result['status'],flush=True)
if __name__=='__main__':main()
