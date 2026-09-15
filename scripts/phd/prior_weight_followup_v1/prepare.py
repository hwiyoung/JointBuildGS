"""Freeze three prior-only interventions from existing region-weight runs."""
import hashlib
import json
from pathlib import Path
import shutil


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def write(p,v):
    with Path(p).open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2)


def main():
    assert Path('/.dockerenv').exists()
    repo,p,out=Path('/repo'),Path('/payload'),Path('/out')
    spec=read(repo/'configs/phd/region_weight_v1/prior_0005_v1.json')
    write(out/'config.json',spec)
    shutil.copytree(repo/'scripts/phd/prior_weight_followup_v1',out/'scripts')
    viewer=p/spec['viewer'];write(out/'baseline_manifest.json',read(viewer/'weights_v1/manifest.json'))
    audit=[]
    for region in spec['regions']:
        is_p1=region=='P1';old=p/spec['baseline_p1'] if is_p1 else p/spec['baseline_p2p3']/region
        parent=old if is_p1 else old.parent
        target=out/region;target.mkdir()
        src=target/'source';shutil.copytree(parent/'source',src,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        provname='p1_single_view_weight_source_provenance.json' if is_p1 else 'region_weight_source_provenance.json'
        helper='jbgs_p1_weight.py' if is_p1 else 'jbgs_region_weight.py'
        prov=read(src/provname)
        for rel,h in prov['prepared_payload_hashes'].items():assert sha(src/rel)==h,rel
        before=sha(src/helper);text=(src/helper).read_text();assert '.005' in text
        (src/helper).write_text(text.replace('.005','.0005'))
        compile((src/helper).read_text(),helper,'exec')
        after=sha(src/helper)
        for key in ['prepared_payload_hashes','prepared_implementation_hashes','helper_sha256']:
            assert helper in prov[key];prov[key][helper]=after
        prov['prior_followup']=dict(parent_provenance_sha256=sha(parent/'source'/provname),
            changed_files=[helper],before_sha256=before,after_sha256=after,
            prior_weight=[.005,.0005],training_objective_and_masks_otherwise_unchanged=True)
        prov['policy']=prov.get('policy','').replace('.005','.0005')
        (src/provname).write_text(json.dumps(prov,indent=2))
        shutil.copytree(old/'mask',target/'mask')
        cfg=read(old/'config.json');assert cfg['prior_weight']==.005 and cfg['visual_weight']==.05
        cfg.update(task_id=spec['task_id'],authorization=spec['authorization'],prior_weight=.0005,alphas=[4],
                   baseline_config_sha256=sha(old/'config.json'),baseline_relative=str(old.relative_to(p)))
        write(target/'config.json',cfg)
        scripts=target/'scripts';scripts.mkdir()
        family='p1_single_view_weight_v1' if is_p1 else 'region_weight_v1'
        for name in ['run_phase.py','validate_gate.py','viewer_publish.py']:
            text=(repo/'scripts/phd'/family/name).read_text().replace('.005','.0005')
            if name=='run_phase.py':
                text=text.replace('choices=(0, 1, 4)','choices=(4,)')
                text=text.replace("if not all(row['mvs_weight'] == cfg['visual_weight'] for row in traces):",
                    "if not all(row['mvs_weight'] == cfg['visual_weight'] and row['prior_weight'] == cfg['prior_weight'] for row in traces):")
            if name=='viewer_publish.py':
                text=text.replace("'/driver/viewer_config.json'", "'/viewer_config.json'")
                text=text.replace('ALPHAS = (0, 1, 4)','ALPHAS = (4,)').replace('total=3','total=1').replace('{count}/3','{count}/1').replace('count == 3','count == 1')
                text=text.replace("checkpoint_iteration=30000,", "checkpoint_iteration=30000, prior_weight=.0005, r1_weight=4,")
            compile(text,name,'exec');(scripts/name).write_text(text)
        shutil.copyfile(repo/'scripts/phd/geogs_mvs_pgsr_v1/viewer/export_geometry.py',scripts/'export_geometry.py')
        for folder in ['parent_scripts','legacy_scripts']:(target/folder).mkdir()
        for name in ['run_phase.py','finalize.py']:
            shutil.copyfile(parent/'parent_scripts'/name,target/'parent_scripts'/name)
        shutil.copyfile(repo/'scripts/phd/geogs_p1p2p3_v1/parse_extraction.py',target/'legacy_scripts/parse_extraction.py')
        vc=read(viewer/'p1_weights_v1/source/viewer_config.json') if is_p1 else read(old/'viewer_config.json')
        vc.update(task_id=spec['task_id'],config_sha256=sha(target/'config.json'),
                  url_prefix='/data/prior_weights_v1/'+region+'/',prior_weight=.0005)
        write(target/'viewer_config.json',vc)
        (target/'status.txt').write_text('QUEUED\n')
        prefix='p1_weight' if is_p1 else 'region_weight'
        first=old/'train/alpha_4/model'/(prefix+'_first_step.json')
        shutil.copyfile(first,target/'baseline_first_step.json')
        trace=old/'train/alpha_4/model'/(prefix+'_camera_trace.jsonl')
        shutil.copyfile(trace,target/'baseline_camera_trace.jsonl')
        audit.append(dict(region=region,baseline_config_sha256=sha(old/'config.json'),
            config_sha256=sha(target/'config.json'),source_provenance_sha256=sha(src/provname),
            mask_sha256=cfg['mask_sha256'],anchor_sha256=cfg['anchor_sha256'],changed_helper=prov['prior_followup']))
    write(out/'preparation.json',dict(status='PASS',scientific_verdict=None,regions=audit))
    excluded={'status.txt','frozen_files.json'}
    ledger={str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.is_file() and f.name not in excluded and f.suffix!='.log'}
    write(out/'frozen_files.json',ledger)
    print(json.dumps(audit))


if __name__=='__main__':main()
