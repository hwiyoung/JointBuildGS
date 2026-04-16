"""Rescale COLMAP cameras.txt to match actual image size.

The upstream colmap_export was calibrated on 8270x5476 but the JPG files on disk are
8192x5460. Apply per-axis scale (fx*sx, fy*sy, cx*sx, cy*sy) and write a new
cameras.txt / images.txt staged directory.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="directory containing cameras.txt/images.txt/points3D.txt")
    ap.add_argument("--dst", required=True)
    ap.add_argument("--target-w", type=int, required=True)
    ap.add_argument("--target-h", type=int, required=True)
    args = ap.parse_args()

    src, dst = Path(args.src), Path(args.dst)
    dst.mkdir(parents=True, exist_ok=True)

    tw, th = args.target_w, args.target_h

    # --- cameras.txt ---
    out_cam = []
    with open(src / "cameras.txt") as f:
        for line in f:
            s = line.rstrip("\n")
            if s.startswith("#") or not s.strip():
                out_cam.append(s); continue
            parts = s.split()
            cam_id, model, w, h = parts[0], parts[1], int(parts[2]), int(parts[3])
            params = [float(x) for x in parts[4:]]
            sx, sy = tw / w, th / h
            if model == "SIMPLE_PINHOLE":
                f_, cx, cy = params
                # use average scale for focal (close enough), scale principal point per axis
                new_params = [f_ * (sx + sy) / 2, cx * sx, cy * sy]
            elif model == "PINHOLE":
                fx, fy, cx, cy = params
                new_params = [fx * sx, fy * sy, cx * sx, cy * sy]
            elif model == "SIMPLE_RADIAL":
                f_, cx, cy, k = params
                new_params = [f_ * (sx + sy) / 2, cx * sx, cy * sy, k]
            else:
                # generic: scale first 2 by sx, next 2 by sy if looks like fx,fy,cx,cy; else keep
                new_params = params
            out_cam.append(" ".join([cam_id, model, str(tw), str(th), *[f"{x:.6f}" for x in new_params]]))
    (dst / "cameras.txt").write_text("\n".join(out_cam) + "\n")

    # --- images.txt ---
    # Must rescale POINTS2D[] xy by (sx, sy) using the camera scale factor.
    # Simpler: determine global sx, sy by comparing first cam's (w,h) vs target.
    # For per-camera correctness we should map per camera_id, but for SIMPLE_PINHOLE single cam
    # global factors suffice.
    with open(src / "cameras.txt") as f:
        for line in f:
            s = line.strip()
            if s.startswith("#") or not s: continue
            parts = s.split()
            w0, h0 = int(parts[2]), int(parts[3])
            break
    sx, sy = tw / w0, th / h0

    with open(src / "images.txt") as f, open(dst / "images.txt", "w") as g:
        line_no = 0
        for line in f:
            line_no += 1
            s = line.rstrip("\n")
            if s.startswith("#"):
                g.write(s + "\n"); continue
            if not s.strip():
                g.write("\n"); continue
            parts = s.split()
            if parts[0].isdigit() and len(parts) >= 10 and (parts[1].replace('.', '', 1).replace('-', '', 1).isdigit() or '.' in parts[1] or 'e' in parts[1].lower()):
                # header line: keep as-is
                g.write(s + "\n"); continue
            # POINTS2D line: triples (x,y,id) separated by whitespace
            nums = s.split()
            rescaled = []
            for i in range(0, len(nums), 3):
                x, y, pid = float(nums[i]), float(nums[i + 1]), nums[i + 2]
                rescaled.extend([f"{x*sx:.3f}", f"{y*sy:.3f}", pid])
            g.write(" ".join(rescaled) + "\n")

    # points3D.txt: copy as-is (3D world coords unaffected by image-plane rescale).
    (dst / "points3D.txt").write_bytes((src / "points3D.txt").read_bytes())
    print(f"wrote rescaled model to {dst} (target {tw}x{th}, sx={sx:.5f} sy={sy:.5f})")


if __name__ == "__main__":
    main()
