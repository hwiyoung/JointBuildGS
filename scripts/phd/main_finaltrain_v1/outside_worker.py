"""Run inherited geometry/photo kernels with already-frozen regional values."""
import os,sys,json,time
from pathlib import Path
site=sys.argv[1];os.environ['FINALTRAIN_SITE']=site
sys.path.insert(0,str(Path(__file__).parent/'inherited_judgeapply'))
from common import *
import geometry_run,ring_missing,sight,photo_prepare,score

def main():
    start=time.monotonic();O.mkdir(parents=True,exist_ok=True)
    dump(O/'input_gate.json',dict(status='PASS_INPUT_ALIGNMENT',scope='full TARGET stage0 arrays',scientific_verdict=None))
    geometry_run.main(site)
    ring_missing.main(site)
    frozen=json.loads((PH/'main_judgeapply_v1/PHD-MAIN-JUDGEAPPLY-v1/calibration.json').read_text())
    for prior in cfg()['priors']:
        p=O/'geometry_raw'/f'{site}__{prior}.npz';d=loadz(p)
        rr=loadz(O/'ring_recomputed'/p.name);d['u_mvs']=rr['u_mvs']
        rmap={x['kind']:x['r_m'] for x in frozen['r_rows'] if x['site']==site and x['prior']==prior}
        d['r_m']=np.array([rmap[int(k)] if rmap[int(k)] is not None else np.nan for k in d['kind']])
        d['sigma_W_m']=np.full(len(d['n']),frozen['sigma_W_m'])
        d['L_m']=1.96*(np.sqrt(d['u_mvs']**2+d['sigma_P_m']**2+d['sigma_W_m']**2)+abs(d['r_m']))
        g=np.full(len(d['n']),9,np.int8);valid=(d['n']>=4)&np.isfinite(d['d_m'])&np.isfinite(d['L_m'])
        g[(d['n']>=0)&(d['n']<4)]=2;g[valid&(abs(d['d_m'])<=d['L_m'])]=0;g[valid&(abs(d['d_m'])>d['L_m'])]=1;d['geometry']=g
        savez(O/'geometry'/p.name,**d)
    sight.main(site)
    photo_prepare.main(site)
    score.main('cpu',site)
    # Exact JUDGEAPPLY photo-code precedence; frozen t replaces threshold estimation.
    prep=loadz(O/'photo_prepared'/f'{site}.npz');scores=loadz(O/'photo_scores'/site/'scores.npz')
    thresholds=json.loads((R/'docs/experiments/phd/main_judgeapply_v1/tables'/f'{site}_photo_thresholds.json').read_text())['rows']
    for prior in cfg()['priors']:
        d=loadz(O/'geometry'/f'{site}__{prior}.npz');mp=loadz(O/'photo_mapping'/f'{site}__{prior}.npz');g=loadz(O/'photo_geometry'/f'{site}__{prior}.npz')
        ii=np.flatnonzero(prep['prior']==prior);ix=prep['source_index'][ii];p,m=scores['score'][ii].T;code=np.full(len(ii),9,np.int8)
        for k in cfg()['priors'][prior]:
            t=next(x['t'] for x in thresholds if x['prior']==prior and x['kind']==k);part=g['kind'][ix]==k
            if t is not None:
                code[part&(p<t)&(m>=t)]=1;code[part&(p>=t)&(m<t)]=0;code[part&(p<t)&(m<t)]=2;code[part&(p>=t)&(m>=t)]=3
                code[part&~np.isfinite(scores['score'][ii]).all(1)]=5
        code[~prep['available'][ii,1]]=4;code[(scores['texture'][ii]<5).all(1)]=6;code[((prep['selected_images'][ii]>=0).sum(-1)<3).any(1)]=7
        allcode=np.full(len(g['point_id']),9,np.int8);allcode[ix]=code;d['photo_code']=allcode[mp['point_index']]
        st=loadz(O/'sight'/f'{site}__{prior}.npz');d['free']=np.where(d['kind']==1,st['free10'],st['free5'])
        # Execute the original decision statements; the removed fusion/oracle arms
        # require evaluation labels and are irrelevant to method targets.
        text=(HERE/'judgments.py').read_text();a=text.index('      reg=np.full');b=text.index('      fp=PH/',a)
        import textwrap
        env=dict(np=np,d=d,N=len(d['n']),prior=prior,free=d['free'])
        exec(textwrap.dedent(text[a:b]),env)
        d['judge_region']=env['reg'][5];d['reason']=env['why'][5]
        savez(O/'method'/f'{site}__{prior}.npz',**d)
    dump(O/'complete.json',dict(at=now(),seconds=time.monotonic()-start,status='PASS_FULL_JUDGMENTS',calibration_recomputed=False,thresholds_recomputed=False,scientific_verdict=None))
if __name__=='__main__':main()
