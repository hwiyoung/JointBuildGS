"""Seal the reviewed diagnostic and distinguish execution from actual update evidence."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text())


def main():
    if not Path('/.dockerenv').exists(): raise RuntimeError('Docker required')
    ap=argparse.ArgumentParser();ap.add_argument('--attempt',type=Path,required=True)
    ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--git-base',required=True)
    a=ap.parse_args();out=a.attempt/'technical_result_manifest_v1.json'
    if out.exists(): raise FileExistsError(out)
    paths=['prepare_v2','prepare_screen']+[f'probe/{r}' for r in ('P1','P2','P3')]
    paths += [f'screen/{r}' for r in ('P2','P3')]+[f'reference/{r}' for r in ('P1','P2','P3')]
    paths += ['review','mobile_overview_v2','qa_v2']
    receipts=[]
    for name in paths:
        p=a.attempt/name/'receipt.json';r=read(p)
        assert r['status'].startswith('PASS') and r.get('scientific_verdict') is None
        receipts.append(dict(path=str(p.relative_to(a.attempt)),sha256=sha(p),status=r['status']))
    cases=read(a.attempt/'prepare_v2/cases.json');summary=read(a.attempt/'review/summary.json')
    assert len(summary)==9
    actual=sum(r['changed_gaussians'] for r in summary)
    assert actual==0, 'This receipt describes the observed abstention-only attempt'
    screen={r:read(a.attempt/f'screen/{r}/receipt.json') for r in ('P2','P3')}
    assert all(r['eligible_count']==0 and r['modified_gaussians']==0 for r in screen.values())
    qa=read(a.attempt/'qa_v2/receipt.json')
    assert qa['html_sha256']==sha(a.attempt/'review/index.html')
    assert qa['data_sha256']==sha(a.attempt/'review/data.js')
    assert all(c['pass'] for c in qa['checks']) and qa['stage_card_count']==72
    for im in qa['screenshots']: assert sha(a.attempt/'qa_v2'/im['path'])==im['sha256']
    frozen=a.attempt/'final_source';frozen.mkdir(exist_ok=False)
    sources=[]
    for directory in ['configs/phd/mvs_surface_update_v1','scripts/phd/mvs_surface_update_v1',
                      'docs/experiments/phd/mvs_surface_update_v1','src/apps/mvs_surface_update_v1']:
        sources.extend(p for p in (a.repo/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    sources.extend([a.repo/'src/phd/mvs_surface_update_v1.py'])
    sources.extend(a.repo/p for p in ['tests/phd/test_mvs_surface_update_v1.py',
        'tests/phd/test_mvs_gaussian_probe_v1.py','tests/phd/test_mvs_surface_update_reference_v1.py',
        'tests/phd/test_mvs_association_screen_v1.py'])
    source_rows=[]
    for p in sorted(sources):
        relative=p.relative_to(a.repo);dest=frozen/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,dest);source_rows.append(dict(path=str(relative),sha256=sha(p)))
    inventory=read(a.attempt/'prepare_v2/candidate_inventory.json')
    counts=[]
    for region in cases['regions']:
        rid=region['id'];rr=[r for r in inventory if r['camera'].startswith(rid+'_')]
        counts.append(dict(region=rid,discrepancy_observations=sum(r['candidate_points'] for r in rr),
            admitted_observations=sum(r['admitted_probe_points'] for r in rr),
            screened_admitted_observations=len(screen[rid]['cases']) if rid in screen else 0,
            eligible_update_observations=0,changed_gaussians=0))
    manifest=dict(schema='jbgs.mvs_surface_update.technical_result.v1',task_id=cases['task_id'],
        scientific_verdict=None,status='PARTIAL_NO_ELIGIBLE_UPDATE',technical_pipeline_verified=True,
        actual_update_effect_comparison_available=False,artifact_root_local='../JointBuildGS-artifacts',
        artifact_root_container='/artifacts/JointBuildGS',
        attempt_relative='phase-payloads/phd/mvs_surface_update_v1/PHD-MVS-SURFACE-UPDATE-v1/'+a.attempt.name,
        git_base=a.git_base,receipts=receipts,source_snapshot='final_source',source_sha256=source_rows,
        regions=counts,representative_cases=9,stage_cards=72,
        browser=dict(checks=qa['check_count'],desktop_width=1440,mobile_width=390,
            desktop_cards=72,mobile_cards=72,artifacts=len(qa['resources']),screenshots=len(qa['screenshots'])),
        renderer='Exact native GeoGS-state-camera-v1 planar surfel renderer bound by Anchor8k implementation hashes',
        optimization_continuation=False,checkpoint_and_existing_training_modified=False,
        actual_gaussian_edits=actual,evaluation_reference_used_for_selection=False,
        reference='UAS evaluation only after probe freeze; same original return IDs and paired support',
        crs='EPSG:25832 shifted local; inherited absolute datum limitations',depth_axis='camera_Z_m',
        interpretation='No eligible edit under frozen gates. Zero before-after differences do not establish correction or preservation after an edit.',
        preserved_earlier_payloads=['prepare','mobile_overview','qa'],
        review_url='http://127.0.0.1:8908/review/',binding='loopback',
        mobile_summary='mobile_overview_v2/P1_P2_P3_overview.png',
        staged_pdf='review/P1_P2_P3_eight_stages.pdf',
        comparison_pdf='review/all_cases_mobile.pdf',
        report='docs/experiments/phd/mvs_surface_update_v1/RESULT_ko_v1.md')
    out.write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(status=manifest['status'],manifest=str(out),sha256=sha(out),counts=counts)))


if __name__=='__main__': main()
