"""Package the bounded v3 development results; no scientific verdict."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", default="/artifacts/JointBuildGS")
    parser.add_argument("--verification", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    base = Path(args.artifact_root) / "phase-payloads/phd/p2_ab_v3"
    locations = {
        "A_synthetic": base / "PHD-P2-AB-V3-A-JOINT-ERROR-PROBE-v2/receipt.json",
        "B_SH0": base / "PHD-P2-AB-V3-B-APPEARANCE-v1/result.json",
        "B_SH3": base / "PHD-P2-AB-V3-B-SH3-v1/result.json",
        "handoff_fixture": base / "PHD-P2-AB-V3-HANDOFF-v1/return/receipt.json",
        "verification": Path(args.verification),
    }
    receipts = {name: json.loads(path.read_text()) for name, path in locations.items()}
    verification = receipts["verification"]
    if verification["status"] != "PASS":
        raise ValueError("verification did not pass")
    source_hashes = verification["source_sha256"]
    for path, expected in source_hashes.items():
        if sha(path) != expected:
            raise ValueError(f"source changed after verification: {path}")
    run_source_checks = {}
    for name, receipt in receipts.items():
        if receipt.get("scientific_verdict") is not None:
            raise ValueError("unexpected scientific verdict")
        for path, expected in receipt.get("source_hashes", receipt.get("source_sha256", {})).items():
            checked = Path(path)
            if checked.is_absolute() and str(checked).startswith("/workspace/JointBuildGS/"):
                checked = Path(str(checked).removeprefix("/workspace/JointBuildGS/"))
            run_source_checks[name + ":" + path] = sha(checked) == expected
    if not all(run_source_checks.values()):
        raise ValueError("executed source and packaged source differ")
    a = receipts["A_synthetic"]
    b0, b3 = receipts["B_SH0"], receipts["B_SH3"]
    for b in (b0, b3):
        if b["status"] != "COMPLETED_DIAGNOSTIC":
            raise ValueError("B did not complete")
        if not all(all(arm["checks"].values()) for arm in b["arms"]):
            raise ValueError("B mechanism verification failed")
    initial_images_equal = {}
    b0root, b3root = locations["B_SH0"].parent, locations["B_SH3"].parent
    views0 = b0["arms"][0]["initial"]["metrics"]
    views3 = b3["arms"][0]["initial"]["metrics"]
    if [v["image_id"] for v in views0] != [v["image_id"] for v in views3]:
        raise ValueError("SH comparison views differ")
    for row in views0:
        for prefix, suffix in (("rgb", "png"), ("target", "png"), ("support", "png"),
                               ("quality", "npy"), ("depth", "npy"), ("geometry_mass", "npy")):
            filename = f"{prefix}_{row['image_id']}.{suffix}"
            initial_images_equal[filename] = sha(b0root / "initial" / filename) == sha(b3root / "initial" / filename)
    if not all(initial_images_equal.values()):
        raise ValueError("SH comparison initial images/support/geometry differ")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    for path in source_hashes:
        target = output / "source_snapshot" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    record = dict(schema="jointbuildgs.phd.p2_ab_v3.development.v1",
        task_id="PHD-P2-AB-V3-CONCRETE-METHODS-v1", status="DEVELOPMENT_COMPONENTS_VERIFIED",
        scientific_verdict=None, git_head=verification["git_head"], container_image=verification["container_image"],
        source_sha256=source_hashes,
        receipts={name: dict(artifact_relative_path=str(path.relative_to(args.artifact_root)), sha256=sha(path))
                  for name, path in locations.items()},
        all_executed_sources_match=True, all_SH0_SH3_initial_images_masks_and_depths_match=True,
        cross_representation_initial_checks=initial_images_equal,
        A_designed_case_summary=a["summary"],
        B_summary={name: [{"arm": arm["arm"], "steps": arm["steps"], "checks": arm["checks"],
                    **{k: arm["final"][k] for k in ("fixed_support_pixel_weighted_mae", "mean_view_mae", "mean_view_ssim")}}
                          for arm in receipts[name]["arms"]] for name in ("B_SH0", "B_SH3")},
        preservation=dict(v2_source_files=verification["protected_v2_source_files"],
                          v2_receipts=verification["protected_v2_receipts"], original_v3_design_unchanged=True),
        limitations=["A uses supplied synthetic scalar constraints; no calibrated real-P2 A decisions",
                     "Handoff uses an explicit same-P2 source-routing fixture, not inferred decisions",
                     "B uses fixed ALS diagnostic geometry; no actual A handoff consumed",
                     "SH appearance and weight probes do not execute surface binding or geometry detail recovery",
                     "No strong published baseline reproduction or scientific/generalization verdict"])
    (output / "technical_development_manifest_v1.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(dict(status=record["status"], source_count=len(source_hashes), receipt_count=len(locations))))


if __name__ == "__main__":
    main()
