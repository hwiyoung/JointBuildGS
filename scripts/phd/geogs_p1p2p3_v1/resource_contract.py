"""Explicit extraction resource amendment, independent of training controls."""
import hashlib
import json
from pathlib import Path

RESOURCE_SHA = '804f371b9db70b089daccdba2052df8c71b54b5d20acba2ea2f5c6d3d7eb7efa'


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            value.update(block)
    return value.hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


class ResourceContract:
    def __init__(self, task, path, layout, repeat):
        self.task, self.layout, self.repeat = Path(task), layout, repeat
        self.path, self.digest, self.data = None, None, None
        if path is None:
            require(not (self.task/'contracts/extraction_resource_v3.json').exists(),
                    'This task requires its explicit --resource-contract')
            return
        self.path = Path(path)
        if not self.path.is_absolute():
            self.path = self.task/self.path
        relative = self.path.relative_to(self.task)
        require('..' not in relative.parts, 'Resource contract must reside inside task')
        self.digest, self.data = sha(self.path), json.loads(self.path.read_text())
        require(self.digest == RESOURCE_SHA, 'Unknown or modified extraction resource amendment')
        expected = dict(schema='GEOGS_EXTRACTION_RESOURCE_AMENDMENT_v1', revision='resource_v3',
                        scientific_verdict=None, scientific_config_sha256=sha(self.task/'contracts/execution_v1.json'),
                        runtime_layout_sha256=layout.digest, supplemental_repeat_contract_sha256=repeat.digest,
                        training_controls_changed=False, primary_final_mesh_res=1024,
                        output_directory='extraction_resource_v3')
        require(all(self.data.get(k) == v for k,v in expected.items()), 'Resource amendment identity differs')

    def binding(self):
        return dict(resource_contract_sha256=self.digest,
                    resource_revision=self.data['revision'] if self.data else None,
                    resource_contract_path=str(self.path.relative_to(self.task)) if self.path else None)

    def require_receipt(self, receipt):
        require(receipt.get('resource_contract_sha256') == self.digest, 'Resource contract SHA differs')

    def family(self, repeat_id):
        require(repeat_id in (None, 'native_repeat_1'), 'Unknown resource run family')
        return repeat_id or 'primary'

    def aux_run(self, region, condition, repeat_id=None):
        require(region in self.layout.regions and Path(condition).name == condition and condition not in ('.','..'),
                'Invalid regional resource output path')
        if self.data is None:
            return self.repeat.run(region) if repeat_id else self.layout.run(region, condition)
        require(not repeat_id or condition == 'D005_Pnative', 'Supplemental resource producer must be native')
        return self.task/self.data['output_directory']/self.family(repeat_id)/region/condition

    def variant_inventory(self, region, condition, repeat_id=None):
        if self.data is None:
            return []
        self.aux_run(region, condition, repeat_id)
        result = []
        if condition == 'D005_Pnative' and repeat_id is None:
            result += [dict(name='anchor_512', iteration=8000, mesh_res=512, required=True,
                            export_images=True, source_kind='common_anchor'),
                       dict(name='anchor', iteration=8000, mesh_res=1024, required=False,
                            export_images=True, source_kind='common_anchor')]
        result += [dict(name='mesh_512', iteration=30000, mesh_res=512, required=True,
                        export_images=False, source_kind='final_complete'),
                   dict(name='mesh_2048', iteration=30000, mesh_res=2048, required=False,
                        export_images=False, source_kind='final_complete')]
        return result

    def validate_variant(self, receipt, planned, directory):
        self.require_receipt(receipt)
        for key in ('iteration', 'mesh_res', 'required', 'export_images', 'source_kind'):
            require(receipt.get(key) == planned[key], 'Resource variant plan differs: '+planned['name'])
        require(receipt.get('variant') == planned['name'] and receipt.get('scientific_verdict') is None,
                'Resource variant identity differs')
        for field in ('memory_trace', 'source_log'):
            item = receipt[field]
            path = Path(item['path'])
            require(not path.is_absolute() and '..' not in path.parts, 'Variant evidence must be relative')
            require(sha(directory/path) == item['sha256'], 'Variant evidence hash differs: '+field)
        if receipt.get('status') == 'PASS':
            require(receipt.get('native_exit_code') == 0 and receipt.get('validated_exit_code') == 0,
                    'PASS variant must complete official rendering')
            for name in ('fuse.ply','fuse_post.ply'):
                relative = f'model/train/ours_{planned["iteration"]}/{name}'
                files = [row for row in receipt['files'] if row['path'] == relative]
                require(len(files) == 1 and files[0].get('exists') is True, 'Atomic raw/post output missing')
                path = directory/relative
                require(sha(path) == files[0]['sha256'] and path.stat().st_size == files[0]['bytes'],
                        'Variant output differs from producer')
                valid = [row for row in receipt['validation'] if row.get('path') == relative]
                require(len(valid) == 1 and valid[0].get('valid_triangle_surface') is True,
                        'PASS requires valid raw and post triangle surfaces')
            return
        require(not planned['required'] and receipt.get('status') == 'TECHNICAL_RESOURCE_UNAVAILABLE',
                'Required or unrecognized variant failure blocks completion')
        before, after = receipt['memory_before'], receipt['memory_after']
        delta = after['memory_events'].get('oom_kill',0)-before['memory_events'].get('oom_kill',0)
        trace = [json.loads(line) for line in (directory/receipt['memory_trace']['path']).read_text().splitlines()]
        require(receipt.get('native_exit_code') == -9 and delta >= 1 and receipt.get('cgroup_oom_kill_delta') == delta,
                'Optional technical unavailability requires native SIGKILL and matching cgroup OOM kill')
        require(trace and trace[0] == before and trace[-1] == after
                and receipt.get('cgroup_memory_limit_bytes') == self.data['resource_policy']['memory_limit_bytes']
                and str(before['memory_max']) == str(self.data['resource_policy']['memory_limit_bytes'])
                and str(after['memory_max']) == str(before['memory_max']),
                'Optional OOM proof does not match this variant memory trace/cap')

    def validate_receipt(self, receipt, region, condition, repeat_id=None):
        self.require_receipt(receipt)
        expected = dict(status='PASS', phase='auxiliary', region=region, condition=condition,
                        scientific_verdict=None, config_sha256=self.data['scientific_config_sha256'],
                        runtime_layout_sha256=self.layout.digest, run_family=self.family(repeat_id))
        require(all(receipt.get(k) == v for k,v in expected.items()), 'Resource auxiliary aggregate incomplete or differently bound')
        if repeat_id:
            self.repeat.require_run_receipt(receipt, region)
        else:
            require(not receipt.get('repeat_id'), 'Primary resource output cannot substitute a repeat')
        inventory = self.variant_inventory(region, condition, repeat_id)
        rows = receipt.get('variants', [])
        require(len(rows) == len(inventory) and {r['name'] for r in rows} == {r['name'] for r in inventory},
                'Every required and optional variant must be accounted for exactly once')
        root = self.aux_run(region, condition, repeat_id)
        for planned in inventory:
            row = next(row for row in rows if row['name'] == planned['name'])
            relative = f'auxiliary/{planned["name"]}/receipt.json'
            require(row.get('receipt_path') == relative and sha(root/relative) == row['receipt_sha256'],
                    'Resource variant receipt binding differs')
            value = json.loads((root/relative).read_text())
            require(row.get('status') == value.get('status'), 'Aggregate and variant statuses differ')
            self.validate_variant(value, planned, root/'auxiliary'/planned['name'])
