"""Publish additive RGB display packets; never train, extract or score geometry."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import traceback

import numpy as np

from export_geometry import export_native_mesh, export_points
from baselines import colorize_photos, recover_uas_rgb, colmap_depth_points, RAW_UAS_SHA256, RAW_UAS_BYTES
from surface_selection import resolve_surface

REFERENCE_SHAS = {
    'P1': '3d111cf0cd8ab39fccb85ce0075486ec40f4f60584b5c68b2ab122918b321543',
    'P2': '9dc75111e8a5e83808d566c0b6621092423898a1f6badb9438f1a0d75e16e7ba',
    'P3': 'a72041a28c8242d3901f5696d88e607473814299baab43103fda89fc179b1f81'}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b''):
            result.update(chunk)
    return result.hexdigest()


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def atomic(path, value):
    tmp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    write(tmp, value)
    os.replace(tmp, path)


def checked(root, record):
    path = (root / record['path']).resolve(strict=True)
    path.relative_to(root.resolve())
    if path.stat().st_size != record['bytes'] or sha(path) != record['sha256']:
        raise ValueError('Frozen input identity mismatch: ' + str(path))
    return path


def qualify(value, prefix):
    if isinstance(value, dict):
        return {key: prefix + item if key == 'url' and isinstance(item, str) and not item.startswith('/')
                else qualify(item, prefix) for key, item in value.items()}
    if isinstance(value, list):
        return [qualify(item, prefix) for item in value]
    return value


class Publisher:
    def __init__(self, args):
        self.args, self.root = args, args.output
        self.cfg = read(args.config)
        self.base_cfg = read(args.base / 'contracts/execution_v1.json')
        self.seal = read(args.base / 'contracts/candidates_sealed_v1.json')
        if self.seal['config_sha256'] != sha(args.base / 'contracts/execution_v1.json'):
            raise ValueError('Original control seal/config mismatch')
        self.baselines = read(args.base / 'contracts/evaluation_sources_v1.json')
        self.experiment_sha = sha(args.new / 'inputs_v2/experiment.json')
        self.source_sha = sha(args.new / 'sources/GeoGS-mvs-pgsr-v1/mvs_pgsr_source_provenance.json')
        if args.raw_uas.stat().st_size != RAW_UAS_BYTES or sha(args.raw_uas) != RAW_UAS_SHA256:
            raise ValueError('Original RGB LiDAR bytes differ from the frozen source')
        self.code = {p.name: sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
        self.version = hashlib.sha256(json.dumps([self.cfg, self.code], sort_keys=True).encode()).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'cache').mkdir(exist_ok=True)
        (self.root / 'snapshots').mkdir(exist_ok=True)
        self.errors = []

    def cache(self, identity, factory):
        key = hashlib.sha256(json.dumps([self.version, identity], sort_keys=True).encode()).hexdigest()
        directory = self.root / 'cache' / key
        receipt = directory / 'export.json'
        if receipt.exists():
            metadata = read(receipt)
            if metadata['identity'] != identity or metadata['status'] != 'PASS_RGB_DISPLAY_EXPORT':
                raise ValueError('Display cache identity mismatch')
        else:
            if directory.exists():
                raise ValueError('Incomplete display cache preserved: ' + str(directory))
            data = factory(directory)
            metadata = {'status': 'PASS_RGB_DISPLAY_EXPORT', 'identity': identity, 'data': data,
                        'scientific_verdict': None, 'source_code': self.code}
            write(receipt, metadata)
        data = qualify(copy.deepcopy(metadata['data']), f'/data/cache/{key}/')
        if data.get('color', {}).get('kind') == 'NATIVE_VERTEX_RGB':
            data['color']['label'] = '표면에 저장된 RGB · 원래 정점색'
        elif data.get('color', {}).get('kind') == 'SH_DC_COLOR':
            data['color']['label'] = '학습된 Gaussian SH 기본색 · 중심점 표시'
        if isinstance(data.get('color', {}).get('provenance'), dict):
            data['color']['provenance'] = {'url': f'/data/cache/{key}/export.json'}
        # Verbose source IDs and color provenance stay in the downloadable packet.
        data['source'] = {'identity': identity, 'display_only': True,
                          'export': f'/data/cache/{key}/export.json'}
        data['links'] = [{'label': 'RGB·기하 출처', 'url': f'/data/cache/{key}/export.json'}]
        return data

    def mesh(self, region, record, bounds, colorizer=None):
        path = self.args.base / record['path']
        identity = {'source': 'parent', **record, 'region': region, 'kind': 'native_rgb_mesh',
                    'photo_colorized': colorizer is not None, 'bounds': bounds}
        def factory(directory):
            checked(self.args.base, record)
            return export_native_mesh(path, directory, bounds, expected_sha=record['sha256'],
                                      point_cap=self.cfg['point_cap'], colorizer=colorizer)
        return self.cache(identity, factory)

    def baseline(self, region, kind, bounds):
        if kind == 'mvs_colmap':
            path = self.args.new / 'inputs_v2' / region / 'bindings.json'
            identity = {'kind': 'colmap_supervision_rgb', 'region': region, 'binding_sha256': sha(path), 'bounds': bounds}
            def factory(directory):
                xyz, rgb, provenance = colmap_depth_points(path, path.parent, self.args.base / 'inputs' / region,
                                                           point_cap=self.cfg['point_cap'])
                return export_points(xyz, rgb, directory, bounds=bounds, point_cap=self.cfg['point_cap'],
                    source=provenance, color=provenance['color'], geometry_kind='COLMAP depth 역투영점 · 실제 감독 입력')
        elif kind == 'mvs':
            record = next(x for x in self.baselines['baselines'] if x['region'] == region)
            identity = {'kind': 'original_mvs_rgb', 'region': region, 'sha256': record['sha256'], 'bounds': bounds}
            def factory(directory):
                path = checked(self.args.base, record)
                with np.load(path, allow_pickle=False) as data:
                    return export_points(data['mvs_xyz'], data['mvs_rgb'], directory, bounds=bounds,
                        point_cap=self.cfg['point_cap'], source=record,
                        color={'kind': 'NATIVE_MVS_RGB', 'label': 'MVS 원본 RGB', 'coverage': 1.0},
                        geometry_kind='OpenMVS 융합점군 · 기존 비교 입력')
        else:
            path = self.args.reference / region / 'reference.npz'
            identity = {'kind': 'exact_uas_raw_rows_rgb', 'region': region,
                        'reference_sha256': REFERENCE_SHAS[region], 'bounds': bounds}
            def factory(directory):
                if sha(path) != REFERENCE_SHAS[region]:
                    raise ValueError('Frozen reference mismatch')
                xyz, rgb, provenance = recover_uas_rgb(path, self.args.raw_uas,
                    self.base_cfg['crs']['world_shift'], point_cap=self.cfg['point_cap'])
                provenance['builder_start_full_raw_sha256_verified'] = RAW_UAS_SHA256
                return export_points(xyz, rgb, directory, bounds=bounds, point_cap=self.cfg['point_cap'],
                    source=provenance, source_indices=np.asarray(provenance['selected_uas_raw_rows'], dtype=np.uint64),
                    color={'kind': 'NATIVE_LIDAR_RGB', 'label': '드론 LiDAR 원본 RGB', 'coverage': 1.0},
                    geometry_kind='드론 LiDAR 관측점 · GT 참조')
        return self.cache(identity, factory)

    def prior_colors(self, points, region):
        rgb, provenance = colorize_photos(points, self.args.base / 'inputs' / region,
                                          maximum_views=self.cfg['prior_color_maximum_views'])
        return rgb, {**provenance['color'], 'provenance': provenance}

    def new_candidate(self, region, mode, prior, bounds):
        identifier = f'{mode}_{prior:g}'
        value = {'id': identifier, 'label': f'{"MVS+PGSR" if mode == "mvs_pgsr" else "MVS-only"} · prior {prior:g}',
                 'group': 'mvs_geogs', 'representation_policy': 'surface_only',
                 'status': 'pending', 'stage': '30,000 step 대기',
                 'reason': '학습 또는 최종 checkpoint 검증 중입니다.'}
        completed = []
        for path in sorted((self.args.new / 'train' / region / identifier).glob('attempt.*/receipt.json')):
            try:
                receipt = read(path)
            except json.JSONDecodeError:
                continue
            expected = {'status': 'PASS', 'completed': True, 'phase': 'train', 'final_iteration': 30000,
                        'region': region, 'mode': mode, 'prior': prior, 'config_sha256': self.experiment_sha,
                        'source_provenance_sha256': self.source_sha, 'scientific_verdict': None}
            if all(receipt.get(k) == v for k, v in expected.items()):
                completed.append((path.parent, receipt))
            elif receipt.get('status') in ('FAIL', 'FAILED'):
                value.update(status='failed', reason='실행 실패가 기록되었습니다. 결과로 대체하지 않습니다.')
        if not completed:
            return value, False
        if len(completed) != 1:
            raise ValueError('Ambiguous completed training directory: ' + region + '/' + identifier)
        run, receipt = completed[0]
        producer = receipt['complete_state_receipt']
        relative = str(run.relative_to(self.args.new))
        expected_sha = producer['ply_sha256']
        condition = 'D005_Pnative' if prior == .005 else 'D0005_Pnative'
        control = next(row for row in self.seal['candidates'] if row['region'] == region
                       and row['condition'] == condition and row['iteration'] == 30000
                       and row['mesh_res'] == 512 and row['mesh_kind'] == 'raw'
                       and not row.get('supplemental_only'))
        surface = resolve_surface(self.args.new, region=region, mode=mode, prior=prior,
            training_relative=relative, ply_sha=expected_sha, config_sha=self.experiment_sha,
            source_sha=self.source_sha,
            input_manifest_sha=sha(self.args.base / 'inputs' / region / 'input_manifest.json'),
            expected_extraction=control['realized_extraction'],
            runtime_image_id=self.cfg['runtime_image_id'])
        if surface is None:
            value.update(status='pending', stage='30,000 step 완료 · 표면 추출 대기',
                         reason='학습은 완료됐습니다. 검증된 RGB 표면이 추출되면 자동으로 표시합니다.')
            return value, True
        extraction, record, origin = surface
        identity = {'kind': 'completed_native_rgb_tsdf512', 'run': relative,
                    'sha256': record['sha256'], 'bounds': bounds}
        def factory(directory):
            path = checked(extraction, record)
            return export_native_mesh(path, directory, bounds, expected_sha=record['sha256'],
                                      point_cap=self.cfg['point_cap'])
        value.update(self.cache(identity, factory), status='available',
                     stage='30,000 step · RGB TSDF512 추출 완료', extraction_origin=origin)
        value.pop('reason', None)
        return value, True

    def build(self):
        regions, completed_count, errors = [], 0, []
        for region in self.cfg['regions']:
            domain = self.base_cfg['regions'][region]['domain']
            bounds = {'min': [domain[a][0] for a in 'xyz'], 'max': [domain[a][1] for a in 'xyz']}
            candidates = []
            def add(identifier, label, group, stage, operation):
                nonlocal errors
                row = {'id': identifier, 'label': label, 'group': group, 'stage': stage}
                try:
                    row.update(operation(), status='available')
                except Exception as exc:
                    row.update(status='failed', reason=str(exc))
                    errors.append({'region': region, 'candidate': identifier, 'error': str(exc), 'trace': traceback.format_exc()})
                candidates.append(row)
            prior_path = f'inputs/{region}/surface/als_surface.ply'
            record = next(x for x in self.seal['files'] if x['path'] == prior_path)
            add('prior', '원래 ALS prior 형상', 'prior', '학습 입력 · 형상 변경 없음',
                lambda: self.mesh(region, record, bounds,
                    colorizer=lambda points: self.prior_colors(points, region)))
            add('mvs', 'MVS · 기존 OpenMVS', 'mvs', '원본 융합점군 · COLMAP depth와 별도 계보',
                lambda: self.baseline(region, 'mvs', bounds))
            add('mvs_colmap', 'MVS · COLMAP depth', 'mvs', '실제 감독 depth 역투영 · 원사진 RGB',
                lambda: self.baseline(region, 'mvs_colmap', bounds))
            selected = [x for x in self.seal['candidates'] if x['region'] == region and x['mesh_res'] == 512
                        and x['mesh_kind'] == 'raw' and not x.get('supplemental_only')]
            anchor = next(x for x in selected if x['iteration'] == 8000 and x['condition'] == 'D005_Pnative')
            add('anchor', 'Anchor-only · 8,000', 'anchor', '원래 Anchor · RGB TSDF512',
                lambda: self.mesh(region, anchor['surface'], bounds))
            for condition in self.base_cfg['conditions']:
                cid = condition['id']
                row = next(x for x in selected if x['iteration'] == 30000 and x['condition'] == cid)
                label = f'prior {condition["lambda_lod_anchor"]:g} · 보호 {"유지" if condition["protection"] == "native" else "해제"}'
                add(cid, label, 'geogs', 'DA3 · 30,000 step · RGB TSDF512',
                    lambda row=row: self.mesh(region, row['surface'], bounds))
            for mode in ('mvs', 'mvs_pgsr'):
                for prior in (.005, .0005):
                    try:
                        candidate, finished = self.new_candidate(region, mode, prior, bounds)
                        completed_count += int(finished)
                    except Exception as exc:
                        candidate = {'id': f'{mode}_{prior:g}', 'label': f'{mode} · prior {prior:g}',
                                     'group': 'mvs_geogs', 'representation_policy': 'surface_only',
                                     'status': 'failed', 'reason': str(exc)}
                        errors.append({'region': region, 'candidate': candidate['id'], 'error': str(exc), 'trace': traceback.format_exc()})
                    candidates.append(candidate)
            add('gt', 'Drone LiDAR · GT', 'gt', '관측 참조 · native RGB',
                lambda: self.baseline(region, 'gt', bounds))
            regions.append({'id': region, 'bounds': bounds, 'frame': '기존 EPSG:25832 local frame · m',
                'default_candidates': {'prior': 'prior', 'mvs': 'mvs_colmap', 'anchor': 'anchor', 'vanilla': 'D005_Pnative',
                                       'geogs': 'D0005_Pnative', 'mvs_geogs': 'mvs_pgsr_0.005', 'gt': 'gt'},
                'candidates': candidates})
        queue_file = self.args.new / 'queue/attempt.eh1jxGEn/status.txt'
        manifest = {'schema': 'geogs_rgb_comparison_v1', 'task_id': self.cfg['task_id'],
                    'scientific_verdict': None, 'built_at': datetime.now(timezone.utc).isoformat(),
                    'run_status': {'completed': completed_count, 'total': 12,
                                   'available_mvs_surfaces': sum(c['group'] == 'mvs_geogs' and c['status'] == 'available'
                                       for r in regions for c in r['candidates']),
                                   'queue_status': queue_file.read_text().strip() if queue_file.exists() else 'UNKNOWN'},
                    'regions': regions, 'crs': self.base_cfg['crs'], 'errors': errors,
                    'source_code': self.code, 'config_sha256': sha(self.args.config),
                    'notes': ['RGB 색상은 형상 정확도 또는 현재성 판정이 아닙니다.',
                              'GT 원본·학습 결과를 수정하지 않는 별도 표시 자료입니다.']}
        final = self.args.new / 'evaluation/finalization_receipt_v1.json'
        if final.exists():
            receipt = read(final)
            if receipt['status'] == 'PASS':
                manifest['report'] = '/results/evaluation/' + Path(receipt['report_path']).parent.name + '/REPORT.md'
        snapshot = f'manifest_{time.time_ns()}.json'
        write(self.root / 'snapshots' / snapshot, manifest)
        atomic(self.root / 'manifest.json', manifest)
        atomic(self.root / 'builder_status.json', {'status': 'PASS' if not errors else 'PARTIAL',
               'scientific_verdict': None, 'snapshot': snapshot, 'errors': errors,
               'completed_training_runs': completed_count, 'updated_at': manifest['built_at']})
        print(json.dumps({'status': 'PASS' if not errors else 'PARTIAL', 'completed': completed_count,
                          'errors': len(errors), 'built_at': manifest['built_at']}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    for name in ('base', 'new', 'reference', 'raw-uas', 'output', 'config'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker required')
    publisher = Publisher(args)
    while True:
        publisher.build()
        if not args.watch:
            break
        time.sleep(publisher.cfg['poll_seconds'])


if __name__ == '__main__':
    main()
