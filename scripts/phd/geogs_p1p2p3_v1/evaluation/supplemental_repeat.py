"""Explicit supplemental native repetition; never an extra primary condition."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

from runtime_layout import relative_path, sha

COMPLETION_SHA = '3e200db7de4cc171158b08deccffd3869bfd2d30c2a5b89805b86ad1903112c6'
COMPLETION_SCOPE = 'PRIMARY18_SUPPLEMENTAL_INCOMPLETE'


class SupplementalRepeat:
    def __init__(self, task, path, layout):
        self.task, self.layout = Path(task), layout
        self.path, self.digest, self.data = None, None, None
        self.completion = None
        if path is None:
            if ((self.task/'contracts/supplemental_repeat_v1.json').exists() or
                    (self.task/'contracts/evaluation_completion_v2.json').exists()):
                raise ValueError('This task requires its preregistered explicit --repeat-contract before evaluation')
            return
        self.path = Path(path)
        if not self.path.is_absolute():
            self.path = self.task/self.path
        relative_path(str(self.path.relative_to(self.task)))
        self.digest = sha(self.path)
        self.data = json.loads(self.path.read_text())
        expected = dict(schema='GEOGS_SUPPLEMENTAL_NATIVE_REPEAT_v1', condition_id='D005_Pnative',
                        start_iteration=8000, iterations=30000, scientific_verdict=None)
        if any(self.data.get(key) != value for key, value in expected.items()):
            raise ValueError('Unknown supplemental repetition scientific identity')
        if self.data.get('runtime_layout_sha256') != layout.digest or layout.path is None:
            raise ValueError('Supplemental repetition requires its exact explicit runtime layout')
        if self.data.get('scientific_config_sha256') != sha(self.task/'contracts/execution_v1.json'):
            raise ValueError('Supplemental repetition scientific configuration changed')
        if set(self.data['regions']) != set(layout.regions) or len(self.data['regions']) != len(layout.regions):
            raise ValueError('One supplemental repetition is required for every region')
        if self.data['phases'] != ['train', 'render', 'metrics', 'auxiliary']:
            raise ValueError('Supplemental repetition must complete all fixed phases')
        if self.data['allocator'] != layout.data['allocator']:
            raise ValueError('Supplemental repetition must retain the declared allocator')
        relative_path(self.data['output_directory'])
        identifier = self.data['repeat_id']
        if not identifier or Path(identifier).name != identifier or identifier in ('.', '..', 'D005_Pnative'):
            raise ValueError('A separate supplemental candidate identity is required')
        cfg = json.loads((self.task/'contracts/execution_v1.json').read_text())
        if self.data['seed'] != cfg['seed'] or identifier in {row['id'] for row in cfg['conditions']}:
            raise ValueError('Repetition may not change seed or replace a primary condition')
        native = next(row for row in cfg['conditions'] if row['id'] == 'D005_Pnative')
        if any(self.data[field] != native[field] for field in ('lambda_lod_anchor', 'protection')):
            raise ValueError('Repetition may not change the native scientific controls')
        if set(self.data['anchors']) != set(layout.regions):
            raise ValueError('Repetition must retain all exact regional anchor paths')
        for region in layout.regions:
            expected = layout.anchor_checkpoint(region)
            if self.task/relative_path(self.data['anchors'][region]['checkpoint_directory']) != expected:
                raise ValueError('Repetition cannot substitute another anchor path')
        self._load_completion()

    def _load_completion(self):
        path = self.task/'contracts/evaluation_completion_v2.json'
        if not path.exists():
            return
        digest = sha(path)
        if digest != COMPLETION_SHA:
            raise ValueError('Unknown evaluation completion amendment SHA')
        data = json.loads(path.read_text())
        expected = dict(schema='GEOGS_EVALUATION_COMPLETION_AMENDMENT_v2',
                        evaluation_scope=COMPLETION_SCOPE, primary_runs_required=18,
                        primary_phases_required=72, evaluable_repeat_regions=[], scientific_verdict=None,
                        runtime_layout_sha256=self.layout.digest,
                        supplemental_repeat_contract_sha256=self.digest)
        if any(data.get(key) != value for key, value in expected.items()):
            raise ValueError('Completion amendment changes the fixed execution scope')
        for field, filename in [('scientific_config_sha256', 'execution_v1.json'),
                                ('resource_contract_sha256', 'extraction_resource_v3.json'),
                                ('analysis_config_sha256', 'evaluation_analysis_v1.json')]:
            if data.get(field) != sha(self.task/'contracts'/filename):
                raise ValueError('Completion amendment requires unchanged ' + filename)
        availability = data['supplemental_availability']
        if ([row['region'] for row in availability] != list(self.layout.regions) or
                any(row['repeat_id'] != self.identifier or row['condition'] != 'D005_Pnative' or
                    row['run_directory'] != str(self.run(row['region']).relative_to(self.task)) or
                    row['completed'] is not False or row['quality_metrics'] is not None or
                    row['scientific_verdict'] is not None for row in availability)):
            raise ValueError('Completion amendment supplemental availability differs')
        expected_paths = {str(self.run(region).relative_to(self.task)/name)
                          for region in ('P1', 'P2')
                          for name in ('train_receipt.json', 'train_invocation.json', 'train.log', 'train_gpu.csv')}
        paths = [str(relative_path(row['path'])) for row in data['failure_evidence']]
        if len(paths) != 8 or set(paths) != expected_paths:
            raise ValueError('Completion amendment requires the exact eight failure evidence files')
        self.completion = SimpleNamespace(path=path, digest=digest, data=data)

    @property
    def evaluable_regions(self):
        if self.completion:
            return list(self.completion.data['evaluable_repeat_regions'])
        return list(self.layout.regions) if self.data else []

    def evaluation_enabled(self, region):
        if region not in self.layout.regions:
            raise ValueError('Unknown supplemental repetition region')
        return region in self.evaluable_regions

    @property
    def supplemental_availability(self):
        return copy.deepcopy(self.completion.data['supplemental_availability']) if self.completion else None

    @property
    def identifier(self):
        return self.data['repeat_id'] if self.data else None

    def binding(self):
        result = dict(repeat_contract_sha256=self.digest, supplemental_repeat_id=self.identifier)
        if self.completion:
            result.update(completion_contract_sha256=self.completion.digest,
                          evaluation_scope=self.completion.data['evaluation_scope'])
        return result

    def require_receipt(self, receipt):
        if receipt.get('repeat_contract_sha256') != self.digest:
            raise ValueError('Repeat contract SHA differs; supply the exact explicit --repeat-contract')
        if self.completion:
            if any(receipt.get(key) != self.binding()[key]
                   for key in ('completion_contract_sha256', 'evaluation_scope')):
                raise ValueError('Evaluation completion amendment binding differs')
        elif receipt.get('completion_contract_sha256') is not None or receipt.get('evaluation_scope') is not None:
            raise ValueError('Completion-amended results require the fixed completion contract')

    def run(self, region):
        if self.data is None or region not in self.layout.regions:
            raise ValueError('No declared regional supplemental repetition')
        return self.task/relative_path(self.data['output_directory'])/region/'D005_Pnative'

    def require_run_receipt(self, receipt, region):
        # Native producers precede the prospective evaluation amendment. Their
        # original receipts must not be rewritten to carry evaluation metadata.
        if receipt.get('repeat_contract_sha256') != self.digest:
            raise ValueError('Repeat contract SHA differs; supply the exact explicit --repeat-contract')
        self.layout.require_receipt(receipt)
        if (receipt.get('repeat_id') != self.identifier or receipt.get('supplemental_only') is not True or
                receipt.get('region') != region or receipt.get('condition') != 'D005_Pnative'):
            raise ValueError('Supplemental run is not the declared same-condition repetition')
        if receipt.get('phase') == 'train' and receipt.get('training_start_iteration') != 8000:
            raise ValueError('Supplemental repetition must restore exact iteration8000')
        if receipt.get('phase') in self.data['phases'] and receipt.get('runtime_image_id') != self.data['runtime_image_id']:
            raise ValueError('Supplemental repetition runtime image changed')

    def require_candidates(self, seal):
        self.require_receipt(seal)
        repeated = [row for row in seal['candidates'] if row.get('supplemental_only') is True]
        if self.completion:
            if seal.get('supplemental_availability') != self.supplemental_availability:
                raise ValueError('Sealed supplemental availability differs from completion contract')
            if repeated or any(row.get('condition') == self.identifier for row in seal['candidates']):
                raise ValueError('Deferred supplemental repetitions cannot enter primary evaluation')
            evidence = seal.get('completion_decision_evidence', [])
            expected = self.completion.data['failure_evidence']
            if ([{key: row.get(key) for key in ('path', 'sha256')} for row in evidence] != expected or
                    any(not isinstance(row.get('bytes'), int) or row['bytes'] <= 0 for row in evidence)):
                raise ValueError('Sealed completion failure evidence differs from fixed contract')
            frozen = {row['path']: row for row in seal.get('files', [])}
            if len(frozen) != len(seal.get('files', [])) or any(frozen.get(row['path']) != row for row in evidence):
                raise ValueError('Completion evidence is absent or duplicated in seal inventory')
            contract = frozen.get(str(self.completion.path.relative_to(self.task)), {})
            if contract.get('sha256') != self.completion.digest or contract.get('bytes') != self.completion.path.stat().st_size:
                raise ValueError('Completion contract is absent from seal inventory')
            return
        if self.data is None:
            if repeated:
                raise ValueError('Supplemental candidates require an explicit repeat contract')
            return
        if any(row['region'] not in self.layout.regions for row in repeated):
            raise ValueError('Unknown supplemental repetition region')
        for region in self.layout.regions:
            rows = [row for row in repeated if row['region'] == region]
            final = [row for row in rows if row['variant']=='final' and row['mesh_kind']=='raw']
            if len(final) != 1 or any(row['condition'] != self.identifier for row in rows):
                raise ValueError('Every declared native repetition must be sealed before evaluation')
            if any(row.get('run_directory') != str(self.run(region).relative_to(self.task)) for row in rows):
                raise ValueError('Repeated candidate path differs from its fixed supplemental output')
            expected_hash = self.data['anchors'][region].get('checkpoint_sha256')
            if expected_hash and any(row['anchor_provenance']['checkpoint']['sha256'] != expected_hash for row in rows):
                raise ValueError('Repeated candidate restored a different frozen checkpoint')
