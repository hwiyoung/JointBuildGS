"""Shared report helpers. Public analyses default to development files only."""
import csv
import inspect
import json
from pathlib import Path
import numpy as np
from preflight import dump,sha
O=Path('/out');DOC=Path('/docs');CFG=json.loads(Path('/cfg/widen0_v2.json').read_text())
CELLS=CFG['cells']['order'];KO=['둘 다 맞음','사전 정보만 틀림','영상만 틀림','둘 다 틀림','MVS 없음 · 사전 정보 맞음','MVS 없음 · 사전 정보 틀림','참값 없음']
KEYS=['centre','raw_centre','normal','area','building','roof_type','roof_like','source_extra','normal_defined','patch_id','cell','tau','gt_status','gt_p','gt_n_inner','gt_n_col','mvs_p','mvs_a_e','mvs_a_views','mvs_a_support_lmeds','mvs_a_support_final','u_mvs','u_prior','prior_error','difference_over_uncertainty','signed_difference_over_uncertainty']
def load(prior,holdout=False,keys=None):
    root=O/('holdout/patch_values' if holdout else 'patch_values');parts=[]
    for f in sorted(root.glob(f'*__{prior}__R1.5.npz')):
        with np.load(f) as z:
            assert np.all(z['holdout']==holdout),f
            parts.append({k:z[k] for k in keys or KEYS})
    assert parts,root
    return {k:np.concatenate([p[k] for p in parts]) for k in parts[0]}
def number(v):
    a=np.asarray(v);a=a[np.isfinite(a)];return float(np.median(a)) if len(a) else None
def quantiles(v):
    a=np.asarray(v);a=a[np.isfinite(a)];return dict(n=len(a),q25=float(np.quantile(a,.25)) if len(a) else None,median=number(a),q75=float(np.quantile(a,.75)) if len(a) else None)
def csvwrite(path,rows):
    if not rows:rows=[{'status':'no rows'}]
    fields=list(dict.fromkeys(k for r in rows for k in r));path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in r.items()})
def save_table(name,rows,**meta):
    generator=Path(inspect.stack()[1].filename)
    obj=dict(rows=rows,source='PHD-MAIN-WIDEN0-v2 generated table; sources in rows and generator; [이 발주에서 냄]',
        generator=str(generator),generator_sha256=sha(generator),config_sha256=sha('/cfg/widen0_v2.json'),scientific_verdict=None)
    obj.update(meta)
    dump(DOC/'tables'/f'{name}.json',obj)
    csvwrite(DOC/'tables'/f'{name}.csv',rows)
def font():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    paths=list(Path('/fonts').glob('*SansCJK*Regular*.ttc'))
    if paths:
        font_manager.fontManager.addfont(str(paths[0]));plt.rcParams['font.family']=font_manager.FontProperties(fname=str(paths[0])).get_name()
    plt.rcParams['axes.unicode_minus']=False
    return plt
def figure(fig,name,data):
    dest=DOC/'figures';dest.mkdir(exist_ok=True)
    fig.savefig(dest/f'{name}.png',dpi=300,bbox_inches='tight');fig.savefig(dest/f'{name}.pdf',dpi=300,bbox_inches='tight')
    dump(dest/f'{name}.json',dict(data=data,source='development only; [이 발주에서 냄]',scientific_verdict=None))
