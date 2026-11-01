"""Independent receipt, saved-pixel, frozen-code and complete-map audit of r2 3.5."""
import ast,re,platform
import numpy as np
from common import *

def main():
    cfg,lock=locked_r2();runtime=json.loads((CFG/'target_v1.stage1.r2.lock.json').read_text())
    for path,digest in runtime['files'].items():
        preserved=OUT/'revisions/r2_stage1_source/fork'/Path(path).relative_to('src/phd/forks/GeoGS-conf-guided-v1-r19')
        assert sha(preserved)==digest,path
    assert json.loads((OUT/'r2/verification/runtime.json').read_text())['status']=='PASS_DEFAULT_OFF_AST'
    reps=json.loads((CFG/'representatives_v1.json').read_text())['rows']
    expected={(r['site'],p) for r in reps for p in r['priors']}
    actual={(r['site'],r['prior']) for p in (OUT/'r2/preflight').glob('*/initial_render.json') for r in [json.loads(p.read_text())]}
    assert actual==expected,(actual,expected)
    views=0;checks=[];mapfiles=0
    for site in cfg['sites']+cfg['deferred_sites']:
        for prior in cfg['priors']:
            root=OUT/'r2/stage1'/f'{site}_{prior}';index=json.loads((root/'maps/index.json').read_text())
            assert index['config_sha256']==lock['config_sha256']
            assert index['target_sha256']==sha(OUT/'r2/targets'/f'{site}_{prior}.npz')
            for row in index['views'].values():
                assert sha(root/'maps'/row['file'])==row['sha256'];mapfiles+=1
    for site,prior in sorted(expected):
        root=OUT/'r2/preflight'/f'{site}_{prior}';r=json.loads((root/'initial_render.json').read_text())
        assert r['optimization_steps']==0 and r['criterion_m']==.05 and r['config_sha256']==lock['config_sha256']
        assert r['status']==('PASS' if r['pooled_median_m']<=.05 else 'FAIL_INITIAL_RENDER_DEPTH_5CM')
        assert r['pooled_pixels']==sum(v['rendered_target_pixels'] for v in r['views'])
        assert json.loads((root/'unit.json').read_text())['status']=='PASS'
        assert json.loads((root/'seed_scale_check.json').read_text())['status']=='PASS'
        commands=OUT/'r2/preflight_commands'/f'{site}_{prior}'
        assert json.loads((commands/'receipt.json').read_text())['exit_code']==0
        binding=json.loads((commands/'code_binding.json').read_text())
        for name,digest in runtime['files'].items():assert binding[name]==digest
        seed=json.loads((OUT/'r2/stage1'/f'{site}_{prior}'/'seed_receipt.json').read_text())
        assert seed['target_sha256']==sha(OUT/'r2/targets'/f'{site}_{prior}.npz')
        assert json.loads((OUT/'r2/verification'/f'stage1_{site}_{prior}.json').read_text())['status']=='PASS_STAGE1_INPUTS'
        for view in [v for v in r['views'] if v.get('representative')]:
            with np.load(root/(view['camera']+'.npz')) as z:
                A,B=z['render_depth'],z['target_depth'];valid=np.isfinite(A)&np.isfinite(B)&(A>0)&(B>0)
                error=np.abs(A[valid].astype(float)-B[valid].astype(float));median=float(np.median(error))
            assert abs(median-view['absolute_depth_error_median_m'])<=1e-5
            assert len(error)==view['rendered_target_pixels'];views+=1
        if r['status']!='PASS':
            diagnostic=json.loads((OUT/'r2/diagnose'/f'{site}_{prior}'/'diagnosis.json').read_text())
            assert diagnostic['training_steps']==0
            for d in diagnostic['rows']:assert d['analytic_plane_control']['quantiles'][2]<.001
        checks.append(dict(site=site,prior=prior,median_m=r['pooled_median_m'],gate=r['status'],audit='PASS'))
    assert views==5 and mapfiles==1838
    syntax=0
    for p in list(Path(__file__).parent.glob('*.py'))+list((REPO/'src/phd/forks/GeoGS-conf-guided-v1-r19').rglob('*.py')):
        ast.parse(p.read_text(),filename=str(p));syntax+=1
    report=DOC/'영역별목표학습_보고_r2.md';body=report.read_text()
    assert len(body)<20000 and len(re.findall(r'^## [1-8]\. ',body,re.M))==8
    links=re.findall(r'!\[[^\]]*\]\(([^)]+)\)',body)
    for link in links:
        p=DOC/link;assert p.is_file() and p.with_suffix('.json').is_file()
    assert not list((OUT/'r2/runs').glob('**/point_cloud.ply'))
    failed=any(r['gate']!='PASS' for r in checks)
    record=dict(at=stamp(),status='PASS_PREFLIGHT_EVIDENCE',initial_render_gate='FAIL' if failed else 'PASS',
        checks=checks,maps_sha256_checked=mapfiles,representative_renders_checked=views,python_files_syntax_checked=syntax,
        report_sha256=sha(report),figure_pairs=len(links),config_sha256=lock['config_sha256'],runtime_lock_sha256=sha(CFG/'target_v1.stage1.r2.lock.json'),
        training_steps=0,scientific_verdict=None,environment=dict(python=platform.python_version(),numpy=np.__version__))
    dump(OUT/'r2/preflight_verification.json',record);dump(DOC/'tables/preflight_verification_r2.json',record)
    for folder in ['preflight','diagnose']:
        for p in (OUT/'r2'/folder).glob('*/*.json'):
            if p.name in ['unit.json','seed_scale_check.json','initial_render.json','diagnosis.json']:
                dump(DOC/'tables/r2_stage1_evidence'/folder/p.parent.name/p.name,json.loads(p.read_text()))
    print(json.dumps(record),flush=True)

if __name__=='__main__':main()
