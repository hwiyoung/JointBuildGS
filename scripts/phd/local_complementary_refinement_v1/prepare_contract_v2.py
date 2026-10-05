"""Freeze the declared main revision without selecting anything from reference errors."""
import argparse
import json
from pathlib import Path
import time

from common import read, record, require_docker, sha, write_new


def checked(root, relative):
    root, relative = Path(root), Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Unsafe sealed path')
    result = root / relative
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError('Sealed path escapes mount')
    return result


def main():
    require_docker()
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='/config.json')
    parser.add_argument('--output', default='/contracts')
    args = parser.parse_args()
    cfg = read(args.config)
    out = Path(args.output)
    if (out / 'input_binding.json').exists():
        raise FileExistsError('Preserve frozen contracts')
    if cfg['schema'] != 'jbgs.local_complementary_refinement.v2' or cfg['scientific_verdict'] is not None:
        raise ValueError('Expected technical main v2')
    if any(Path(p).exists() for p in ('/reference', '/references', '/parent', '/artifacts/JointBuildGS')):
        raise ValueError('References and broad artifact mounts prohibited')
    started = time.time()
    result = dict(task_id=cfg['task_id'], revision='main_v2', scientific_verdict=None,
        reference_accessed=False, config=record(args.config), threshold_policy=cfg['local_weight'],
        tau0_m=cfg['local_weight']['tau0_m'], tau1_m=cfg['local_weight']['tau1_m'],
        parent_preparation_binding=record('/preparation/input_binding.json'),
        input_audit=record('/input_audit/input_audit_v2.json'), regions={},
        producer=record(__file__), started_unix=started)
    source = read('/parent_source_identity.json')
    if sha('/input_audit/input_audit_v2.json') != cfg['local_weight']['input_audit_sha256']:
        raise ValueError('Input audit differs from threshold decision')
    audit = read('/input_audit/input_audit_v2.json')
    if (audit.get('status') != 'PASS_INPUT_CONVENTION_AUDIT_WITH_RECORDED_LIMITATIONS'
        or audit.get('reference_accessed') is not False or audit.get('evaluation_rgb_accessed') is not False
        or audit.get('scientific_verdict') is not None):
        raise ValueError('Input-only audit gate did not pass')
    old = read('/preparation/input_binding.json')
    for region in cfg['regions']:
        root = Path('/parent_inputs') / region
        manifest_path = root / 'input_manifest.json'
        manifest = read(manifest_path)
        if manifest['status'] != 'INPUTS_SEALED_FOR_EXECUTION' or manifest['region'] != region:
            raise ValueError('Invalid parent seal')
        if sha(manifest_path) != old['regions'][region]['manifest']['sha256']:
            raise ValueError('Preparation input seal differs')
        for item in manifest['files']:
            if sha(checked(root, item['path'])) != item['sha256']:
                raise ValueError('Input bytes differ: ' + item['path'])
        anchor = Path('/anchors') / region
        anchor_receipt = read(anchor / 'receipt.json')
        checkpoint = record(anchor / 'checkpoint.pth')
        if (anchor_receipt['iteration'] != 8000 or not anchor_receipt['after_protection_registration']
            or checkpoint['sha256'] != anchor_receipt['checkpoint_sha256']
            or checkpoint['sha256'] != old['regions'][region]['checkpoint']['sha256']):
            raise ValueError('Complete Anchor identity differs')
        entry = dict(manifest=record(manifest_path), checkpoint=checkpoint,
            anchor_receipt=record(anchor / 'receipt.json'), training_paths=manifest['training_paths'],
            verified_input_file_count=len(manifest['files']), baselines={})
        for condition in cfg['conditions']:
            name = condition['parent_condition']
            run = Path('/parent_runs') / region / name
            invocation, receipt = read(run / 'train_invocation.json'), read(run / 'train_receipt.json')
            if (receipt['status'] != 'PASS' or invocation['region'] != region or invocation['condition'] != name
                or invocation['input_manifest_sha256'] != entry['manifest']['sha256']
                or invocation['implementation_hashes'] != source['parent_implementation_hashes']
                or invocation['runtime_image_id'] != cfg['runtime']['image_id']):
                raise ValueError('Parent completed run does not match shared input/source/runtime')
            complete = run / 'model/jbgs_complete/iteration_30000'
            state_receipt = read(complete / 'receipt.json')
            if state_receipt['iteration'] != 30000 or state_receipt['scientific_verdict'] is not None:
                raise ValueError('Parent final state not complete')
            final = record(complete / 'checkpoint.pth')
            ply = record(complete / 'point_cloud.ply')
            if final['sha256'] != state_receipt['checkpoint_sha256'] or ply['sha256'] != state_receipt['ply_sha256']:
                raise ValueError('Parent final state bytes changed')
            entry['baselines'][name] = dict(train_invocation=record(run / 'train_invocation.json'),
                train_receipt=record(run / 'train_receipt.json'), final_state_receipt=record(complete / 'receipt.json'),
                final_checkpoint=final, final_ply=ply, status='COMPLETE_BYTES_VERIFIED_REUSE_NO_TRAINING')
            print(json.dumps(dict(region=region, baseline=name, status='VERIFIED')), flush=True)
        result['regions'][region] = entry
    result.update(status='INPUTS_AND_COMMON_THRESHOLDS_FROZEN', verified_baseline_count=18,
        finished_unix=time.time(), wall_seconds=time.time()-started)
    write_new(out / 'input_binding.json', result)
    print(json.dumps(dict(status=result['status'], scientific_verdict=None)), flush=True)


if __name__ == '__main__':
    main()
