"""Exact order-3 majority decision; target arithmetic remains FINALTRAIN's."""
import ast
from pathlib import Path
import numpy as np

def decide(case_ids,owners,original,in_eval,u_mvs,h_mvs):
    original=np.asarray(original)
    result=original.copy()
    assigned=np.zeros(len(original),bool)
    counts=np.zeros((len(original),5),np.int64)
    good=(owners>=0)&(owners<len(original))&(case_ids>=0)&(case_ids<=4)
    np.add.at(counts,(owners[good],case_ids[good]),1)
    expected={0:0,1:2,2:1,4:4}
    for i in np.flatnonzero(np.asarray(in_eval,bool)&(counts.sum(1)>0)):
        winners=np.flatnonzero(counts[i]==counts[i].max())
        if len(winners)>1:
            if 0 in winners:result[i]=0;assigned[i]=True
        elif winners[0] in expected:result[i]=expected[winners[0]];assigned[i]=True
    missing_u=assigned&(result==0)&~np.isfinite(u_mvs)
    result[missing_u]=1
    missing_h=assigned&(result==2)&~np.isfinite(h_mvs)
    result[missing_h]=original[missing_h]
    return result,counts,dict(agreement_without_u_m=int(missing_u.sum()),
        correction_without_h_m=int(missing_h.sum()),changed=int((result!=original).sum()))

def calculate_targets(data,prior):
    """Extract only the original function, avoiding unrelated module-side effects."""
    path=Path('/repo/scripts/phd/main_finaltrain_v1/targets.py')
    node=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='calculate')
    scope=dict(np=np)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope)
    return scope['calculate'](data,prior)
