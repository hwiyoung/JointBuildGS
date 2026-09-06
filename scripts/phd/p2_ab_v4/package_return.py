"""Check new outputs and preserved old work, then freeze this bounded return."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", default="/artifacts/JointBuildGS")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    artifact = Path(args.artifact_root)
    base = artifact / "phase-payloads/phd/p2_ab_v4"
    preserved = {}
    for version in ("v2", "v3"):
        filename = "technical_result_manifest_v2.json" if version == "v2" else "technical_development_manifest_v1.json"
        manifest = json.loads((Path("artifacts/manifests/phd/p2_ab_" + version) / filename).read_text())
        source = manifest["source_sha256"]
        for path, expected in source.items():
            if sha(path) != expected:
                raise ValueError("preserved source changed: " + path)
        receipts = manifest["promoted_results"] if version == "v2" else manifest["receipts"]
        for row in receipts.values():
            if sha(artifact / row["artifact_relative_path"]) != row["sha256"]:
                raise ValueError("preserved receipt changed")
        preserved[version] = dict(source_files=len(source), receipts=len(receipts), status="PASS")
    files = []
    for folder in ("src/phd/p2_ab_v4", "scripts/phd/p2_ab_v4", "configs/phd/p2_ab_v4",
                   "docs/experiments/phd/p2_ab_v4", "src/apps/p2_ab_inspector_v4"):
        files.extend(p for p in Path(folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    files.extend(Path("tests/phd").glob("test_p2_ab_v4_*.py"))
    for path in files:
        content = path.read_text()
        if path.suffix == ".py": ast.parse(content, filename=str(path))
        if path.suffix == ".json": json.loads(content)
        if content and not content.endswith("\n"): raise ValueError("missing newline: " + str(path))
        if any(line != line.rstrip() for line in content.splitlines()): raise ValueError("trailing whitespace: " + str(path))
        if path.suffix == ".md":
            for target in re.findall(r"\]\(([^)]+)\)", content):
                if "://" not in target and not target.startswith("#"):
                    if not (path.parent / target.split("#")[0]).exists(): raise ValueError("broken local link: " + target)
    locations = {
        "MVS_B": base / "PHD-P2-AB-V4-B-MVS-APPEARANCE-v1/result.json",
        "viewer_common_pixels": base / "PHD-P2-AB-V4-QUALITATIVE-v1/viewer/technical_receipt.json",
        "browser_QA": base / "PHD-P2-AB-V4-BROWSER-QA-v1/browser_qa.json",
        "unit_tests": base / "PHD-P2-AB-V4-UNIT-TESTS-v1/capture.json",
    }
    results = {name: json.loads(p.read_text()) for name, p in locations.items()}
    if results["MVS_B"]["status"] != "COMPLETED_DIAGNOSTIC": raise ValueError("MVS run incomplete")
    for name in ("browser_QA", "unit_tests"):
        if results[name]["status"] != "PASS": raise ValueError(name + " failed")
    for arm in results["MVS_B"]["arms"]:
        if not all(arm["checks"].values()): raise ValueError("MVS geometry check failed")
    for name in ("MVS_B", "viewer_common_pixels"):
        result = results[name]
        for key in ("source_sha256", "source_hashes", "input_sha256", "input_hashes"):
            for p, expected in result.get(key, {}).items():
                if sha(p) != expected: raise ValueError("executed input/source changed: " + p)
    viewer = locations["viewer_common_pixels"].parent
    for p, expected in results["viewer_common_pixels"]["output_sha256"].items():
        if sha(viewer / p) != expected: raise ValueError("viewer output changed: " + p)
    if sha(base / "PHD-P2-AB-V4-BROWSER-QA-v1/browser_qa_source.mjs") != sha("scripts/phd/p2_ab_v4/browser_qa.mjs"):
        raise ValueError("browser test driver changed")
    for row in results["browser_QA"]["screenshots"]:
        if sha(base / "PHD-P2-AB-V4-BROWSER-QA-v1" / row["filename"]) != row["sha256"]:
            raise ValueError("browser screenshot changed")
    data = json.loads((viewer / "data.json").read_text())
    count = sum(row["common_pixels"] for row in data["views"])
    if count != 5150892 or len(data["views"]) != 11 or len(data["models"]) != 10:
        raise ValueError("unexpected comparison domain")
    for model in data["models"]:
        identifier = model["id"]
        metrics = [row["metrics"][identifier] for row in data["views"]]
        for row, metric in zip(data["views"], metrics):
            if metric["pixels"] != row["common_pixels"]: raise ValueError("method-dependent denominator")
        mae = sum(m["absolute_rgb_sum"] for m in metrics) / (3 * count)
        psnr = -10 * math.log10(sum(m["squared_rgb_sum"] for m in metrics) / (3 * count))
        if abs(mae - data["summary"][identifier]["mae"]) > 1e-12 or abs(psnr - data["summary"][identifier]["psnr_db"]) > 1e-12:
            raise ValueError("common summary arithmetic")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    source_hashes = {str(p): sha(p) for p in sorted(files)}
    for p in files:
        dest = output / "source_snapshot" / p
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
    receipt = dict(schema="jointbuildgs.phd.p2_ab_v4.technical_return.v1",
        task_id="PHD-P2-AB-V4-MVS-INITIALIZATION-AND-VISUAL-RETURN-v1",
        status="MVS_APPEARANCE_AND_QUALITATIVE_VALIDATION_COMPLETE", scientific_verdict=None,
        utc=datetime.now(timezone.utc).isoformat(), git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD"),
        container_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID"), source_sha256=source_hashes,
        receipts={name: dict(artifact_relative_path=str(p.relative_to(artifact)), sha256=sha(p)) for name, p in locations.items()},
        preserved=preserved, browser_checks=len(results["browser_QA"]["checks"]), unit_tests=5,
        viewer_url="http://127.0.0.1:8895/PHD-P2-AB-V4-QUALITATIVE-v1/viewer/?view=333",
        common_pixels=count, comparison_summary=data["summary"],
        limitations=["A scalar numbers are synthetic, not P2 decisions",
                     "MVS initialization is the user-directed development baseline, not an inferred A action",
                     "Geometry remains fixed; improvements are appearance, not new geometry/detail recovery",
                     "P2/its 11 evaluation views are development observations, not independent confirmation"])
    (output / "technical_return_manifest_v1.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: receipt[k] for k in ("status", "preserved", "browser_checks", "unit_tests", "common_pixels")}))


if __name__ == "__main__":
    main()
