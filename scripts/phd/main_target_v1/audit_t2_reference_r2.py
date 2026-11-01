"""Read-only reference reconstruction; no resulting mask enters the new rule."""
import numpy as np
from common import *
from target_rules import fit_t2


def main():
    files = sorted((JN / 'core_points').glob('*__ALS.npz'))
    with np.load(files[0]) as z:
        print('FIELDS', z.files, flush=True)
    parts=[]
    for f in files:
        with np.load(f) as z:
            keys=['kind','area','d_mean_cm','DL_cm','judgment_before','judgment_after']
            parts.append({k:z[k] for k in keys if k in z.files})
    d={k:np.concatenate([p[k] for p in parts]) for k in parts[0]}
    rows=[]
    for key in d:
        if key in ['area','d_mean_cm','DL_cm']:continue
        for value in np.unique(d[key]):
            m=(d['kind']==1)&(d[key]==value)&np.isfinite(d['d_mean_cm'])&(d['d_mean_cm']!=0)
            if not m.any():continue
            row=dict(field=key,value=int(value),patches=int(m.sum()),area_m2=float(d['area'][m].sum()))
            if key!='kind':row['fit']=fit_t2(d['d_mean_cm'][m]/100,d['area'][m])
            rows.append(row)
    m=(d['kind']==1)&(np.abs(d['d_mean_cm'])>d['DL_cm'])
    rows.append(dict(field='saved_DL_cm_significant',patches=int(m.sum()),area_m2=float(d['area'][m].sum()),fit=fit_t2(d['d_mean_cm'][m]/100,d['area'][m])))
    dump(OUT/'r2/input_audit/t2_reference_candidates.json',dict(rows=rows,reference_only=True,scientific_verdict=None))
    print(json.dumps(rows),flush=True)


if __name__=='__main__':main()
