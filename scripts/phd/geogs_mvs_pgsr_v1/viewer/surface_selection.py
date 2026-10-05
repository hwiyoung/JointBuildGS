"""Select an existing native raw surface bound to the exact displayed training run.

This module checks metadata and path containment. The caller must check the raw
payload SHA256 when loading/exporting it. None means no completed surface was
found; it does not authorize a different representation as a substitute.
"""
import json
from pathlib import Path
import re


EXTRACTION_KEYS = ('mesh_res', 'num_cluster', 'voxel_size_m', 'sdf_trunc_m', 'depth_trunc_m')
CONDITIONS = {.005: 'D005_Pnative', .0005: 'D0005_Pnative'}


def _read(path):
    try:
        value = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ValueError('Invalid surface-selection metadata: ' + str(path)) from error
    if not isinstance(value, dict):
        raise ValueError('Expected surface-selection metadata object: ' + str(path))
    return value


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _null(value, name):
    _require('scientific_verdict' in value and value['scientific_verdict'] is None,
             name + ' must explicitly preserve scientific_verdict null')


def _contained(path, root):
    resolved = path.resolve(strict=True)
    try:
        resolved.relative_to(root.resolve(strict=True))
    except ValueError as error:
        raise ValueError('Surface path escapes its owning directory: ' + str(path)) from error
    return resolved


def _raw_record(extraction, record):
    _require(isinstance(record, dict), 'Missing raw surface record')
    relative = record.get('path')
    _require(isinstance(relative, str) and relative and not Path(relative).is_absolute()
             and '..' not in Path(relative).parts, 'Raw surface path must be a contained relative path')
    _require(isinstance(record.get('sha256'), str)
             and re.fullmatch('[0-9a-f]{64}', record['sha256']) is not None,
             'Invalid raw surface SHA256 metadata')
    _require(type(record.get('bytes')) is int and record['bytes'] > 0, 'Invalid raw surface byte count')
    path = _contained(extraction / relative, extraction)
    _require(path.is_file(), 'Raw surface payload is not a file')
    return record


def resolve_surface(task: Path, *, region, mode, prior, training_relative, ply_sha,
                    config_sha, source_sha, input_manifest_sha, expected_extraction,
                    runtime_image_id):
    """Return (extraction_dir, raw_record, origin), or None if still pending.

    Origins are ``canonical_finalization`` and ``matched_comparison``. Canonical
    extraction receipts have precedence over completed matched-comparison runs.
    Same-tier duplicate raw hashes are accepted deterministically; conflicting
    hashes or invalid provenance for the requested run raise ValueError.
    """
    task = Path(task).resolve(strict=True)
    _require(region in ('P1', 'P2', 'P3') and mode in ('mvs', 'mvs_pgsr')
             and type(prior) in (int, float) and prior in CONDITIONS, 'Unsupported surface condition')
    _require(isinstance(training_relative, str) and training_relative
             and not Path(training_relative).is_absolute() and '..' not in Path(training_relative).parts,
             'Training path must be a contained relative path')
    _require(isinstance(expected_extraction, dict)
             and all(key in expected_extraction for key in EXTRACTION_KEYS),
             'Expected extraction parameters are incomplete')
    identifier = f'{region}.{mode}.{CONDITIONS[prior]}'
    expected_job = {'id': identifier, 'region': region, 'mode': mode, 'prior': prior,
                    'training_relative': training_relative, 'config_sha256': config_sha,
                    'source_provenance_sha256': source_sha, 'input_manifest_sha256': input_manifest_sha}
    expected_ply_path = training_relative + '/model/point_cloud/iteration_30000/point_cloud.ply'
    for owner, origin in (('evaluation', 'canonical_finalization'),
                          ('matched_comparison_v1', 'matched_comparison')):
        matches = []
        for path in sorted((task / owner).glob(f'attempt.*/extractions/{identifier}/receipt.json')):
            path = _contained(path, task)
            receipt = _read(path)
            if receipt.get('status') != 'PASS':
                continue
            job = receipt.get('job')
            _require(isinstance(job, dict), 'PASS extraction receipt is missing its job')
            if job.get('training_relative') != training_relative:
                continue
            extraction = path.parent
            if origin == 'matched_comparison':
                attempt = extraction.parent.parent
                completion_path = attempt / 'receipt.json'
                if not completion_path.is_file():
                    continue
                completion = _read(_contained(completion_path, task))
                if completion.get('status') != 'PASS_MATCHED_COMPARISON':
                    continue
                _null(completion, 'Matched completion receipt')
                plan = _read(_contained(attempt / 'plan.json', task))
                _null(plan, 'Matched plan')
                runs = plan.get('runs')
                _require(isinstance(runs, list), 'Matched plan is missing runs')
                bound = [row for row in runs if isinstance(row, dict) and row.get('id') == identifier]
                _require(len(bound) == 1 and bound[0] == job, 'Matched plan does not bind the exact extraction job')
            _null(receipt, 'Extraction receipt')
            _null(job, 'Extraction job')
            for key, expected in expected_job.items():
                _require(key in job and job[key] == expected, 'Extraction job mismatch: ' + key)
            _require(receipt.get('runtime_image_id') == runtime_image_id, 'Extraction runtime image mismatch')
            _require(receipt.get('exit_code') == 0, 'PASS extraction has a nonzero or missing exit code')
            files = job.get('files')
            _require(isinstance(files, list), 'Extraction job is missing training file bindings')
            ply_records = [row for row in files if isinstance(row, dict) and row.get('path') == expected_ply_path]
            _require(len(ply_records) == 1 and ply_records[0].get('sha256') == ply_sha,
                     'Extracted surface does not bind the exact displayed final PLY')
            realized = receipt.get('realized_extraction')
            _require(isinstance(realized, dict), 'Missing realized extraction parameters')
            for key in EXTRACTION_KEYS:
                _require(key in realized and realized[key] == expected_extraction[key],
                         'Realized extraction parameter mismatch: ' + key)
            surfaces = receipt.get('surfaces')
            _require(isinstance(surfaces, dict), 'Missing extraction surface records')
            record = _raw_record(extraction, surfaces.get('raw'))
            matches.append((extraction, record, origin))
        if matches:
            _require(len({row[1]['sha256'] for row in matches}) == 1,
                     'Ambiguous completed raw surfaces: different SHA256 in ' + origin)
            _require(len({row[1]['bytes'] for row in matches}) == 1,
                     'Duplicate raw SHA256 has inconsistent byte counts in ' + origin)
            return matches[0]
    return None
