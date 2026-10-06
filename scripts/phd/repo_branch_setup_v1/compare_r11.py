"""PHD-REPO-BRANCH-SETUP-v1 3.5: the fork r11 three ways (jointbuildgs:dev, stdlib).

  python compare_r11.py

  /v/rebuild/sources/GeoGS-conf-guided-v1-r11   rebuilt now by build_fork_r11.py of this repository from the r10 sources (read-only)
  /orig_sources/GeoGS-conf-guided-v1-r11        the original r11 of PHD-MAIN-PREP-DISCARD-RULE-v1 (read-only)
  /repo/src/phd/forks/GeoGS-conf-guided-v1-r11  the copy committed in this repository (no submodules/)
  /orig_prov/build_report_r11.json, /v/rebuild/provenance/build_report_r11.json
Every file by sha256: rebuilt = original (all files), committed = original without submodules/; the two build reports agree on
the changed files, the removed files and the shared module v5. Writes /v/rebuild/compare_r11.json. scientific_verdict: null."""
import hashlib
import json
from pathlib import Path

REBUILT = Path("/v/rebuild/sources/GeoGS-conf-guided-v1-r11")
ORIG = Path("/orig_sources/GeoGS-conf-guided-v1-r11")
COMMITTED = Path("/repo/src/phd/forks/GeoGS-conf-guided-v1-r11")


def tree(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def diff(a, b):
    return dict(only_first=sorted(set(a) - set(b)), only_second=sorted(set(b) - set(a)),
                differing=sorted(k for k in set(a) & set(b) if a[k] != b[k]))


def main():
    r, o, c = tree(REBUILT), tree(ORIG), tree(COMMITTED)
    o_nosub = {k: v for k, v in o.items() if not k.startswith("submodules/")}
    d_ro, d_co = diff(r, o), diff(c, o_nosub)
    ra = json.loads(Path("/v/rebuild/provenance/build_report_r11.json").read_text())
    oa = json.loads(Path("/orig_prov/build_report_r11.json").read_text())
    rep = {k: ra[k] == oa[k] for k in ("changed_or_added", "removed", "shared_module_v5", "only_expected_changes")}
    out = dict(
        rebuilt_vs_original=dict(files=[len(r), len(o)], equal=not any(d_ro.values()), **d_ro),
        committed_vs_original_without_submodules=dict(files=[len(c), len(o_nosub)], equal=not any(d_co.values()), **d_co),
        build_reports_agree=rep, rebuilt_only_expected_changes=ra["only_expected_changes"],
        repo_commit_of_rebuild=ra["repo_commit"], scientific_verdict=None)
    Path("/v/rebuild/compare_r11.json").write_text(json.dumps(out, indent=1))
    ok = out["rebuilt_vs_original"]["equal"] and out["committed_vs_original_without_submodules"]["equal"] and all(rep.values())
    print("R11 EQUAL" if ok else "R11 DIFFERENCES", "rebuilt", len(r), "original", len(o), "committed", len(c),
          "reports agree", rep)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
