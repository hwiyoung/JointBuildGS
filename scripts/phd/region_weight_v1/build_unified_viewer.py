"""Bind completed P1/P2/P3 runs to their actual supervision regions, without training."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch
import numpy as np
from PIL import Image


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def main():
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Run in the pinned Docker image')
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--payload', default='/payload')
    ap.add_argument('--out', default='/out')
    args = ap.parse_args()
    cfg, p, out = read(args.config), Path(args.payload), Path(args.out)
    v = p / cfg['viewer_root']
    if (out / 'manifest.json').exists():
        raise RuntimeError('Output exists; use a new publication directory')
    inputs, completion = {}, []

    def bound(path):
        inputs[str(path)] = sha(path)
        return read(path)

    def asset(path):
        # New output directory is mounted separately; public URLs remain /data/.
        rel = cfg['destination'] + '/' + str(path.relative_to(out)) if path.is_relative_to(out) else str(path.relative_to(v))
        return dict(url='/data/' + rel, bytes=path.stat().st_size, sha256=sha(path))

    manifests = [bound(v / d / 'manifest.json') for d in ['p1_weights_v1', 'p2p3_weights_v1']]
    regions = copy.deepcopy([r for m in manifests for r in m['regions']])
    for region in ['P1', 'P2', 'P3']:
        run = p / cfg['P1'] if region == 'P1' else p / cfg['P2P3'] / region
        vr = v / 'p1_weights_v1' if region == 'P1' else v / 'p2p3_weights_v1' / region
        config = bound(run / 'config.json')
        mask_path = run / 'mask' / ('r1_mask.npz' if region == 'P1' else 'manifest.json')
        inputs[str(mask_path)] = sha(mask_path)
        for alpha in [0, 1, 4]:
            tr = run / f'train/alpha_{alpha}'
            er = vr / f'alpha_{alpha}'
            train = bound(tr / 'receipt.json')
            final = bound(tr / 'model/jbgs_complete/iteration_30000/receipt.json')
            extraction = bound(er / 'extraction/receipt.json')
            publication = bound(er / 'publication.json')
            assert train['status'] == extraction['status'] == 'PASS'
            assert final['iteration'] == 30000
            assert publication['status'] == 'PASS_INDIVIDUAL_FINAL_DISPLAY'
            provenance = publication['provenance']
            assert provenance['training_receipt_sha256'] == sha(tr / 'receipt.json')
            assert provenance['extraction_receipt_sha256'] == sha(er / 'extraction/receipt.json')
            assert provenance['config_sha256'] == sha(run / 'config.json')
            assert provenance['mask_sha256'] == sha(mask_path)
            for r in regions:
                if r['id'].split('_')[0] == region:
                    c = next(c for c in r['conditions'] if c['id'] == f'alpha_{alpha}')
                    assert c['status'] == 'available' and c['provenance'] == provenance
            completion.append(dict(region=region, alpha=alpha, iteration=30000,
                                   train=train['status'], extraction=extraction['status'],
                                   publication=publication['status'],
                                   completed_at=datetime.fromtimestamp(publication['completed_unix'], timezone.utc).isoformat()))

        if region == 'P1':
            sys.path.insert(0, str(Path(__file__).parent))
            inputs[str(Path(__file__).parent / 'mvs_depth.py')] = sha(Path(__file__).parent / 'mvs_depth.py')
            from mvs_depth import read_colmap_depth
            bp = p / cfg['mvs_root'] / 'P1'
            binding = bound(bp / 'bindings.json')
            assert sha(bp / 'bindings.json') == config['binding_sha256']
            camera = next(row for row in binding['train'] if Path(row['name']).stem == config['target_camera'])
            depth = read_colmap_depth(bp / camera['local_depth'], camera['maps']['depth'])
            inputs[str(bp / camera['local_depth'])] = camera['maps']['depth']['sha256']
            with np.load(mask_path, allow_pickle=False) as m:
                labels, valid, use, r1 = [m[k].copy() for k in ['region_id_native', 'valid_native', 'use_native', 'r1_native']]
                assert np.array_equal(use, valid & np.isin(labels, [1, 2, 3]))
                assert np.array_equal(r1, valid & (labels == 1))
                assert np.array_equal(m['use_mask'], m['valid_rgb'] & np.isin(m['region_id'], [1, 2, 3]))
                assert np.array_equal(m['r1_mask'], m['valid_rgb'] & (m['region_id'] == 1))
            assert np.array_equal(valid, np.isfinite(depth) & (depth > 0))
            font_manager.fontManager.addfont(cfg['font'])
            plt.rcParams.update({'font.family': font_manager.FontProperties(fname=cfg['font']).get_name(), 'axes.unicode_minus': False})
            fig, axes = plt.subplots(2, 3, figsize=(18, 11))
            view = next(r for r in regions if r['id'] == 'P1')['views'][0]
            rgb = v / view['original']['url'].removeprefix('/data/')
            axes[0, 0].imshow(Image.open(rgb)); axes[0, 0].set_title('원사진 · 0100_D 전체 프레임')
            cm = matplotlib.colormaps['viridis'].copy(); cm.set_bad('#ededed')
            im = axes[0, 1].imshow(np.ma.masked_where(~valid, depth), cmap=cm, vmin=50, vmax=85)
            fig.colorbar(im, ax=axes[0, 1], fraction=.035, label='카메라 Z 깊이 (m)')
            axes[0, 1].set_title('입력 native MVS · 색은 거리값')
            colors = ['#E69F00', '#267DB3', '#6F8C62', '#BD5C86', '#B8B8BE', '#353A40']
            axes[0, 2].imshow(labels, cmap=ListedColormap(colors), norm=BoundaryNorm(np.arange(.5, 7), 6), interpolation='nearest')
            axes[0, 2].set_title('동결된 학습 마스크의 R1–R6')
            for i, a in enumerate([0, 1, 4]):
                w = np.where(r1, a, np.where(use, 1, 0))
                display = np.where(w == 4, 2, w)
                axes[1, i].imshow(display, cmap=ListedColormap(['#ededed', '#009E73', '#E69F00']), norm=BoundaryNorm([-.5, .5, 1.5, 2.5], 3), interpolation='nearest')
                axes[1, i].set_title(f'실제 상대 가중치 · R1 = {a}')
            for ax in axes.flat:
                ax.set_xticks([]); ax.set_yticks([])
            fig.suptitle('P1 · DJI_20241217084553_0100_D.JPG · 입력 depth와 실제 가중치', fontsize=19)
            fig.legend(handles=[Patch(color=c, label=l) for c, l in zip(colors, ['R1 보정 시험 지면', 'R2 건물', 'R3 정적 지면', 'R4 제외', 'R5 유보', 'R6 범위 밖'])], loc='lower center', bbox_to_anchor=(.5, .065), ncol=6)
            fig.text(.05, .043, '가중치 그림: 회색 0 · 초록 1 · 주황 4. R2·R3는 1, 제외·유보·범위 밖·결측은 0. 전역 MVS 계수 0.05.', fontsize=12)
            fig.text(.05, .015, 'P1은 0100_D만 이 마스크 적용; 다른 97개 depth는 기존 조건 유지. 0099_D는 평가뷰로 학습 감독 미적용.', fontsize=12)
            fig.subplots_adjust(left=.015, right=.985, top=.91, bottom=.14, wspace=.10, hspace=.20)
            figure = out / 'P1_0100_native_regions_weights.png'
            fig.savefig(figure, dpi=140); plt.close(fig)
            policy = 'P1: 0100_D 한 장에만 수동 마스크 적용 · 나머지 97개 학습 depth는 기존 감독 유지. R1은 보정 시험 지면입니다.'
            source_masks = {camera['name']: dict(figure=asset(figure), mask_sha256=sha(mask_path), applied=True)}
        else:
            masks = bound(mask_path)
            review_path = v / 'p2p3_manual_regions_v1' / region / 'review.json'
            review = bound(review_path)
            assert masks['annotation_receipt_sha256'] == review['annotations_receipt_sha256']
            assert masks['annotation_config_sha256'] == review['config_sha256']
            source_masks = {}
            for row in review['sources']:
                m = next(m for m in masks['views'] if m['camera'] == Path(row['name']).stem)
                actual = mask_path.parent / m['path']
                assert sha(actual) == m['sha256']
                inputs[str(actual)] = sha(actual)
                with np.load(actual, allow_pickle=False) as array:
                    counts = {str(i): int((array['region_id'] == i).sum()) for i in range(1, 7)}
                    assert counts == row['rgb_counts']
                source_masks[row['name']] = dict(figure=asset(review_path.parent / row['image']),
                    mask_sha256=m['sha256'], applied=True,
                    gallery_url=f'/app/manual_regions.html?region={region}&view={row["train_index"]}',
                    all_views_url=f'/app/manual_regions.html?region={region}&mode=all&view={row["train_index"]}')
            target = '반복 아치 지붕' if region == 'P2' else '긴 곡면 지붕과 전면 외벽'
            policy = f'{region}: 전체 {len(masks["views"])}개 학습 depth에 영역 마스크 적용. R1은 {target}입니다. 기준 영상 2장의 수동 분류를 MVS 대응으로 다른 뷰에 전파했습니다.'
        for r in regions:
            if r['id'].split('_')[0] != region:
                continue
            r['weight_policy'] = policy
            for view in r['views']:
                view['weights'] = source_masks.get(view['image_name'], dict(applied=False,
                    reason='0099_D는 평가뷰입니다. 학습 depth 감독에 사용하지 않아 적용된 가중치 영역이 없습니다. 0100_D 학습뷰를 선택하면 실제 영역도가 표시됩니다.'))

    # Verify every old and new display asset before publishing the combined manifest.
    verified = {}
    def verify(obj):
        if isinstance(obj, dict):
            if all(k in obj for k in ['url', 'bytes', 'sha256']):
                u = obj['url']; prefix = '/data/' + cfg['destination'] + '/'
                path = out / u.removeprefix(prefix) if u.startswith(prefix) else v / u.removeprefix('/data/')
                if u not in verified:
                    assert path.stat().st_size == obj['bytes'] and sha(path) == obj['sha256'], u
                    verified[u] = obj['sha256']
            for item in obj.values(): verify(item)
        elif isinstance(obj, list):
            for item in obj: verify(item)
    verify(regions)
    now = datetime.now(timezone.utc).isoformat()
    manifest = dict(schema='unified_weight_comparison_v1', task_id=cfg['task_id'], scientific_verdict=None,
                    generated_at=now, regions=regions, completion=completion,
                    run_status=dict(completed=9, total=9, label='9/9 완료 · 각 30,000회 학습 + 표면 추출 + 렌더 등록'),
                    surface_contract=dict(label='Raw RGB TSDF512 · 각 대상 내 동일 추출 조건',
                        parameters={'P1': manifests[0]['surface_contract']['parameters'], **manifests[1]['surface_contract']['parameters']}))
    save(out / 'manifest.json', manifest)
    save(out / 'receipt.json', dict(status='PASS_COMPLETION_AND_WEIGHT_LINKAGE', scientific_verdict=None,
         generated_at=now, training_changed=False, scoring_changed=False, completion=completion,
         inputs=inputs, display_assets_verified=verified, config_sha256=sha(args.config),
         script_sha256=sha(__file__), manifest_sha256=sha(out / 'manifest.json'), runtime=cfg['runtime_image'],
         python=sys.version, numpy=np.__version__, matplotlib=matplotlib.__version__))
    print(json.dumps(dict(status='PASS_COMPLETION_AND_WEIGHT_LINKAGE', completed=len(completion), assets=len(verified))))


if __name__ == '__main__':
    main()
