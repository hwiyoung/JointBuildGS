"""Draw saved transition codes with explicit margins; no distance/classification recomputation."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Docker is required")
    receipt_path = args.source / "receipt.json"
    original = json.loads(receipt_path.read_text())
    if original["status"] != "PASS_REFERENCE_PROXIMITY_TRANSITIONS" or original["comparison_count"] != 6:
        raise ValueError("Completed numerical comparison required")
    outputs = {row["path"]: row for row in original["outputs"]}
    receipt = dict(schema="GEOGS_PREFIX8000_SUPPORT_FIGURES_v2", scientific_verdict=None,
        status="RUNNING", started_unix=time.time(), command=sys.argv, script_sha256=digest(Path(__file__)),
        source_receipt_sha256=digest(receipt_path), source_numerical_outputs_modified=False,
        transition_classifications_recomputed=False, geometry_or_scoring_recomputed=False,
        previous_visual_qa=dict(status="PARTIAL_LABEL_CLIPPING", region="P2",
            observation="P2 figure lower X-axis label partly outside image boundary; numerical/map data remain valid",
            original_png="P2.transitions_0.5m.png", original_png_sha256=outputs["P2.transitions_0.5m.png"]["sha256"],
            preserved=True), inputs=[], outputs=[])
    try:
        for region in ("P1", "P2", "P3"):
            fig, axes = plt.subplots(1, 2, figsize=(12, 7))
            fig.subplots_adjust(left=0.07, right=0.98, bottom=0.1, top=0.82, wspace=0.2)
            for ax, kind in zip(axes, ("raw", "post")):
                name = region + ".anchor8000_to_sfm8000." + kind + ".npz"
                path = args.source / name
                if digest(path) != outputs[name]["sha256"]:
                    raise ValueError("Saved transition array changed")
                receipt["inputs"].append(outputs[name])
                with np.load(path, allow_pickle=False) as archive:
                    xyz = archive["reference_points"]
                    thresholds = archive["thresholds_m"]
                    codes = archive["status_codes"][int(np.flatnonzero(thresholds == 0.5)[0])]
                    names = archive["status_code_names"]
                for code, color in ((3, "#bdbdbd"), (0, "#4477aa"), (1, "#228833"), (2, "#cc3311")):
                    mask = codes == code
                    ax.scatter(xyz[mask, 0], xyz[mask, 1], s=1, color=color, linewidths=0,
                        label=str(names[code]) + ": " + str(int(mask.sum())), rasterized=True)
                # Exact primary metric bounds were already checked and bound by the source comparison.
                comparison = next(row for row in original["comparisons"] if row["region"] == region and row["kind"] == kind)
                metric_record = comparison["inputs"][1]
                metric_path = Path("/task") / metric_record["path"]
                if digest(metric_path) != metric_record["sha256"]:
                    raise ValueError("Saved metric bounds changed")
                bounds = json.loads(metric_path.read_text())["bounds_half_open"]
                ax.set(xlim=bounds[0], ylim=bounds[1], xlabel="Scene X (m)", ylabel="Scene Y (m)")
                ax.set_title(kind + " triangle surface", fontsize=11, pad=10)
                ax.set_aspect("equal", adjustable="box")
                ax.legend(loc="upper left", fontsize=7, markerscale=4)
            fig.suptitle(region + " | Anchor8000 to SfM8000 | distance < 0.5 m\n"
                "Observed reference proximity only; vertically overlapping points may overlap in XY", fontsize=12, y=0.98)
            png = args.out / (region + ".transitions_0.5m.png")
            if png.exists():
                raise FileExistsError(png)
            fig.savefig(png, dpi=160, bbox_inches="tight", pad_inches=0.14)
            plt.close(fig)
            receipt["outputs"].append(dict(path=png.name, bytes=png.stat().st_size, sha256=digest(png)))
        for row in receipt["inputs"]:
            if digest(args.source / row["path"]) != row["sha256"]:
                raise ValueError("Numerical input changed during redraw")
        receipt["status"] = "PASS_SAVED_TRANSITION_FIGURES"
    except Exception as error:
        receipt.update(status="FAIL_SAVED_TRANSITION_FIGURES", error=str(error), error_type=type(error).__name__)
        raise
    finally:
        receipt["completed_unix"] = time.time()
        with (args.out / "receipt.json").open("x") as stream:
            json.dump(receipt, stream, indent=2, allow_nan=False)
            stream.write("\n")
    print(json.dumps(dict(status=receipt["status"], scientific_verdict=None)))


if __name__ == "__main__":
    main()
