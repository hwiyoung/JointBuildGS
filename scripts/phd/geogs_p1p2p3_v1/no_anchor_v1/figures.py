"""Assemble fixed section frames and plot saved reference-proximity transitions."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
import numpy as np
from PIL import Image


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--task', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--regions', nargs='+', choices=['P1', 'P2', 'P3'], default=['P1', 'P2', 'P3'])
    p.add_argument('--support-relative', default='support_transitions_v1')
    p.add_argument('--output-relative', default='comparison_figures_v1')
    a = p.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker required')
    for value in (a.support_relative, a.output_relative):
        if Path(value).is_absolute() or '..' in Path(value).parts:
            raise ValueError('Fresh relative output required')
    dest = a.out / a.output_relative
    dest.mkdir(parents=True, exist_ok=False)
    items, inputs = [], {}
    cfg = json.loads((a.task / 'contracts/execution_v1.json').read_text())
    colors = ['#808890', '#168a63', '#d14845', '#d8dadd']
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(np.arange(-.5, 4.5), 4)
    for region in a.regions:
        for kind in ('raw', 'post'):
            sources = [a.task / 'evaluation/viewer' / region / (c + '.sections.png') for c in (
                'prior_mesh', 'D005_Pnative.anchor_512.' + kind,
                'D005_Pnative.mesh_512.' + kind, 'D0005_Pnative.mesh_512.' + kind)]
            sources += [a.out / 'viewer' / region /
                f'SFM_noanchor_D005_Pnative_R{n}.mesh_512.{kind}.sections.png' for n in (22000, 30000)]
            frames = []
            for source in sources:
                inputs[str(source)] = sha(source)
                with Image.open(source) as image:
                    frames.append(image.convert('RGB'))
            if len({im.size for im in frames}) != 1:
                raise ValueError('Fixed section frame sizes differ')
            w, h = frames[0].size
            stack = Image.new('RGB', (w, h * len(frames)), 'white')
            for i, frame in enumerate(frames):
                stack.paste(frame, (0, i * h))
            path = dest / f'{region}.{kind}.matched_sections.png'
            stack.save(path)
            with Image.open(path) as actual:
                for i, frame in enumerate(frames):
                    assert actual.crop((0, i * h, w, (i + 1) * h)).tobytes() == frame.tobytes()
            items.append(dict(region=region, kind=kind, path=path.name, sha256=sha(path),
                source_paths=[str(s) for s in sources], operation='VERTICAL_CONCATENATION_WITHOUT_RESAMPLING',
                pixel_equality_verified=True, selection='all existing fixed regional sections'))
            fig, axes = plt.subplots(2, 2, figsize=(12, 10), constrained_layout=True)
            bounds = cfg['regions'][region]['domain']
            for row, baseline in enumerate(('D005_Pnative', 'D0005_Pnative')):
                for col, iteration in enumerate((22000, 30000)):
                    name = f'{region}.{baseline}__to__SFM_noanchor_D005_Pnative_R{iteration}.{kind}.npz'
                    source = a.out / a.support_relative / name
                    inputs[str(source)] = sha(source)
                    with np.load(source, allow_pickle=False) as data:
                        xyz = data['reference_points']
                        index = np.flatnonzero(data['thresholds_m'] == .5)
                        assert len(index) == 1
                        codes = data['status_codes'][index[0]]
                    ax = axes[row, col]
                    # Stable display-only stride; rates use every saved reference point.
                    stride = max(1, int(np.ceil(len(xyz) / 250000)))
                    shown = np.arange(0, len(xyz), stride)
                    counts = np.bincount(codes, minlength=4)
                    fractions = counts / len(codes) if len(codes) else np.full(4, np.nan)
                    scatter = ax.scatter(xyz[shown, 0], xyz[shown, 1], c=codes[shown], cmap=cmap,
                        norm=norm, s=1.5, linewidths=0, rasterized=True)
                    ax.set_aspect('equal')
                    ax.set_title(f'{baseline} -> SfM {iteration:,}\nnew {fractions[1]:.1%}; lost {fractions[2]:.1%}')
                    ax.set_xlabel('Scene-local X (m)')
                    ax.set_ylabel('Scene-local Y (m)')
                    items.append(dict(region=region, kind=kind, transition_array=str(source),
                        threshold_m=.5, exact_all_reference_counts=counts.tolist(),
                        display_stride=stride, displayed_reference_points=len(shown),
                        all_reference_points=len(xyz), temporal_labels=False))
            fig.suptitle(f'{region} / TSDF512 {kind}: reference-to-surface proximity < 0.5 m\n'
                'Observed reference only; temporal asset validity is not classified')
            bar = fig.colorbar(scatter, ax=axes, ticks=range(4), shrink=.65)
            bar.ax.set_yticklabels(['retained hit', 'new hit', 'lost hit', 'still missed'])
            path = dest / f'{region}.{kind}.reference_transitions.png'
            fig.savefig(path, dpi=160)
            plt.close(fig)
            items.append(dict(region=region, kind=kind, path=path.name, sha256=sha(path),
                threshold_m=.5, selection='all fixed regional reference points; display-only stable stride'))
    for name, digest in inputs.items():
        if sha(Path(name)) != digest:
            raise ValueError('Evidence source changed during plotting')
    with (dest / 'receipt.json').open('x') as stream:
        json.dump(dict(status='PASS_FIXED_EVIDENCE_FIGURES', scientific_verdict=None,
            regions=a.regions, source_sha256=inputs, generated=items, script_sha256=sha(Path(__file__)),
            geometry_alignment_performed=False, quality_metrics_recomputed=False), stream, indent=2)
    print(json.dumps(dict(status='PASS_FIXED_EVIDENCE_FIGURES', output=str(dest))))


if __name__ == '__main__':
    main()
