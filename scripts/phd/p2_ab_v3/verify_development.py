"""Verify immutable v2 evidence and collect exact v3 development provenance."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", default="/artifacts/JointBuildGS")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    old = json.loads(Path("artifacts/manifests/phd/p2_ab_v2/technical_result_manifest_v2.json").read_text())
    source_checks = {p: sha(p) == value for p, value in old["source_sha256"].items()}
    receipt_checks = {name: sha(Path(args.artifact_root) / row["artifact_relative_path"]) == row["sha256"]
                      for name, row in old["promoted_results"].items()}
    original_design = "docs/experiments/phd/p2_ab_v3/00_CONTRIBUTION_AND_METHOD_DESIGN_ko_v3.md"
    design_check = sha(original_design) == "716fbe24c402e1cecde70435cae47bccd15fc230977804ee8c85bd727c62f1ac"
    if not all(source_checks.values()) or not all(receipt_checks.values()) or not design_check:
        raise AssertionError("protected evidence changed")
    paths = []
    for directory in ("src", "scripts", "configs", "docs/experiments"):
        root = Path(directory) / "phd/p2_ab_v3"
        paths.extend(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    paths.extend(Path("tests/phd").glob("test_p2_ab_v3_*.py"))
    links = 0
    for path in paths:
        content = path.read_text()
        if path.suffix == ".py":
            ast.parse(content, filename=str(path))
        elif path.suffix == ".json":
            json.loads(content)
        if any(line.rstrip() != line for line in content.splitlines()):
            raise ValueError(f"trailing whitespace: {path}")
        if content and not content.endswith("\n"):
            raise ValueError(f"missing final newline: {path}")
        if path.suffix == ".md":
            for target in re.findall(r"\]\(([^)]+)\)", content):
                if "://" not in target and not target.startswith("#"):
                    resolved = path.parent / target.split("#")[0]
                    if not resolved.exists():
                        raise ValueError(f"broken link: {path}: {target}")
                    links += 1
    test = subprocess.run(["python", "-m", "unittest", "discover", "-s", "tests/phd",
                           "-p", "test_p2_ab_v3_*.py"], capture_output=True, text=True)
    print(test.stdout + test.stderr)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "tests.log").write_text(test.stdout + test.stderr)
    result = dict(status="PASS" if test.returncode == 0 else "FAIL", scientific_verdict=None,
        protected_v2_source_files=len(source_checks), protected_v2_receipts=len(receipt_checks),
        protected_v3_original_design_unchanged=design_check, validated_local_links=links,
        source_sha256={str(p): sha(p) for p in sorted(paths)}, test_exit_code=test.returncode,
        test_command="python -m unittest discover -s tests/phd -p test_p2_ab_v3_*.py",
        test_log_sha256=sha(output / "tests.log"), python=platform.python_version(),
        git_head=os.environ.get("JBGS_SOURCE_GIT_HEAD"),
        container_image=os.environ.get("JBGS_CONTAINER_IMAGE_ID"))
    (output / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    if test.returncode:
        raise RuntimeError("v3 test suite failed; log preserved")
    print(json.dumps({k: v for k, v in result.items() if k != "source_sha256"}))


if __name__ == "__main__":
    main()
