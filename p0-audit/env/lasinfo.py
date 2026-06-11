#!/opt/conda/bin/python
"""Small lasinfo-compatible report for P0 containers.

The P0 tools image already carries laspy/lazrs. This wrapper provides the
`lasinfo` command name needed by the pipeline without adding a second LAZ stack.
"""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
from pathlib import Path

import laspy


VERSION = "lasinfo laspy-backed 0.1"


def fmt_xyz(values: tuple[float, float, float] | list[float]) -> str:
    return f"{values[0]:.3f} {values[1]:.3f} {values[2]:.3f}"


def report(path: Path) -> str:
    with laspy.open(path) as las_file:
        header = las_file.header
        point_count = int(header.point_count)
        mins = header.mins
        maxs = header.maxs
        scales = header.scales
        offsets = header.offsets
        point_format = header.point_format
        version = header.version
        try:
            crs = header.parse_crs()
            crs_text = crs.to_string() if crs else "not set"
        except Exception as exc:  # pragma: no cover - defensive report path
            crs_text = f"unreadable ({exc})"

    width = maxs[0] - mins[0]
    depth = maxs[1] - mins[1]
    area = width * depth
    density = point_count / area if area > 0 else 0.0

    return "\n".join(
        [
            f"{VERSION}",
            f"file name: {path}",
            f"LAS version: {version}",
            f"point data format: {point_format.id}",
            f"number of point records: {point_count}",
            f"min x y z: {fmt_xyz(mins)}",
            f"max x y z: {fmt_xyz(maxs)}",
            f"bounding box width x depth: {width:.3f} {depth:.3f}",
            f"bounding box area: {area:.3f} square meters",
            f"point density: {density:.6f} points per square meter",
            f"scale factor x y z: {fmt_xyz(scales)}",
            f"offset x y z: {fmt_xyz(offsets)}",
            f"coordinate reference system: {crs_text}",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Print LAS/LAZ summary statistics.")
    parser.add_argument("path", nargs="?", help="LAS/LAZ file to inspect")
    parser.add_argument("--version", action="store_true", help="print wrapper version")
    args = parser.parse_args()

    if args.version:
        try:
            pyproj_version = metadata.version("pyproj")
        except metadata.PackageNotFoundError:
            pyproj_version = "not installed"
        print(f"{VERSION} (laspy {laspy.__version__}, pyproj {pyproj_version})")
        return 0

    if not args.path:
        parser.error("path is required unless --version is used")

    print(report(Path(args.path)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
