"""Docker-only completion gates for the fixed primary and supplemental scope."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).parent/'evaluation_code'))
from repeat_contract import validate_primary_readiness
from runtime_layout import RuntimeLayout, sha
from supplemental_repeat import SupplementalRepeat
from seal_candidates import validate_phase_receipt
from resource_contract import ResourceContract
import resource_support as resources

IMAGE = 'sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
CONFIG_SHA = 'b08bbcc808da060322fc1ed05902edbb08db2a0784dd146f4644adc12228eab4'
LAYOUT_SHA = '28b83d4a462d764cbe0d59b32f7a816db92236141879806a5a1bc8ce4e450cd5'
REPEAT_SHA = '3c62494f13de96dba33b1c36cbadf58e555305fee01ce641dd41f560bdfacafc'
STAGES = ('seal', 'geometry:P1', 'renders:P1', 'geometry:P2', 'renders:P2',
          'geometry:P3', 'renders:P3', 'summary', 'cases')


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def record(task, path):
    path = Path(path)
    require(path.is_file() and path.stat().st_size > 0, 'Missing nonempty output: ' + str(path))
    return dict(path=str(path.relative_to(task)), sha256=sha(path), bytes=path.stat().st_size)


def checked(task, item):
    relative = Path(item['path'])
    require(not relative.is_absolute() and '..' not in relative.parts, 'Invalid task-relative artifact')
    current = record(task, task/relative)
    require(current['sha256'] == item['sha256'] and current['bytes'] == item.get('bytes', current['bytes']),
            'Recorded artifact changed: ' + item['path'])
    return current


class FinalizationGate:
    def __init__(self, task):
        self.task = Path(task)
        self.config_path = self.task/'contracts/execution_v1.json'
        self.cfg = read(self.config_path)
        self.layout = RuntimeLayout(self.task, self.task/'contracts/runtime_layout_allocator_v2.json', self.cfg['regions'])
        self.repeat = SupplementalRepeat(self.task, self.task/'contracts/supplemental_repeat_v1.json', self.layout)
        require(sha(self.config_path) == CONFIG_SHA and self.layout.digest == LAYOUT_SHA and self.repeat.digest == REPEAT_SHA,
                'This finalizer permits only the unchanged preregistered allocator-v2 experiment')
        self.layout.require_scientific_config(self.config_path)
        resource_path = self.task/'contracts/extraction_resource_v3.json'
        self.resource = ResourceContract(self.task, resource_path if resource_path.exists() else None, self.layout, self.repeat)

    def condition_ids(self, region):
        conditions = [row['id'] for row in self.cfg['conditions']]
        # Legacy admission fixtures expose only identifier; real tasks always
        # use SupplementalRepeat's explicit regional evaluation policy.
        enabled = getattr(self.repeat, 'evaluation_enabled', lambda name: bool(self.repeat.identifier))
        if enabled(region):
            conditions.append(self.repeat.identifier)
        return conditions

    def readiness(self):
        if not self.resource.data:
            validate_primary_readiness(self.task/'runs_allocator_v2', self.cfg, CONFIG_SHA, LAYOUT_SHA)
        files = [record(self.task, self.task/'contracts'/name) for name in
                 ('execution_v1.json', 'runtime_layout_allocator_v2.json', 'supplemental_repeat_v1.json',
                  'evaluation_analysis_v1.json', 'evaluation_sources_v1.json')]
        if self.resource.path:
            files.append(record(self.task,self.resource.path))
        if self.repeat.completion:
            files.append(record(self.task, self.repeat.completion.path))
        count = 0
        for region in self.cfg['regions']:
            input_sha = sha(self.task/'inputs'/region/'input_manifest.json')
            runs = [(row['id'], self.layout.run(region, row['id']), None) for row in self.cfg['conditions']]
            if self.repeat.evaluation_enabled(region):
                runs.append(('D005_Pnative', self.repeat.run(region), self.repeat))
            for condition, run, repeat in runs:
                for phase in ('train', 'render', 'metrics', 'auxiliary'):
                    phase_root = self.resource.aux_run(region,condition,repeat.identifier if repeat else None) if phase=='auxiliary' and self.resource.data else run
                    path = phase_root/(phase+'_receipt.json')
                    receipt = read(path)
                    validate_phase_receipt(receipt, region, condition, phase, CONFIG_SHA, input_sha, self.layout, repeat)
                    if phase == 'auxiliary' and self.resource.data:
                        self.resource.validate_receipt(receipt,region,condition,repeat.identifier if repeat else None)
                    require(receipt.get('native_exit_code') == 0 and receipt.get('validated_exit_code') == 0
                            and receipt.get('runtime_image_id') == IMAGE and receipt.get('scientific_verdict') is None,
                            'Native phase did not complete in the pinned runtime: ' + str(path))
                    files.append(record(self.task, path))
                    count += 1
        expected_count = 72 if self.repeat.completion else 84
        require(count == expected_count, 'All fixed primary and enabled supplemental phases are required')
        status = ('PRIMARY18_REQUIRED_PHASES_PASS_SUPPLEMENTAL_INCOMPLETE' if self.repeat.completion else
                  'ALL_21_REQUIRED_PHASES_PASS_OPTIONAL_ACCOUNTED' if self.resource.data else 'ALL_21_RUNS_84_PHASES_PASS')
        availability = {'supplemental_availability': self.repeat.supplemental_availability} if self.repeat.completion else {}
        return dict(status=status, phase_receipts=count, files=files, **availability,
                    config_sha256=CONFIG_SHA, **self.layout.binding(), **self.repeat.binding(), **self.resource.binding(), scientific_verdict=None)

    def bound_receipt(self, path, status, seal_sha, **identity):
        receipt = read(path)
        require(receipt.get('status') == status and receipt.get('scientific_verdict') is None,
                'Stage has no successful technical receipt: ' + str(path))
        self.layout.require_receipt(receipt)
        self.repeat.require_receipt(receipt)
        if getattr(self,'resource',None) and self.resource.data:
            self.resource.require_receipt(receipt)
        require(all(receipt.get(key) == value for key, value in identity.items()), 'Stage identity changed: ' + str(path))
        if seal_sha:
            key = 'sealed_render_manifest_sha256' if status == 'PASS_RENDER_QUALITY_EVALUATION' else 'candidate_seal_sha256'
            require(receipt.get(key) == seal_sha, 'Stage belongs to a different candidate seal: ' + str(path))
        if getattr(self, 'stage_input_verification', False) and status in ('PASS_GEOMETRY_EVALUATION', 'PASS_RENDER_QUALITY_EVALUATION'):
            proof = receipt.get('input_verification', {})
            expected_stage = 'renders' if status == 'PASS_RENDER_QUALITY_EVALUATION' else 'geometry'
            require(proof.get('policy') == 'REGIONAL_CONSUMED_INPUTS_v1'
                    and proof.get('stage') == expected_stage and proof.get('region') == receipt.get('region')
                    and proof.get('candidate_seal_sha256') == seal_sha
                    and type(proof.get('files_count')) is int and proof['files_count'] > 0
                    and type(proof.get('verified_bytes')) is int and proof['verified_bytes'] > 0,
                    'Explicit regional consumed-input verification is absent: ' + str(path))
            sealed, current_seal_sha = self.candidate_seal()
            require(current_seal_sha == seal_sha, 'Consumed-input proof belongs to another candidate seal')
            catalogue = {row['path']: row for row in sealed['files']}
            require(len(catalogue) == len(sealed['files']), 'Duplicate sealed input path')
            regional = [row for row in sealed['candidates'] if row['region'] == receipt['region']]
            if expected_stage == 'geometry':
                expected_paths = {f'inputs/{receipt["region"]}/surface/als_surface.ply'}
                expected_paths.update(row['surface']['path'] for row in regional)
            else:
                expected_paths = {f'inputs/{receipt["region"]}/scene/split_manifest_da3_v2.json'}
                for candidate in regional:
                    for view in candidate['render_records']:
                        expected_paths.add(view['render_path'])
                        expected_paths.add(f'inputs/{receipt["region"]}/scene/images/'+view['name'])
            require(regional and expected_paths <= set(catalogue), 'Consumed-input catalogue is incomplete')
            expected_records = [{key: catalogue[name][key] for key in ('path', 'bytes', 'sha256')}
                                for name in sorted(expected_paths)]
            digest = hashlib.sha256(json.dumps(expected_records, sort_keys=True, separators=(',', ':'),
                                               ensure_ascii=False).encode('utf-8')).hexdigest()
            require(proof.get('files') == expected_records and proof.get('manifest_sha256') == digest
                    and proof['files_count'] == len(expected_records)
                    and proof['verified_bytes'] == sum(row['bytes'] for row in expected_records)
                    and proof.get('scientific_verdict') is None,
                    'Consumed-input proof omits or changes the exact regional scoring inventory')
        return receipt

    def candidate_seal(self):
        path = self.task/'contracts/candidates_sealed_v1.json'
        seal = read(path)
        status = resources.seal_status(self.resource, self.repeat)
        require(seal.get('status') == status and seal.get('config_sha256') == CONFIG_SHA
                and seal.get('scientific_verdict') is None and seal.get('reference_accessed') is False,
                'Complete reference-free candidate seal is required')
        self.layout.require_receipt(seal)
        self.repeat.require_candidates(seal)
        self.resource.require_receipt(seal)
        expected = set()
        planned_inventory = {}
        for region in self.cfg['regions']:
            for condition in self.condition_ids(region):
                variants = ['final']
                if self.resource.data:
                    repeated = condition == self.repeat.identifier
                    for item in self.resource.variant_inventory(region,'D005_Pnative' if repeated else condition,self.repeat.identifier if repeated else None):
                        planned_inventory[(region,condition,item['name'])] = item
                else:
                    variants += ['mesh_'+str(res) for res in self.cfg['extraction']['sensitivity_mesh_res']]
                    if condition in ('D005_Pnative', self.repeat.identifier):
                        variants.append('anchor')
                expected.update((region, condition, variant, kind) for variant in variants for kind in ('raw', 'post'))
        if self.resource.data:
            entries = seal.get('extraction_inventory',[])
            keys = [(row['region'],row['condition'],row['variant']) for row in entries]
            require(len(keys) == len(set(keys)) and set(keys) == set(planned_inventory),'Incomplete resource variant inventory')
            for row in entries:
                key = row['region'],row['condition'],row['variant']
                planned = planned_inventory[key]
                require(all(row[field] == planned[field] for field in ('iteration','mesh_res','required','export_images')),
                        'Resource extraction inventory differs from registered plan')
                require(row['status'] in ('PASS','TECHNICAL_RESOURCE_UNAVAILABLE') and (not row['required'] or row['status']=='PASS'),
                        'Unresolved required or optional resource extraction')
                if row['status'] == 'PASS':
                    expected.update((*key,kind) for kind in ('raw','post'))
        actual = [(row['region'], row['condition'], row['variant'], row['mesh_kind']) for row in seal['candidates']]
        require(len(actual) == len(set(actual)) and set(actual) == expected, 'Candidate seal omits or duplicates a fixed variant')
        return seal, sha(path)

    def decide(self, stage):
        require(stage in STAGES, 'Unknown finalization stage')
        if stage == 'seal':
            path = self.task/'contracts/candidates_sealed_v1.json'
            if not path.exists():
                return 'RUN', []
            seal, _ = self.candidate_seal()
            # Legacy mode rechecks the full corpus. Explicit stage-input mode
            # retains the complete seal identity and verifies consumed bytes in
            # each evaluator; final preservation still rechecks every seal byte.
            if not getattr(self, 'stage_input_verification', False):
                for item in seal['files']:
                    checked(self.task, item)
            return 'SKIP', [record(self.task, path)]
        sealed, seal_sha = self.candidate_seal()
        kind, _, region = stage.partition(':')
        if kind == 'geometry':
            directory = self.task/'evaluation/geometry'/region
            if not directory.exists():
                require(not (self.task/'evaluation/viewer'/region).exists(), 'Partial geometry viewer output exists')
                return 'RUN', []
            path = directory/'receipt.json'
            self.bound_receipt(path, 'PASS_GEOMETRY_EVALUATION', seal_sha, region=region)
            files = [record(self.task, directory/name) for name in ('receipt.json', 'geometry_metrics.csv', 'viewer_index.json')]
            return 'SKIP', files
        if kind == 'renders':
            directory = self.task/'evaluation/renders'/region
            if not directory.exists():
                return 'RUN', []
            files = []
            conditions = self.condition_ids(region)
            for condition in conditions:
                if getattr(self,'resource',None) and self.resource.data:
                    stages = [row['variant'] for row in sealed['candidates'] if row['region']==region and
                              row['condition']==condition and row.get('render_records')]
                    require(len(stages) == len(set(stages)) and 'final' in stages,'Invalid declared render evaluation inventory')
                else:
                    stages = ['final']+(['anchor'] if condition in ('D005_Pnative', self.repeat.identifier) else [])
                for variant in stages:
                    path = directory/condition/variant/'receipt.json'
                    value = self.bound_receipt(path, 'PASS_RENDER_QUALITY_EVALUATION', seal_sha,
                                               region=region, condition=condition, stage=variant)
                    require(value['expected_evaluation_views'] == self.cfg['regions'][region]['expected_test'],
                            'Render evaluation view count differs')
                    files.append(record(self.task, path))
            return 'SKIP', files
        if kind == 'summary':
            for region in self.cfg['regions']:
                for parent in ('geometry:'+region, 'renders:'+region):
                    require(self.decide(parent)[0] == 'SKIP', 'Summary prerequisites are incomplete')
            directory = self.task/'evaluation/summary'
            if not directory.exists():
                require(not (self.task/'evaluation/viewer/manifest.json').exists(), 'Partial summary viewer manifest exists')
                return 'RUN', []
            path = directory/'receipt.json'
            value = self.bound_receipt(path, 'TABLES_AND_ACTUAL_VIEWER_DATA_READY', seal_sha,
                                       config_sha256=CONFIG_SHA,
                                       analysis_config_sha256=sha(self.task/'contracts/evaluation_analysis_v1.json'))
            for item in value['summary_files']:
                checked(self.task, item)
            return 'SKIP', [record(self.task, path)]
        require(self.decide('summary')[0] == 'SKIP', 'Case figures require complete summary')
        directory = self.task/'evaluation/cases_v1'
        if not directory.exists():
            require(not (self.task/'evaluation/viewer/manifest_v2.json').exists(), 'Partial case viewer manifest exists')
            return 'RUN', []
        require(not (directory/'failure_receipt.json').exists(), 'Preserved case failure requires separate recovery')
        path = directory/'index.json'
        value = self.bound_receipt(path, 'ACTUAL_CASE_FIGURES_READY', seal_sha,
                                   summary_receipt_sha256=sha(self.task/'evaluation/summary/receipt.json'))
        require(value.get('viewer_manifest_v2') == 'evaluation/viewer/manifest_v2.json', 'Case viewer v2 absent')
        for case in value['cases']:
            metadata_path = directory/case['metadata_url']
            require(sha(metadata_path) == case['metadata_sha256'], 'Case metadata changed')
            for item in read(metadata_path)['files']:
                checked(self.task, dict(item, path=str((metadata_path.parent/item['path']).relative_to(self.task))))
        viewer = self.task/value['viewer_manifest_v2']
        require(read(viewer).get('previous_manifest_sha256') == sha(self.task/'evaluation/viewer/manifest.json'),
                'Case viewer lineage differs')
        return 'SKIP', [record(self.task, path), record(self.task, viewer)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('ready', 'decision', 'finish'), required=True)
    parser.add_argument('--stage', choices=STAGES)
    parser.add_argument('--task', type=Path, default=Path('/task'))
    parser.add_argument('--attempt', type=Path, default=Path('/control'))
    parser.add_argument('--stage-input-verification', action='store_true')
    args = parser.parse_args()
    require(Path('/.dockerenv').exists() and not Path('/reference').exists()
            and not Path('/artifacts/JointBuildGS').exists(), 'Control validation requires Docker without raw reference')
    gate = FinalizationGate(args.task)
    if args.stage_input_verification:
        require(gate.repeat.completion is not None,
                'Stage-input verification requires the exact explicit primary18 completion amendment')
    gate.stage_input_verification = args.stage_input_verification
    verification_policy = 'REGIONAL_CONSUMED_INPUTS_v1' if args.stage_input_verification else 'FULL_SEALED_CORPUS_PER_STAGE'
    if args.mode == 'ready':
        value = gate.readiness()
        value.update(checked_unix=time.time(), helper_sha256=sha(__file__), input_verification_policy=verification_policy)
        with (args.attempt/'ready.json').open('x') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
        print(value['status'])
        return
    readiness = read(args.attempt/'ready.json')
    require(readiness.get('input_verification_policy', 'FULL_SEALED_CORPUS_PER_STAGE') == verification_policy,
            'Finalization input-verification policy changed after readiness')
    for item in readiness['files']:
        checked(args.task, item)
    if args.mode == 'decision':
        require(args.stage is not None, 'A decision stage is required')
        print(gate.decide(args.stage)[0])
        return
    observed = []
    for stage in STAGES:
        action, records = gate.decide(stage)
        require(action == 'SKIP', 'Finalization stage remains incomplete: ' + stage)
        observed.append(dict(stage=stage, files=records))
    value = dict(status='QUANTITATIVE_AND_CASE_OUTPUTS_READY_BROWSER_QA_PENDING', scientific_verdict=None,
                 stages=observed, completed_unix=time.time(), helper_sha256=sha(__file__),
                 browser_qa_complete=False, human_analysis_complete=False, scientific_conclusion_generated=False,
                 input_verification_policy=verification_policy, final_full_preservation_required=True,
                 **gate.layout.binding(), **gate.repeat.binding(), **gate.resource.binding())
    with (args.attempt/'complete.json').open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
    print(value['status'])


if __name__ == '__main__':
    main()
