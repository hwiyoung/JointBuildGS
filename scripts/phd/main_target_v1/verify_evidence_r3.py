"""Verify frozen sources, replayed medians, initial census and current delivery links."""
import ast,re,platform
import numpy as np
from common import *

def main():
    cfg,lock=locked_r3();gate=json.loads((CFG/'gate_r3.code.lock.json').read_text())
    for name,digest in gate['files'].items():assert sha(REPO/name)==digest,name
    old=json.loads((CFG/'target_v1.stage1.r2.lock.json').read_text())
    runtime=json.loads((CFG/'target_v1.runtime.r3.lock.json').read_text())
    for name,digest in runtime['files'].items():
        preserved=OUT/'revisions/r4_stage1_source/fork'/Path(name).relative_to('src/phd/forks/GeoGS-conf-guided-v1-r19')
        assert sha(preserved)==digest,name
    assert json.loads((OUT/'r2/preflight_verification.json').read_text())['maps_sha256_checked']==1838
    assert json.loads((OUT/'r3/verification/runtime.json').read_text())['status']=='PASS_DEFAULT_OFF_AST'
    assert json.loads((DOC/'tables/monitor_verification_r3.json').read_text())['status']=='PASS_MONITOR_DIAGNOSTICS'
    reps=json.loads((CFG/'representatives_v1.json').read_text())['rows'];expected={(r['site'],p) for r in reps for p in r['priors']}
    checks=[];render_count=0;total_views=0
    for site,prior in sorted(expected):
        root=OUT/'r3/preflight'/f'{site}_{prior}';r=json.loads((root/'initial_render.json').read_text())
        assert r['optimization_steps']==0 and r['criterion_m']==.05 and r['config_sha256']==lock['config_sha256']
        assert r['status']==('PASS' if r['pooled_median_m']<=.05 else 'FAIL_INITIAL_RENDER_DEPTH_5CM')
        assert json.loads((root/'unit.json').read_text())['status']=='PASS'
        assert json.loads((root/'seed_scale_check.json').read_text())['prior_scales_byte_identical']
        command=OUT/'r3/preflight_commands'/f'{site}_{prior}'
        assert json.loads((command/'receipt.json').read_text())['exit_code']==0
        binding=json.loads((command/'code_binding.json').read_text())
        for name,digest in old['files'].items():assert binding[name]==digest,name
        for name,digest in gate['files'].items():assert binding[name]==digest,name
        seeds=OUT/'r3/prior_only'/f'{site}_{prior}'
        with np.load(seeds/'seeds.npz') as p,np.load(OUT/'r2/stage1'/f'{site}_{prior}/seeds.npz') as f:
            n=len(p['xyz'])
            for key in ['xyz','target','normal','sigma','quaternion','origin','region','patch']:
                assert np.array_equal(p[key],f[key][:n]),key
            assert np.array_equal(p['keep_original'],f['keep_original'])
        for v in [x for x in r['views'] if x.get('representative')]:
            with np.load(root/(v['camera']+'.npz')) as z:
                a=z['render_depth'].astype('f8');b=z['target_depth'].astype('f8');owner=z['owner']
                good=(owner>=0)&np.isfinite(b)&(b>0);valid=good&np.isfinite(a)&(a>0)
                median=float(np.median(abs(a[valid]-b[valid])))
            assert abs(median-v['absolute_depth_error_median_m'])<1e-5
            assert int(valid.sum())==v['rendered_target_pixels'];render_count+=1
        replay=OUT/'r3/replay_v2'/f'{site}_{prior}';q=json.loads((replay/'verification.json').read_text())
        assert q['status']=='PASS_INDEPENDENT_GATE_REPLAY'
        e=np.load(replay/'absolute_errors_float64.npy',mmap_mode='r');assert sha(replay/'absolute_errors_float64.npy')==q['error_vector_sha256']
        assert float(np.median(e))==q['median_m'] and abs(q['median_m']-r['pooled_median_m'])<1e-5
        census=OUT/'r3/census'/f'{site}_{prior}';c=json.loads((census/'initial_background_sizes.json').read_text())
        with np.load(census/'initial_background_sizes.npz') as z:
            assert int((z['scale']>1.).sum())==c['count_gt_1m'] and float(z['scale'].max())==c['max_scale_m']
            with np.load(OUT/'r2/background'/site/prior/'background.npz') as bg:assert np.array_equal(bg['xyz'],z['xyz'])
            for top in c['top10']:
                i=top['background_index'];assert float(z['scale'][i])==top['scale_m']
                assert z['xyz'][i].tolist()==top['xyz_local_m']
        checks.append(dict(site=site,prior=prior,gate=r['status'],median_m=r['pooled_median_m'],replay_median_m=q['median_m'],
            initial_background_over_1m=c['count_gt_1m'],audit='PASS'));total_views+=len(r['views'])
    assert render_count==5 and total_views==982
    report=DOC/'영역별목표학습_보고_r3.md';body=report.read_text()
    assert len(re.findall(r'^## [1-8]\. ',body,re.M))==8
    links=[]
    for path in [report,DOC/'단계1_r3_재점검.md',DOC/'초기배경_크기_r3.md']:
        for link in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',path.read_text()):
            p=DOC/link;assert p.exists() and p.with_suffix('.json').exists();links.append(link)
    count=0
    for path in list(Path(__file__).parent.glob('*.py'))+list((REPO/'src/phd/forks/GeoGS-conf-guided-v1-r19').rglob('*.py')):
        ast.parse(path.read_text(),filename=str(path));count+=1
    assert not list((OUT/'r3/runs').glob('**/point_cloud.ply'))
    record=dict(at=stamp(),status='PASS_R3_EVIDENCE',experiment_status='STOP_STAGE1_PRIOR_ONLY_DEPTH_5CM',
        checks=checks,independent_replayed_views=total_views,representative_renders_checked=render_count,maps_verified_by_r2=1838,
        figure_pairs=len(set(links)),python_syntax_files=count,report_sha256=sha(report),config_sha256=lock['config_sha256'],
        training_steps=0,pilot_7000='NOT_RUN',scientific_verdict=None,environment=dict(python=platform.python_version(),numpy=np.__version__))
    dump(OUT/'r3/verification/evidence.json',record);dump(DOC/'tables/evidence_verification_r3.json',record)
    for folder in ['preflight','diagnose','census','replay_v2']:
        for p in (OUT/'r3'/folder).glob('*/*.json'):
            dump(DOC/'tables/r3_stage1_evidence'/folder/p.parent.name/p.name,json.loads(p.read_text()))
    print(json.dumps(record),flush=True)

if __name__=='__main__':main()
