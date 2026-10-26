"""
Full evaluation: M3C2 + Chamfer Distance + Traditional Completeness + Voxel Occupancy.

Combines M3C2 distance (from compute_m3c2.py) with classical point cloud metrics
(from eval.py/eval_utils.py) into a single script with unified output.

Usage:
    python evaluation/eval_full.py \
        --eval_path evaluation/GeoGS_pcd_results/b5_15_2dgs.ply

    python evaluation/eval_full.py \
        --eval_path evaluation/GeoGS_mesh_results/b5_15_geogs_pcd.ply \
        --downsample_voxel 0.2
"""

import argparse
import datetime
import os
import time
import numpy as np
import py4dgeo
from scipy.spatial import cKDTree
from plyfile import PlyData, PlyElement
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap


# ── I/O ──────────────────────────────────────────────────────────────────────

def load_ply_points(path):
    """Load xyz coordinates from a PLY file as float64."""
    ply = PlyData.read(path)
    v = ply['vertex']
    return np.vstack([v['x'], v['y'], v['z']]).T.astype(np.float64)


def m3c2_colormap(values, vmin, vmax):
    colors = [(0, 0, 1), (1, 1, 1), (1, 0, 0)]
    cmap = LinearSegmentedColormap.from_list('bwr', colors, N=256)
    normalized = np.clip((values - vmin) / (vmax - vmin + 1e-12), 0, 1)
    rgba = cmap(normalized)
    return (rgba[:, :3] * 255).astype(np.uint8)


def save_colored_ply(points, colors, output_path):
    vertices = np.zeros(len(points), dtype=[
        ('x', 'f4'), ('y', 'f4'), ('z', 'f4'),
        ('red', 'u1'), ('green', 'u1'), ('blue', 'u1')
    ])
    vertices['x'] = points[:, 0]
    vertices['y'] = points[:, 1]
    vertices['z'] = points[:, 2]
    vertices['red'] = colors[:, 0]
    vertices['green'] = colors[:, 1]
    vertices['blue'] = colors[:, 2]
    el = PlyElement.describe(vertices, 'vertex')
    PlyData([el], text=False).write(output_path)


def voxel_downsample(pts, voxel_size):
    """Voxel grid downsampling, returns subset of original points."""
    voxel_idx = np.floor(pts / voxel_size).astype(np.int64)
    _, unique_idx = np.unique(voxel_idx, axis=0, return_index=True)
    return pts[unique_idx].copy()


# ── Metrics ──────────────────────────────────────────────────────────────────

def compute_chamfer_distance(pts1, pts2):
    """Chamfer distance = mean of bidirectional mean NN distances."""
    tree1 = cKDTree(pts1)
    tree2 = cKDTree(pts2)
    d1, _ = tree2.query(pts1)
    d2, _ = tree1.query(pts2)
    return (np.mean(d1) + np.mean(d2)) / 2.0, np.mean(d1), np.mean(d2)


def compute_completeness(gt_pts, eval_pts, thresholds):
    """Fraction of GT points with a NN in eval within each threshold."""
    tree = cKDTree(eval_pts)
    dists, _ = tree.query(gt_pts)
    results = {}
    for t in thresholds:
        results[t] = float(np.sum(dists < t)) / len(gt_pts)
    return results


def compute_voxel_occupancy(gt_pts, eval_pts, voxel_size, min_points):
    """Voxel occupancy completeness."""
    from collections import Counter
    min_bound = np.minimum(gt_pts.min(0), eval_pts.min(0)) - voxel_size
    gt_vi = [tuple(v) for v in np.floor((gt_pts - min_bound) / voxel_size).astype(int)]
    eval_vi = [tuple(v) for v in np.floor((eval_pts - min_bound) / voxel_size).astype(int)]
    gt_occ = {v for v, c in Counter(gt_vi).items() if c >= min_points}
    eval_occ = {v for v, c in Counter(eval_vi).items() if c >= min_points}
    if len(gt_occ) == 0:
        return 0.0, 0, 0, 0
    intersect = gt_occ & eval_occ
    return len(intersect) / len(gt_occ), len(gt_occ), len(eval_occ), len(intersect)


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description='Full point cloud evaluation (M3C2 + CD + Completeness)')
    p.add_argument('--gt_path', type=str,
                   default='./evaluation_data/example_ply/gt_transformed.ply')
    p.add_argument('--eval_path', type=str,
                   default='./evaluation_data/example_ply/pred.ply')
    p.add_argument('--output_root', type=str,
                   default='./evaluation_data/results')

    # M3C2 parameters (dense preset)
    p.add_argument('--m3c2_corepoint_spacing', type=float, default=0.1)
    p.add_argument('--m3c2_normal_radius', type=float, default=0.5)
    p.add_argument('--m3c2_cyl_radius', type=float, default=0.25)
    p.add_argument('--m3c2_max_distance', type=float, default=5.0)
    p.add_argument('--m3c2_color_range', type=float, default=2.0)

    # Downsampling for CD / completeness
    p.add_argument('--downsample_voxel', type=float, default=0.1,
                   help='Voxel size for downsampling before CD and completeness. '
                        'Set to 0 to disable downsampling.')

    # Traditional completeness
    p.add_argument('--completeness_thresholds', type=float, nargs='+',
                   default=[0.1, 0.2, 0.5],
                   help='Distance thresholds (meters) for traditional completeness.')

    # Voxel occupancy
    p.add_argument('--voxel_occupancy_size', type=float, default=0.5)
    p.add_argument('--voxel_occupancy_min_pts', type=int, default=2,
                   help='Min points to consider a voxel occupied. '
                        'Set to 1 for sparse clouds (~0.4m spacing).')

    return p.parse_args()


