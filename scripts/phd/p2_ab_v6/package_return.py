"""Freeze the bounded A-to-B development return; reject changed inputs or QA failure."""
import argparse
import ast
from datetime import datetime, timezone
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import unittest
from scripts.phd.p2_ab_v4.package_return import sha


def main(output,qa_run):
    artifact=Path('/artifacts/JointBuildGS');base=artifact/'phase-payloads/phd/p2_ab_v6'
    output.mkdir(parents=True,exist_ok=False)
    preserved={}
    for version,filename,receipts_key in [
        ('v2','technical_result_manifest_v2.json','promoted_results'),
        ('v3','technical_development_manifest_v1.json','receipts'),
        ('v4','technical_return_manifest_v1.json','receipts')]:
        manifest=json.loads((Path('artifacts/manifests/phd/p2_ab_'+version)/filename).read_text())
        for path,expected in manifest['source_sha256'].items():
            if sha(path)!=expected:raise ValueError('Preserved old source changed: '+path)
        for row in manifest[receipts_key].values():
            if sha(artifact/row['artifact_relative_path'])!=row['sha256']:raise ValueError('Preserved old receipt changed')
        preserved[version]=dict(status='PASS',source_files=len(manifest['source_sha256']),receipts=len(manifest[receipts_key]))
    paths={
        'A':base/'PHD-P2-AB-V6-A-OBSERVATIONAL-v3/technical_receipt.json',
        'B':base/'PHD-P2-AB-V6-B-SURFACE-v3/result.json',
        'C':base/'PHD-P2-AB-V6-C-REFERENCE-v1/evaluation/evaluation.json',
        'viewer':base/'PHD-P2-AB-V6-VIEWER-v1/viewer/technical_receipt.json',
        'browser':base/qa_run/'browser_qa.json'}
    results={name:json.loads(p.read_text()) for name,p in paths.items()}
    if results['browser']['status']!='PASS':raise ValueError('Browser QA failed')
    verified={}
    for name in ('A','B','C','viewer'):
        for field in ('source_hashes','input_hashes'):
            for path,expected in results[name].get(field,{}).items():
                actual=verified.setdefault(path,sha(path))
                if actual!=expected:raise ValueError('Executed input/source changed: '+path)
    viewer=paths['viewer'].parent
    for path,expected in results['viewer']['output_sha256'].items():
        if sha(viewer/path)!=expected:raise ValueError('Viewer output changed')
    for row in results['browser']['screenshots']:
        if sha(paths['browser'].parent/row['filename'])!=row['sha256']:raise ValueError('QA screenshot changed')
    if sha(paths['browser'].parent/'browser_qa_source.mjs')!=sha('scripts/phd/p2_ab_v6/browser_qa.mjs'):
        raise ValueError('Executed browser driver changed')
    data=json.loads((viewer/'data.json').read_text())
    count=sum(row['common_pixels'] for row in data['views'])
    if count!=5150892 or len(data['views'])!=11 or len(data['models'])!=23:raise ValueError('Comparison domain mismatch')
    for model in data['models']:
        if model['kind']!='rgb':continue
        metrics=[v['metrics'][model['id']] for v in data['views']]
        if any(m['pixels']!=v['common_pixels'] for m,v in zip(metrics,data['views'])):raise ValueError('Different denominators')
        mae=sum(m['absolute_rgb_sum'] for m in metrics)/(3*count)
        psnr=-10*math.log10(sum(m['squared_rgb_sum'] for m in metrics)/(3*count))
        expected=data['summary'][model['id']]
        if abs(mae-expected['mae'])>1e-12 or abs(psnr-expected['psnr_db'])>1e-12:raise ValueError('RGB summary arithmetic')
    final=next(r for r in results['B']['arms'] if r['arm']=='dynamic_surface_guard')
    if final['changed_outside_allowable_count'] or final['evidence_worse_than_initial_count'] or not final['protected_surface']['passed']:
        raise ValueError('Final joint contract failed')
    files=[]
    for folder in ('src/phd/p2_ab_v6','scripts/phd/p2_ab_v6','configs/phd/p2_ab_v6','docs/experiments/phd/p2_ab_v6','src/apps/p2_ab_inspector_v6'):
        files.extend(p for p in Path(folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    files.extend(Path('tests/phd').glob('test_p2_ab_v6_*.py'))
    for path in files:
        content=path.read_text()
        if path.suffix=='.py':ast.parse(content,filename=str(path))
        if path.suffix=='.json':json.loads(content)
        if content and not content.endswith('\n'):raise ValueError('Missing newline: '+str(path))
        if any(line!=line.rstrip() for line in content.splitlines()):raise ValueError('Trailing whitespace: '+str(path))
        if path.suffix=='.md':
            for target in re.findall(r'\]\(([^)]+)\)',content):
                if '://' not in target and not target.startswith('#') and not (path.parent/target.split('#')[0]).exists():
                    raise ValueError('Broken local link: '+target)
    stream=io.StringIO()
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName('tests.phd.'+p.stem) for p in Path('tests/phd').glob('test_p2_ab_v6_*.py'))
    tests=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (output/'unit_tests.txt').write_text(stream.getvalue())
    if not tests.wasSuccessful():raise ValueError(stream.getvalue())
    source_hashes={str(p):sha(p) for p in sorted(files)}
    for p in files:
        dest=output/'source_snapshot'/p;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    payloads={}
    for version in (1,2,3):
        for prefix,receipt in [('A-OBSERVATIONAL','technical_receipt.json'),('B-SURFACE','result.json')]:
            root=base/f'PHD-P2-AB-V6-{prefix}-v{version}'
            selected=[root/receipt,root/'config.json']
            if prefix.startswith('A'):
                selected.extend(root.glob('*.npz'))
            elif version==3:
                selected.extend(root.glob('*/gaussians*.npz'));selected.extend(root.glob('*/extracted_surface.npz'))
                selected.extend(root.glob('*/conditional_status.npz'));selected.extend(root.glob('*/training.jsonl'))
            for p in selected:
                payloads[str(p.relative_to(artifact))]=sha(p)
    receipt=dict(schema='jointbuildgs.phd.p2_ab_v6.technical_return.v1',
        task_id='PHD-P2-AB-V6-OBSERVATION-TO-SURFACE-DEVELOPMENT-v1',
        status='CONDITIONAL_MECHANISM_EXPERIMENT_AND_VISUAL_RETURN_COMPLETE',
        scientific_verdict=None,utc=datetime.now(timezone.utc).isoformat(),
        git_head=os.environ.get('JBGS_SOURCE_GIT_HEAD'),container_image=os.environ.get('JBGS_CONTAINER_IMAGE_ID'),
        versions={p:importlib.metadata.version(p) for p in ('torch','numpy','scipy','gsplat')},
        coordinates=dict(frame='SCENE_LOCAL_XYZ',horizontal_crs='EPSG:25832',world_shift_m=[690953,5336071,604]),
        source_sha256=source_hashes,payload_sha256=payloads,
        receipts={name:dict(artifact_relative_path=str(p.relative_to(artifact)),sha256=sha(p)) for name,p in paths.items()},
        preserved=preserved,unit_tests=tests.testsRun,browser_checks=len(results['browser']['checks']),
        viewer_url='http://127.0.0.1:8896/PHD-P2-AB-V6-VIEWER-v1/viewer/?view=333',
        common_pixels=count,A_observable_gaussians=results['A']['observable_gaussians'],
        B_final_summary={k:final[k] for k in ('changed_gt1mm','conditional_eligible_count','unresolved_count','changed_outside_allowable_count','evidence_worse_than_initial_count','protected_surface')},
        limitations=['Full P2 joint source/systematic error calibration and automatic source selection incomplete.',
          'Observational envelope covers 381/266361 Gaussians; transferred local normal intervals are conditional.',
          'Only 630 sampled training rays protected; full boundaries/topology not certified.',
          'All 242 initially correction-needed points remain unresolved after guarded optimization.',
          'No substantive incremental appearance/detail gain; no densification or new semantic geometry tested.',
          'P2 is development evidence; evaluation reference not newly accuracy-calibrated.'])
    (output/'technical_return_manifest_v1.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ('status','preserved','unit_tests','browser_checks','common_pixels')}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--qa-run',default='PHD-P2-AB-V6-BROWSER-QA-v1')
    args=parser.parse_args();main(args.output,args.qa_run)
