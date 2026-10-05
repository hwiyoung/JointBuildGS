"""Create the final additive resolver; preserve every existing run namespace."""
import argparse
import json
from pathlib import Path
import subprocess
from scripts.phd.p2_ab_v1.c_evaluate import read,sha,write,REPO


def main(args):
    out=REPO/'artifacts/manifests/phd/p2_ab_v1/technical_result_manifest_v1.json'
    if out.exists():raise FileExistsError(out)
    inventory={}
    for name in ['src/phd/p2_ab_v1','src/apps/p2_ab_inspector_v1','scripts/phd/p2_ab_v1',
                 'configs/phd/p2_ab_v1','docs/experiments/phd/p2_ab_v1']:
        for p in sorted((REPO/name).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:
                inventory[str(p.relative_to(REPO))]=sha(p)
    for p in sorted((REPO/'tests/phd').glob('test_p2_ab*.py')):
        inventory[str(p.relative_to(REPO))]=sha(p)
    old_inventory=args.base/'PHD-P2-AB-AUDIT-v1/preserved_workspace.sha256'
    verified=[]
    for line in old_inventory.read_text().splitlines():
        digest,name=line.split('  ',1)
        if sha(REPO/name)!=digest:raise RuntimeError('Existing file changed: '+name)
        verified.append(name)
    targets={
      'common':'PHD-P2-AB-COMMON-v2/common/sample_manifest.json',
      'frame':'PHD-P2-AB-COMMON-v2/common/frame_audit.json',
      'reference':'PHD-P2-AB-COMMON-v2/evaluation_v2/reference_manifest.json',
      'decision':'PHD-P2-AB-A-v1/TECHNICAL_RETURN.json',
      'a_figures':'PHD-P2-AB-A-FIGURES-v2/A_decision_validation.pdf',
      'integration':'PHD-P2-AB-C-v2/technical_receipt.json',
      'geometry':'PHD-P2-AB-C-v2/reconstruction_unit_metrics.json',
      'appearance':'PHD-P2-AB-C-APPEARANCE-v2/technical_receipt.json',
      'summary':'PHD-P2-AB-C-SUMMARY-v2/reconstruction_summary.csv',
      'figure':'PHD-P2-AB-C-SUMMARY-v2/reconstruction_comparison.pdf',
      'independent_qa':'PHD-P2-AB-FINAL-QA-v2/QA_RECEIPT.json',
      'browser_qa':'PHD-P2-AB-VIEWER-QA-v1/technical_receipt.json'}
    results={k:dict(artifact_relative_path='phase-payloads/phd/p2_ab_v1/'+n,sha256=sha(args.base/n),
                    bytes=(args.base/n).stat().st_size) for k,n in targets.items()}
    suite=read(REPO/'configs/phd/p2_ab_v1/c_suite_v2.json')
    b={name:dict(result_sha256=sha(args.base/name/'result.json'),
                 artifact_relative_path='phase-payloads/phd/p2_ab_v1/'+name) for name in suite['b_roots']}
    namespaces=sorted(p.name for p in args.base.iterdir() if p.is_dir())
    result=dict(schema='jointbuildgs.phd.p2_ab.technical_result_manifest.v1',task_id='PHD-P2-AB-v1',
        status='DEVELOPMENT_IMPLEMENTATION_AND_SEPARATED_INTEGRATION_VERIFIED',scientific_verdict=None,
        authorization='2026-09-06 direct user: independent A/B design, required implementation/development experiments and same-region separated/full validation; preserve prior work',
        research_result='No demonstrated additional benefit of finite-range decision or constrained reconstruction in this bounded development comparison',
        git_head=subprocess.check_output(['git','-c',f'safe.directory={REPO}','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        committed=False,reproduction='HEAD alone does not contain this task. Use per-run source/config snapshots and frozen input hashes. Existing run IDs fail closed.',
        artifact_root_host='/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts',
        artifact_root_container='/artifacts/JointBuildGS',local_storage_is_not_durable_backup=True,
        counts=dict(all_xy_units=552,development_units=64,decision_candidates=152,decision_rows=43008,
                    aggregate_decision_settings=672,reconstruction_comparisons=20,original_dn_comparisons=1,all_abstain_paths=1,
                    reference_points_prism=2325976,reference_points_development=268544,common_appearance_rays=69722),
        containers=dict(main='sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774',
                        dn='jointbuildgs:dn-splatter-upstream-97588b4; exact image recorded in B adapter/driver'),
        promoted_results=results,b_runs=b,final_repository_source_sha256=inventory,
        existing_work_preservation=dict(verified_files=len(verified),inventory_sha256=sha(old_inventory),all_unchanged=True,
                                       raw_inputs_and_existing_payloads='Mounted read-only in measurement/training; original partial/smoke/failure outputs retained'),
        preserved_new_namespaces=namespaces,
        viewer=dict(url='http://127.0.0.1:8893/PHD-P2-AB-C-v2/viewer/',container='jbgs-p2-ab-inspector-8893',
                    access='loopback only; readonly p2_ab_v1 artifact subtree; existing services unchanged'),
        remaining=['Camera/alignment/current visibility and continuous-domain error contracts uncalibrated',
                   'Conditional sampled point support is not certified surface area',
                   'UAS datum/epoch/acquisition uncertainty is not an absolute metric accuracy certificate',
                   '66 historical development images and exact937-derived MVS are not independent confirmatory data',
                   'Topology, actual boundary joins/detail authority and converged end-to-end performance remain unvalidated',
                   'No Roofer/LoD2 output or scientific verdict inferred from these surface samples'])
    write(out,result)
    print(json.dumps(dict(status='PASS',manifest=str(out),preserved_files=len(verified),new_source_files=len(inventory))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);main(p.parse_args())
