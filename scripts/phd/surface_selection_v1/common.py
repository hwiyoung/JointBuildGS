"""Provenance verification shared by method, evaluation, and read-only viewer."""
import json
from pathlib import Path
from scripts.phd.source_candidate_v1.common import sha,write,clean,describe

REQUIRED=('components.json','graphs.json','membership.npz','units.json','unit_graph.json',
          'input_summary.json','rgb_ledger.json','observations.json','decisions.json','summary.json')

def verify_seal(run):
    run=Path(run);seal=json.loads((run/'method_seal.json').read_text())
    if seal.get('status')!='METHOD_FROZEN_BEFORE_REFERENCE_ACCESS' or seal.get('reference_accessed') is not False:
        raise ValueError('Reference-free method seal required')
    config=json.loads((run/'config.json').read_text())
    if seal['config_sha256']!=sha(run/'config.json'):raise ValueError('Configuration changed')
    required={f'{region}/{name}' for region in config['regions'] for name in REQUIRED}
    if not required<=set(seal['files']):raise ValueError('Incomplete all-region method seal')
    for rel,digest in seal['files'].items():
        path=Path(rel)
        if path.is_absolute() or '..' in path.parts or sha(run/path)!=digest:raise ValueError('Method bytes changed: '+rel)
    return config,seal,sha(run/'method_seal.json')
