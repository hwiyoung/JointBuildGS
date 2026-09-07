"""Explicit operational path revisions, separate from scientific configuration."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def relative_path(value):
    if not isinstance(value, str) or not value:
        raise ValueError('Nonempty task-relative runtime path required')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or str(path) != value or value == '.':
        raise ValueError('Runtime layout may not escape its task or use ambiguous paths')
    return Path(value)


class RuntimeLayout:
    def __init__(self, task, path=None, regions=('P1', 'P2', 'P3')):
        self.task, self.regions = Path(task), tuple(regions)
        self.path, self.digest = None, None
        if path is None:
            self.data = dict(revision='legacy_default_v1', runs_directory='runs', parity_directory='parity',
                             queue_directory='queue', allocator=None, anchors={})
            for region in self.regions:
                baseline = f'runs/{region}/D005_Pnative'
                self.data['anchors'][region] = dict(baseline_directory=baseline,
                    checkpoint_directory=baseline+'/model/jbgs_complete/iteration_8000')
        else:
            self.path = Path(path)
            if not self.path.is_absolute():
                self.path = self.task/self.path
            try:
                self.path.relative_to(self.task)
            except ValueError as error:
                raise ValueError('Runtime layout contract must reside within the task') from error
            self.digest = sha(self.path)
            self.data = json.loads(self.path.read_text())
            if self.data.get('schema') != 'geogs_runtime_layout_v1' or not self.data.get('revision'):
                raise ValueError('Unknown runtime layout contract')
            if self.data.get('scientific_verdict') is not None:
                raise ValueError('Runtime layout cannot contain a scientific verdict')
        for field in ('runs_directory', 'parity_directory', 'queue_directory'):
            relative_path(self.data[field])
        if set(self.data['anchors']) != set(self.regions):
            raise ValueError('Runtime layout must identify each frozen region anchor exactly once')
        for region, anchor in self.data['anchors'].items():
            baseline = relative_path(anchor['baseline_directory'])
            checkpoint = relative_path(anchor['checkpoint_directory'])
            if baseline.parts[-2:] != (region, 'D005_Pnative'):
                raise ValueError('Anchor must come from the matching regional native condition')
            if checkpoint != baseline/'model/jbgs_complete/iteration_8000':
                raise ValueError('Anchor must name the exact completed iteration8000 directory')
            declared = anchor.get('native_final_starts_from_anchor')
            if declared is not None and declared != self.starts_from_anchor(region, 'D005_Pnative'):
                raise ValueError('Declared native restart mode differs from anchor/run paths')

    def binding(self):
        return dict(runtime_layout_sha256=self.digest, runtime_layout_revision=self.data['revision'],
                    runtime_layout_path=str(self.path.relative_to(self.task)) if self.path else None,
                    runs_directory=self.data['runs_directory'])

    def require_receipt(self, receipt):
        if receipt.get('runtime_layout_sha256') != self.digest:
            raise ValueError('Runtime layout SHA differs; supply the exact explicit --runtime-layout contract')

    def require_scientific_config(self, path):
        if self.path and self.data.get('scientific_config_sha256') != sha(path):
            raise ValueError('Runtime layout must bind the unchanged scientific configuration')

    def run(self, region, condition):
        if region not in self.regions or Path(condition).name != condition or condition in ('.', '..'):
            raise ValueError('Unknown region or invalid condition path')
        return self.task/relative_path(self.data['runs_directory'])/region/condition

    def anchor_baseline(self, region):
        return self.task/relative_path(self.data['anchors'][region]['baseline_directory'])

    def anchor_checkpoint(self, region):
        return self.task/relative_path(self.data['anchors'][region]['checkpoint_directory'])

    def starts_from_anchor(self, region, condition):
        return condition != 'D005_Pnative' or self.run(region, condition) != self.anchor_baseline(region)
