"""Verify saved controls for the two native prior-depth contrasts."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--image-id', required=True)
    a = p.parse_args()
    cfg = json.loads(a.config.read_text())
    a.output.mkdir(parents=True, exist_ok=False)
    summary_path = a.source / cfg['summary']
    inputs = {cfg['summary']: digest(summary_path)}
    summaries = list(csv.DictReader(summary_path.open()))
    results = []
    for region in cfg['regions']:
        for condition in cfg['conditions']:
            matched = [r for r in summaries if r['region'] == region and r['condition'] == condition]
            assert len(matched) == 1
            row = matched[0]
            for path_field, hash_field in [('source_trace', 'source_trace_sha256'), ('source_train_receipt', 'source_train_receipt_sha256')]:
                actual = digest(a.source / row[path_field])
                assert actual == row[hash_field], row[path_field]
                inputs[row[path_field]] = actual
            trace = [json.loads(line) for line in (a.source / row['source_trace']).read_text().splitlines()]
            trace = [r for r in trace if r['iteration'] > cfg['refinement_after_iteration']]
            assert [r['iteration'] for r in trace] == list(range(8100, 30001, 100))
            receipt = json.loads((a.source / row['source_train_receipt']).read_text())
            command = receipt['command']
            results.append({
                'region': region, 'condition': condition, 'samples': len(trace),
                'iteration_min': trace[0]['iteration'], 'iteration_max': trace[-1]['iteration'],
                'prior_weights': sorted({r['lod_weight'] for r in trace}),
                'da3_weights': sorted({r['da_weight'] for r in trace}),
                'protected_counts': sorted({r['protected'] for r in trace}),
                'da3_confidence_flag_present': '--use_confidence' in command,
                'training_input_manifest_sha256': receipt['input_manifest_sha256'],
                'actual_training_source_sha256': receipt['implementation_hashes']['train.py'],
                'source_trace': row['source_trace'],
                'interpretation': 'Whole-context sampled controls; not local visibility, effective gradient contribution, or proof of cause.'
            })
    for region in cfg['regions']:
        pair = [r for r in results if r['region'] == region]
        assert len({r['training_input_manifest_sha256'] for r in pair}) == 1
        assert len({r['actual_training_source_sha256'] for r in pair}) == 1
    assert all(digest(a.source / path) == value for path, value in inputs.items())
    out = {'task_id': cfg['task_id'], 'scientific_verdict': None, 'status': 'PASS_SAVED_CONTROL_AUDIT',
           'rows': results, 'input_hashes': inputs, 'inputs_unchanged': True,
           'execution': {'image_id': a.image_id, 'script_sha256': digest(Path(__file__)),
                         'config_sha256': digest(a.config), 'new_training': 0, 'new_renders': 0,
                         'new_mesh_extractions': 0, 'new_model_inference': 0}}
    (a.output / 'receipt.json').write_text(json.dumps(out, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': out['status'], 'rows': results, 'scientific_verdict': None}, ensure_ascii=False))


if __name__ == '__main__':
    main()