def make_output_dir(output_root, eval_path):
    """Create output folder name from eval_path basename.
    e.g. .../GeoGS_pcd_results/b5_15_2dgs.ply -> pcd_b5_15_2dgs
    """
    basename = os.path.splitext(os.path.basename(eval_path))[0]
    parent = os.path.basename(os.path.dirname(eval_path))
    if 'pcd' in parent.lower():
        prefix = 'pcd'
    elif 'mesh' in parent.lower():
        prefix = 'mesh'
    else:
        prefix = 'eval'
    folder = f"{prefix}_{basename}"
    out_dir = os.path.join(output_root, folder)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # --- Setup output directory ---
    out_dir = make_output_dir(args.output_root, args.eval_path)
    print(f"Output directory: {out_dir}")

    # --- Load point clouds ---
    print("\n[1/5] Loading point clouds...")
    t0 = time.time()
    gt_pts = load_ply_points(args.gt_path)
    eval_pts = load_ply_points(args.eval_path)
    print(f"  GT: {len(gt_pts)} points")
    print(f"  Eval: {len(eval_pts)} points")
    print(f"  Loaded in {time.time()-t0:.1f}s")

    # ======================================================================
    # M3C2
    # ======================================================================
    print(f"\n[2/5] Computing M3C2 (normal_r={args.m3c2_normal_radius}, "
          f"cyl_r={args.m3c2_cyl_radius})...")
    t1 = time.time()

    epoch_gt = py4dgeo.Epoch(gt_pts)
    epoch_eval = py4dgeo.Epoch(eval_pts)

    corepoints = voxel_downsample(gt_pts, args.m3c2_corepoint_spacing)
    print(f"  Corepoints: {len(corepoints)}")

    m3c2 = py4dgeo.M3C2(
        epochs=(epoch_gt, epoch_eval),
        corepoints=corepoints,
        normal_radii=[args.m3c2_normal_radius],
        cyl_radius=args.m3c2_cyl_radius,
        max_distance=args.m3c2_max_distance,
    )
    distances, uncertainties = m3c2.run()
    distances = distances.flatten()
    uncertainties = uncertainties.flatten()

    valid_mask = np.isfinite(distances)
    valid_dists = distances[valid_mask]
    n_total = len(distances)
    n_valid = int(valid_mask.sum())
    print(f"  Valid: {n_valid}/{n_total} ({100*n_valid/n_total:.1f}%)")
    print(f"  M3C2 completed in {time.time()-t1:.1f}s")

    # M3C2 stats
    m3c2_stats = {}
    if n_valid > 0:
        m3c2_stats = {
            'mean_dist': float(np.mean(valid_dists)),
            'median_dist': float(np.median(valid_dists)),
            'std': float(np.std(valid_dists)),
            'mean_abs_dist': float(np.mean(np.abs(valid_dists))),
            'rmse': float(np.sqrt(np.mean(valid_dists**2))),
            'min': float(np.min(valid_dists)),
            'max': float(np.max(valid_dists)),
        }
        print(f"  Mean |dist| = {m3c2_stats['mean_abs_dist']:.4f}m, "
              f"RMSE = {m3c2_stats['rmse']:.4f}m")

    # Save M3C2 colored PLY
    if n_valid > 0:
        vmin, vmax = -args.m3c2_color_range, args.m3c2_color_range
        colors = np.full((n_total, 3), 128, dtype=np.uint8)
        colors[valid_mask] = m3c2_colormap(valid_dists, vmin, vmax)
        save_colored_ply(corepoints, colors, os.path.join(out_dir, 'm3c2_colored.ply'))

    # Save M3C2 histogram
    if n_valid > 0:
        fig, ax = plt.subplots(figsize=(10, 6))
        bwr_cmap = LinearSegmentedColormap.from_list('bwr',
                        [(0, 0, 1), (1, 1, 1), (1, 0, 0)], N=256)
        max_abs = min(np.percentile(np.abs(valid_dists), 99), args.m3c2_color_range * 2)
        bins = np.linspace(-max_abs, max_abs, 60)
        n_hist, bin_edges, patches = ax.hist(valid_dists, bins=bins, edgecolor='black',
                                             alpha=0.8, linewidth=0.5)
        bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
        norm_centers = (bin_centers - (-max_abs)) / (2 * max_abs)
        for c, p in zip(norm_centers, patches):
            p.set_facecolor(bwr_cmap(np.clip(c, 0, 1)))

        ax.set_title('M3C2 Signed Distance Distribution', fontsize=14)
        ax.set_xlabel('M3C2 Distance (m)', fontsize=12)
        ax.set_ylabel('Frequency', fontsize=12)
        ax.grid(True, alpha=0.3)
        mean_line = ax.axvline(np.mean(valid_dists), color='k', linestyle='--', linewidth=1.5)
        median_line = ax.axvline(np.median(valid_dists), color='green', linestyle='--', linewidth=1.5)
        stats_text = (f'n = {n_valid}\n'
                      f'RMSE = {m3c2_stats["rmse"]:.4f} m')
        stats_handle = ax.plot([], [], ' ', label=stats_text)[0]
        ax.legend(
            [stats_handle, mean_line, median_line],
            [stats_text, f'Mean = {m3c2_stats["mean_dist"]:.4f} m',
             f'Median = {m3c2_stats["median_dist"]:.4f} m'],
            fontsize=11, loc='upper right', framealpha=0.8, edgecolor='gray')
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, 'm3c2_histogram.png'), dpi=300, bbox_inches='tight')
        plt.close(fig)

    # Save raw M3C2 distances
    np.save(os.path.join(out_dir, 'm3c2_distances.npy'), distances)

    # ======================================================================
    # Downsample for CD & Completeness
    # ======================================================================
    if args.downsample_voxel > 0:
        print(f"\n[3/5] Downsampling for CD & Completeness (voxel={args.downsample_voxel}m)...")
        gt_ds = voxel_downsample(gt_pts, args.downsample_voxel)
        eval_ds = voxel_downsample(eval_pts, args.downsample_voxel)
        print(f"  GT: {len(gt_pts)} -> {len(gt_ds)}")
        print(f"  Eval: {len(eval_pts)} -> {len(eval_ds)}")
    else:
        print(f"\n[3/5] No downsampling (using full clouds)...")
        gt_ds = gt_pts
        eval_ds = eval_pts

    # ======================================================================
    # Chamfer Distance
    # ======================================================================
    print("\n[4/5] Computing Chamfer Distance...")
    t2 = time.time()
    cd, cd_gt2eval, cd_eval2gt = compute_chamfer_distance(gt_ds, eval_ds)
    print(f"  Chamfer Distance: {cd:.6f}m (GT->Eval: {cd_gt2eval:.6f}, Eval->GT: {cd_eval2gt:.6f})")
    print(f"  Completed in {time.time()-t2:.1f}s")

    # Traditional Completeness
    print(f"  Traditional Completeness (thresholds={args.completeness_thresholds})...")
    comp = compute_completeness(gt_ds, eval_ds, args.completeness_thresholds)
    for t, v in comp.items():
        print(f"    {t}m: {v*100:.2f}%")

    # ======================================================================
    # Voxel Occupancy Completeness (on full clouds, no downsampling needed)
    # ======================================================================
    print(f"\n[5/5] Computing Voxel Occupancy Completeness "
          f"(voxel={args.voxel_occupancy_size}m, min_pts={args.voxel_occupancy_min_pts})...")
    t3 = time.time()
    voc, gt_vox, eval_vox, inter_vox = compute_voxel_occupancy(
        gt_pts, eval_pts, args.voxel_occupancy_size, args.voxel_occupancy_min_pts)
    print(f"  GT voxels: {gt_vox}, Eval voxels: {eval_vox}, Intersection: {inter_vox}")
    print(f"  Voxel Occupancy Completeness: {voc*100:.2f}%")
    print(f"  Completed in {time.time()-t3:.1f}s")

    # ======================================================================
    # Save statistics
    # ======================================================================
    stats_path = os.path.join(out_dir, 'statistics.txt')
    with open(stats_path, 'w') as f:
        f.write("Full Point Cloud Evaluation Results\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"GT cloud:   {args.gt_path}\n")
        f.write(f"Eval cloud: {args.eval_path}\n")
        f.write(f"GT points:  {len(gt_pts)}\n")
        f.write(f"Eval points: {len(eval_pts)}\n\n")

        # M3C2 section
        f.write("-" * 60 + "\n")
        f.write("M3C2 Distance\n")
        f.write("-" * 60 + "\n")
        f.write(f"Parameters:\n")
        f.write(f"  Corepoint spacing: {args.m3c2_corepoint_spacing} m\n")
        f.write(f"  Normal radius:     {args.m3c2_normal_radius} m\n")
        f.write(f"  Cylinder radius:   {args.m3c2_cyl_radius} m\n")
        f.write(f"  Max distance:      {args.m3c2_max_distance} m\n\n")
        f.write(f"Total corepoints: {n_total}\n")
        f.write(f"Valid distances:  {n_valid} ({100*n_valid/n_total:.1f}%)\n")
        f.write(f"NaN (no match):  {n_total - n_valid} ({100*(n_total-n_valid)/n_total:.1f}%)\n\n")
        if n_valid > 0:
            f.write(f"Mean distance:    {m3c2_stats['mean_dist']:.6f} m\n")
            f.write(f"Median distance:  {m3c2_stats['median_dist']:.6f} m\n")
            f.write(f"Std deviation:    {m3c2_stats['std']:.6f} m\n")
            f.write(f"Mean |distance|:  {m3c2_stats['mean_abs_dist']:.6f} m\n")
            f.write(f"RMSE:             {m3c2_stats['rmse']:.6f} m\n")
            f.write(f"Min:              {m3c2_stats['min']:.6f} m\n")
            f.write(f"Max:              {m3c2_stats['max']:.6f} m\n\n")
            for p in [25, 50, 75, 90, 95]:
                f.write(f"  {p}th percentile |d|: {np.percentile(np.abs(valid_dists), p):.6f} m\n")

        # CD section
        f.write(f"\n" + "-" * 60 + "\n")
        f.write("Chamfer Distance\n")
        f.write("-" * 60 + "\n")
        if args.downsample_voxel > 0:
            f.write(f"Downsampling: voxel_size={args.downsample_voxel} m\n")
            f.write(f"  GT:   {len(gt_pts)} -> {len(gt_ds)} points\n")
            f.write(f"  Eval: {len(eval_pts)} -> {len(eval_ds)} points\n\n")
        else:
            f.write(f"Downsampling: disabled\n\n")
        f.write(f"Chamfer Distance: {cd:.6f} m\n")
        f.write(f"  GT -> Eval (accuracy):     {cd_gt2eval:.6f} m\n")
        f.write(f"  Eval -> GT (completeness): {cd_eval2gt:.6f} m\n")

        # Traditional Completeness section
        f.write(f"\n" + "-" * 60 + "\n")
        f.write("Traditional Completeness\n")
        f.write("-" * 60 + "\n")
        if args.downsample_voxel > 0:
            f.write(f"Downsampling: voxel_size={args.downsample_voxel} m\n\n")
        else:
            f.write(f"Downsampling: disabled\n\n")
        for t, v in comp.items():
            f.write(f"Threshold {t:.2f}m: {v:.4f} ({v*100:.2f}%)\n")

        # Voxel Occupancy section
        f.write(f"\n" + "-" * 60 + "\n")
        f.write("Voxel Occupancy Completeness\n")
        f.write("-" * 60 + "\n")
        f.write(f"Parameters:\n")
        f.write(f"  Voxel size:       {args.voxel_occupancy_size} m\n")
        f.write(f"  Min points:       {args.voxel_occupancy_min_pts}\n")
        f.write(f"  (computed on full clouds, no downsampling)\n\n")
        f.write(f"GT occupied voxels:   {gt_vox}\n")
        f.write(f"Eval occupied voxels: {eval_vox}\n")
        f.write(f"Intersection:         {inter_vox}\n")
        f.write(f"Completeness:         {voc:.4f} ({voc*100:.2f}%)\n")

        f.write(f"\n" + "=" * 60 + "\n")

    print(f"\nAll results saved to: {out_dir}/")
    print("Done.")


if __name__ == '__main__':
    main()
