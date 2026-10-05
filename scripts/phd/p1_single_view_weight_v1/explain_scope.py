"""One-page explanation of the actual frozen mask; never modifies training."""
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from matplotlib import font_manager
import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker required')
    cfg = json.loads(Path('/source/config.json').read_text())
    for path, expected in (('/mask/r1_mask.npz', cfg['mask_sha256']),
                           ('/mvs/bindings.json', cfg['binding_sha256'])):
        if sha(path) != expected:
            raise ValueError('Frozen input differs: ' + path)
    sys.path.insert(0, '/source')
    from mvs_depth import read_colmap_depth
    binding = json.loads(Path('/mvs/bindings.json').read_text())
    view = next(row for row in binding['train'] if row['name'] == cfg['camera'])
    depth = read_colmap_depth(Path('/mvs') / view['local_depth'], view['maps']['depth'])
    with np.load('/mask/r1_mask.npz', allow_pickle=False) as data:
        use, r1, valid = (data[key].copy() for key in ('use_native', 'r1_native', 'valid_native'))
    if any(x.dtype != np.bool_ or x.shape != depth.shape for x in (use, r1, valid)):
        raise ValueError('Expected native boolean masks')
    if np.any(r1 & ~use) or np.any(use & ~valid):
        raise ValueError('Invalid support nesting')
    h, w = depth.shape
    vv, uu = np.indices((h, w))
    rays = np.stack((uu, vv, np.ones_like(uu)), -1) @ np.linalg.inv(view['maps']['depth']['K']).T
    xyz = (rays * depth[..., None] - np.asarray(view['t'])) @ np.asarray(view['R'])
    evaluation = valid.copy()
    for axis, key in enumerate('xyz'):
        lo, hi = cfg['original_evaluation_bounds'][key]
        evaluation &= (xyz[..., axis] >= lo) & (xyz[..., axis] < hi)
    font_manager.fontManager.addfont(cfg['font_path'])
    plt.rcParams.update({'font.family': font_manager.FontProperties(fname=cfg['font_path']).get_name(),
                         'axes.unicode_minus': False})
    depth_map = matplotlib.colormaps['viridis'].copy()
    depth_map.set_bad('#ededed')
    limits = np.percentile(depth[valid], cfg['depth_color_percentiles'])
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    artist = axes[0].imshow(np.ma.masked_where(~valid, depth), cmap=depth_map, vmin=limits[0], vmax=limits[1])
    axes[0].contour(evaluation, levels=[.5], colors=['#00bfff'], linewidths=2, linestyles='--')
    fig.colorbar(artist, ax=axes[0], fraction=.035, pad=.02, label='카메라 Z 깊이 (m) — 색은 사용 여부가 아님')
    axes[0].set_title('① 원본 MVS: 파란 채움은 깊이값\n청록 점선은 원래 30×30m P1 평가 경계', fontsize=13)
    axes[0].legend(handles=[Line2D([0], [0], color='#00bfff', linestyle='--', linewidth=2,
                                  label='평가 경계 · 현재 감독 마스크와 다름')], loc='lower center', fontsize=9)
    labels = np.where(r1, 2, np.where(use, 1, 0)).astype(np.uint8)
    colors = ['#ededed', '#009e73', '#e69f00']
    axes[1].imshow(labels, cmap=ListedColormap(colors), norm=BoundaryNorm([-.5,.5,1.5,2.5], 3), interpolation='nearest')
    axes[1].set_title('② 현재 0100_D 감독 마스크\n초록 + 주황만 사용 후보, 회색은 제외', fontsize=13)
    axes[1].legend(handles=[Patch(color=colors[2], label='R1: α=0 / 1 / 4'),
                            Patch(color=colors[1], label='R2·R3: 1'),
                            Patch(color=colors[0], label='제외·미분류·범위 밖·결측: 0')],
                   loc='lower center', fontsize=9)
    for ax in axes:
        ax.set_xlabel('native pixel x')
        ax.set_ylabel('native pixel y')
    fig.suptitle('현재 학습에 적용 중인 0100_D의 MVS 감독 범위', fontsize=19, y=.985)
    fig.text(.045, .072, '현재 범위는 왼쪽 청록선 안이 아니라 오른쪽 R1·R2·R3의 합집합입니다. α=0에서는 R1 감독도 0입니다.', fontsize=12)
    fig.text(.045, .038, '0100_D의 마스크와 R1 가중치만 조절합니다. 다른 97개 depth는 기존 조건으로 유지합니다. 학습 설정 변경 없음.', fontsize=11)
    fig.tight_layout(rect=[0,.11,1,.93])
    out = Path('/output/result')
    out.mkdir(exist_ok=False)
    fig.savefig(out / '0100_D_current_supervision_scope.png', dpi=140)
    fig.savefig(out / '0100_D_current_supervision_scope.pdf')
    plt.close(fig)
    receipt = dict(task_id=cfg['task_id'], status='PASS_DISPLAY_OF_FROZEN_TRAINING_MASK',
                   scientific_verdict=None, training_changed=False, source_config=cfg,
                   native_used_pixels=int(use.sum()), native_used_outside_original_30m=int((use & ~evaluation).sum()),
                   mask_sha256=sha('/mask/r1_mask.npz'), script_sha256=sha(__file__),
                   outputs={p.name: sha(p) for p in sorted(out.iterdir())})
    (out / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: receipt[k] for k in ('status','native_used_pixels','native_used_outside_original_30m','training_changed')}))


if __name__ == '__main__':
    main()
