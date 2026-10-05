"""Verify the completed SRDM evidence package without changing scientific data."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        for name in ("href", "src"):
            if name in attrs:
                self.links.append(attrs[name])


def verify(task):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Run artifact verification in Docker")
    read = lambda relative: json.loads((task / relative).read_text())
    seal, evaluation, paired, report = [read(name) for name in (
        "run/CANDIDATE_SEAL.json", "evaluation/evaluation.json", "paired/paired_analysis.json", "report/report_receipt.json")]
    if any(data.get("scientific_verdict", "missing") is not None for data in (seal, evaluation, paired, report)):
        raise ValueError("Unexpected scientific verdict")
    if seal["reference_accessed"] or not evaluation["reference_accessed"]:
        raise ValueError("Reference boundary receipt differs")
    if evaluation["gate"]["outputs"] != seal["outputs"]:
        raise ValueError("Evaluation uses different candidates")
    for base, expected in ((task / "run", seal["outputs"]), (task / "report", report["outputs"])):
        for relative, digest in expected.items():
            if sha(base / relative) != digest:
                raise ValueError(f"Output changed: {base / relative}")
    if report["evaluation_sha256"] != sha(task / "evaluation/evaluation.json"):
        raise ValueError("Report uses different evaluation")
    parser = Links()
    parser.feed((task / "report/index.html").read_text())
    report_root = (task / "report").resolve()
    for link in parser.links:
        value = urlsplit(link)
        if value.scheme or value.netloc:
            raise ValueError(f"Unexpected non-portable link: {link}")
        if value.path:
            target = (report_root / unquote(value.path)).resolve()
            if report_root not in target.parents or not target.is_file():
                raise ValueError(f"Broken or escaping report link: {link}")
        elif value.fragment and value.fragment not in parser.ids:
            raise ValueError(f"Broken report fragment: {link}")
    results = list((task / "run").glob("P*/SRDM_*/result.npz"))
    figures = list((task / "report").rglob("*.png"))
    if len(results) != 9 or len(figures) != 27 or len(evaluation["regions"]) != 3:
        raise ValueError("Incomplete three-region evidence package")
    receipt = {"task_id": "PHD-SRDM-P1P2P3-v1", "status": "TECHNICAL_EXECUTION_AND_ANALYSIS_COMPLETE",
        "created_utc": datetime.now(timezone.utc).isoformat(), "scientific_verdict": None,
        "candidate_files_verified": len(seal["outputs"]), "result_arrays": len(results),
        "report_files_verified": len(report["outputs"]), "figures": len(figures),
        "portable_report_links_checked": len(parser.links), "evaluation_regions": 3,
        "gs_training_performed": False, "gs_after_redecision_performed": False,
        "method_status": "paper reimplementation with documented departures; one stereo pair per development crop",
        "hashes": {name: sha(task / name) for name in ("run/CANDIDATE_SEAL.json", "evaluation/evaluation.json",
            "paired/paired_analysis.json", "report/report_receipt.json", "preservation/PRESERVATION_CHECK.json")},
        "verifier_sha256": sha(__file__)}
    with (task / "FINAL_TECHNICAL_RECEIPT.json").open("x") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-root", type=Path, required=True)
    verify(parser.parse_args().task_root)
