"""Extract exact anchor and resolution sensitivities through official render.py."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

from parse_extraction import PARSER_SOURCE, PARSER_SHA256, parse_extraction_log
from repeat_contract import REPEAT_HELPER_SOURCE, load_repeat_binding, require_repeat_receipt


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--region', required=True)
    parser.add_argument('--condition', required=True)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists() or Path('/reference').exists():
        raise RuntimeError('Use the isolated reference-free Docker runtime')
    cfg = json.loads(args.config.read_text())
    repeat_binding = load_repeat_binding(args.config, '/runtime_layout.json', args.region, args.condition, 'auxiliary')
    output = Path('/output')
    source_model = output / 'model'
    train = json.loads((output / 'train_receipt.json').read_text())
    require_repeat_receipt(train, repeat_binding)
    if train['status'] != 'PASS':
        raise ValueError('A completed fixed training is required')
    variants = [('mesh_' + str(resolution), 30000, resolution, False)
                for resolution in cfg['extraction']['sensitivity_mesh_res']]
    if args.condition == 'D005_Pnative':
        variants.insert(0, ('anchor', 8000, cfg['extraction']['mesh_res'], True))
    receipts = []
    for name, iteration, resolution, export_images in variants:
        destination = output / 'auxiliary' / name
        destination.mkdir(parents=True, exist_ok=False)
        with (destination / 'parse_extraction_snapshot.py').open('xb') as f:
            f.write(PARSER_SOURCE)
        if repeat_binding:
            with (destination / 'repeat_contract_snapshot.json').open('xb') as f:
                f.write(Path('/repeat_contract.json').read_bytes())
            with (destination / 'repeat_helper_snapshot.py').open('xb') as f:
                f.write(REPEAT_HELPER_SOURCE)
        model = destination / 'model'
        point = model / 'point_cloud' / f'iteration_{iteration}' / 'point_cloud.ply'
        point.parent.mkdir(parents=True)
        original = source_model / 'jbgs_complete' / f'iteration_{iteration}' / 'point_cloud.ply'
        if iteration == 8000 and Path('/anchor/point_cloud.ply').exists():
            original = Path('/anchor/point_cloud.ply')
        # Exact complete-state PLY. In particular the upstream iteration8000
        # PLY precedes densification and is not the experimental anchor.
        shutil.copyfile(original, point)
        shutil.copyfile(source_model / 'cfg_args', model / 'cfg_args')
        command = ['python', 'render.py', '-s', '/input/scene', '-m', str(model),
                   '--iteration', str(iteration), '--mesh_res', str(resolution)]
        if not export_images:
            command += ['--skip_train', '--skip_test']
        start = time.time()
        invocation = {'region': args.region, 'condition': args.condition, 'variant': name,
                      'iteration': iteration, 'mesh_res': resolution, 'command': command,
                      'source_complete_ply_sha256': sha(original),
                      'copied_ply_sha256': sha(point), 'scientific_verdict': None,
                      'render_cfg_args_sha256': sha(model / 'cfg_args'),
                      'extraction_helper_snapshot': {'path': 'parse_extraction_snapshot.py', 'sha256': PARSER_SHA256},
                      'config_sha256': sha(args.config), 'started_unix': start}
        if Path('/runtime_layout.json').exists():
            invocation['runtime_layout_sha256'] = sha('/runtime_layout.json')
            invocation['runtime_revision'] = json.loads(Path('/runtime_layout.json').read_text())['revision']
        if repeat_binding:
            invocation.update(repeat_binding)
        (destination / 'invocation.json').write_text(json.dumps(invocation, indent=2))
        with (destination / 'render.log').open('x') as log:
            code = subprocess.call(command, cwd='/source', stdout=log, stderr=subprocess.STDOUT)
        native_code = code
        validation, realized_extraction = [], None
        try:
            realized_extraction = parse_extraction_log(destination / 'render.log', resolution,
                                                       cfg['extraction']['num_cluster'])
        except (OSError, UnicodeError, ValueError) as error:
            code = code or 96
            validation.append({'realized_extraction_validation_error': repr(error)})
        import numpy as np
        import open3d as o3d
        files = []
        for mesh_name in ('fuse.ply', 'fuse_post.ply'):
            mesh = model / f'train/ours_{iteration}' / mesh_name
            exists = mesh.is_file() and mesh.stat().st_size > 0
            files.append({'path': str(mesh.relative_to(destination)), 'exists': exists,
                          'sha256': sha(mesh) if exists else None})
            if not exists and code == 0:
                code = 91
            if exists:
                try:
                    actual = o3d.io.read_triangle_mesh(str(mesh))
                    finite = bool(np.isfinite(np.asarray(actual.vertices)).all())
                    area = float(actual.get_surface_area())
                    valid = len(actual.vertices) > 0 and len(actual.triangles) > 0 and finite and area > 0
                    validation.append({'path': str(mesh.relative_to(destination)), 'vertices': len(actual.vertices),
                                       'triangles': len(actual.triangles), 'finite_vertices': finite,
                                       'surface_area_m2': area, 'valid_triangle_surface': valid})
                    if not valid:
                        code = code or 95
                except Exception as error:
                    code = code or 95
                    validation.append({'surface_validation_error': repr(error)})
        if export_images:
            count = len(list((model / f'test/ours_{iteration}/renders').glob('*.png')))
            if count != cfg['regions'][args.region]['expected_test']:
                code = code or 92
        receipt = dict(invocation, status='PASS' if code == 0 else 'FAIL', exit_code=code,
                       native_exit_code=native_code, validated_exit_code=code,
                       wall_seconds=time.time() - start, files=files, validation=validation,
                       realized_extraction=realized_extraction)
        (destination / 'receipt.json').write_text(json.dumps(receipt, indent=2))
        receipts.append(receipt)
        print(json.dumps(receipt), flush=True)
        if code:
            raise SystemExit(code)
    with (output / 'auxiliary_manifest.json').open('x') as f:
        json.dump({'scientific_verdict': None, 'status': 'PASS', 'variants': receipts,
                   **(repeat_binding or {})}, f, indent=2)


if __name__ == '__main__':
    main()
