#!/usr/bin/env python3
"""Build/deploy the S3 verification static viewers into the shared bundle root.

Currently page 1 (평면 가설, viewer_p1) only; later pages plug into PAGES.
NOT OFFICIAL · scientific_verdict: null.

Reads configs/phd/s3_verify_v1/s1_bundle_v1.json (contract defaults when the
file does not exist yet), then, inside the bundle root
(phase-payloads/phd/PHD-S3-VERIFY-PAGES-v1/):
  1. viewer_p1/            index.html + app.js copied from the repo,
                           three.module.min.js copied from the existing
                           journal1 phase-B payload (build_arrgs_viewer.py:18-19
                           source path reused) — CDN 금지.
  2. viewer_p1/manifest.json   run list + references only (geometry never
                           inlined — the 243 MB blank-viewer lesson).
  3. viewer_p1/web_receipt_v1.json   input sha256 + counts + serve note.

Usage:
  python scripts/phd/s3_verify_v1/build_verify_pages.py
  python scripts/phd/s3_verify_v1/build_verify_pages.py --config configs/phd/s3_verify_v1/s1_bundle_v1.json

Serve (root = bundle root, the parent of viewer_p1/, so ../runs/ resolves):
  cd <bundle_root> && python3 -m http.server 8885 --bind 0.0.0.0
  -> http://<host>:8885/viewer_p1/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PAGE1_SRC = Path(__file__).resolve().parent / "viewer_p1"
ART_HOST = Path("/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts")
CONTAINER_PREFIX = "/artifacts/JointBuildGS"
DEFAULT_CONFIG_PATH = REPO / "configs/phd/s3_verify_v1/s1_bundle_v1.json"

# Contract defaults (phd_s3_verify_s1_bundle_v1) — used only for the keys this
# builder needs when the shared config does not exist yet. The writer-owned
# keys (inlier tau, thinning, synth_seed, prereg values) are not invented here;
# the viewer reads them from each run's own manifest.json.
CONTRACT_DEFAULTS = {
    "out_root": CONTAINER_PREFIX + "/phase-payloads/phd/PHD-S3-VERIFY-PAGES-v1",
    "runs": ["B022", "B173", "B036", "SYNTH_GABLE"],
    "viewer": {
        "three_module_src": (CONTAINER_PREFIX
                             + "/phase-payloads/p2/journal1_phase_b_v1/"
                               "P2-JOURNAL1-PHASE-B-v1/viewer/three.module.min.js"),
        "port": 8885,
        "serve_note": ("정적 서빙 루트 = PHD-S3-VERIFY-PAGES-v1/ (viewer_p1의 부모)"
                       " — 뷰어는 ../runs/ 상대경로. 포트 8885."
                       " NOT OFFICIAL · scientific_verdict: null"),
    },
}

S1_RUN_FILES = ["manifest.json", "s1_points.ply", "s1_planes.json",
                "s1_orphans.json", "s1_view.json"]
S1_SCHEMA = "phd_s3_verify_s1_bundle_v1"


def resolve_path(p: str | Path) -> Path:
    """Map the container artifact prefix to the local sibling checkout when the
    container mount root itself is absent (builder runs on either host). The
    decision keys off the mount ROOT, not the full path — the target dir may
    legitimately not exist yet (first build creates it)."""
    p = str(p)
    if p.startswith(CONTAINER_PREFIX) and not Path(CONTAINER_PREFIX).is_dir():
        return ART_HOST / p[len(CONTAINER_PREFIX):].lstrip("/")
    return Path(p)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_config(path: Path) -> tuple[dict, Path | None]:
    cfg = json.loads(json.dumps(CONTRACT_DEFAULTS))  # deep copy
    if path.is_file():
        user = json.load(open(path))
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
        return cfg, path
    print(f"[build] config 없음: {path} — 계약 기본값 사용")
    return cfg, None


def scan_runs(runs_root: Path, ordered_names: list[str]) -> list[dict]:
    """Run list + references only. Small scalars from each run manifest are
    copied for dropdown labels; geometry stays behind relative-path fetches."""
    found: dict[str, dict] = {}
    if runs_root.is_dir():
        for run_dir in sorted(runs_root.iterdir()):
            mp = run_dir / "manifest.json"
            if not mp.is_file():
                continue
            try:
                m = json.load(open(mp))
            except Exception as e:
                print(f"[build] skip {run_dir.name}: manifest 파싱 실패 ({e})")
                continue
            if m.get("schema") != S1_SCHEMA:
                print(f"[build] skip {run_dir.name}: schema={m.get('schema')!r}")
                continue
            files = {fn: (run_dir / fn).is_file() for fn in S1_RUN_FILES}
            found[run_dir.name] = {
                "name": run_dir.name,
                "dir": f"runs/{run_dir.name}",
                "schema": m.get("schema"),
                "stage": m.get("stage"),
                "s1_mode": m.get("s1_mode"),
                "dataset": m.get("dataset"),
                "crs": m.get("crs"),
                "counts": m.get("counts"),
                "prereg": m.get("prereg"),
                "files": files,
            }
    ordered = [found.pop(n) for n in ordered_names if n in found]
    ordered += [found[n] for n in sorted(found)]  # extras beyond the config list
    return ordered


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH,
                    help="공유 config (기본: configs/phd/s3_verify_v1/s1_bundle_v1.json)")
    args = ap.parse_args()

    cfg, cfg_path = load_config(args.config)
    viewer_cfg = cfg.get("viewer", {})
    port = viewer_cfg.get("port", 8885)
    serve_note = viewer_cfg.get("serve_note",
                                CONTRACT_DEFAULTS["viewer"]["serve_note"])
    out_root = resolve_path(cfg["out_root"])
    viewer_dir = out_root / "viewer_p1"
    viewer_dir.mkdir(parents=True, exist_ok=True)

    # 1) app files — repo copies + vendored three.js (CDN 금지)
    inputs: dict[str, dict] = {}
    for fn in ("index.html", "app.js"):
        src = PAGE1_SRC / fn
        shutil.copy2(src, viewer_dir / fn)
        inputs[f"repo:scripts/phd/s3_verify_v1/viewer_p1/{fn}"] = {
            "sha256": sha256_file(src), "bytes": src.stat().st_size}
    three_src = resolve_path(viewer_cfg.get(
        "three_module_src", CONTRACT_DEFAULTS["viewer"]["three_module_src"]))
    three_dst = viewer_dir / "three.module.min.js"
    if three_src.is_file():
        if not three_dst.is_file():
            shutil.copy2(three_src, three_dst)
        three_dst.chmod(0o644)  # source copy is 0600 — keep it servable
        inputs["three.module.min.js"] = {
            "src": str(three_src), "sha256": sha256_file(three_dst),
            "bytes": three_dst.stat().st_size}
    elif not three_dst.is_file():
        print(f"[build] 경고: three.module.min.js 원본 없음: {three_src} — 뷰어 동작 불가")
    if cfg_path is not None:
        inputs[f"config:{cfg_path.relative_to(REPO) if cfg_path.is_relative_to(REPO) else cfg_path}"] = {
            "sha256": sha256_file(cfg_path), "bytes": cfg_path.stat().st_size}

    # 2) run scan -> viewer manifest (참조만)
    runs = scan_runs(out_root / "runs", list(cfg.get("runs", [])))
    if not runs:
        print(f"[build] 경고: {out_root / 'runs'} 에 s1 번들 런 0개 — "
              "writer 실행 후 이 스크립트를 재실행하면 manifest가 갱신된다.")
    manifest = {
        "schema": "phd_s3_verify_viewer_p1_manifest_v1",
        "page": "p1_plane_hypothesis",
        "note": "S3 검증 페이지 1 — NOT OFFICIAL · scientific_verdict: null",
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "port": port,
        "serve_note": serve_note,
        "runs": runs,
        "not_official": True,
        "scientific_verdict": None,
    }
    json.dump(manifest, open(viewer_dir / "manifest.json", "w"),
              ensure_ascii=False, indent=1)

    # 3) web receipt — input sha256 + counts + serve note
    run_hashes: dict[str, dict] = {}
    agg = {"runs": len(runs), "planes": 0, "points_total": 0, "orphans": 0}
    for r in runs:
        rd = out_root / r["dir"]
        entry = {}
        for fn in S1_RUN_FILES:
            fp = rd / fn
            if fp.is_file():
                entry[fn] = {"sha256": sha256_file(fp), "bytes": fp.stat().st_size}
        run_hashes[r["name"]] = entry
        c = r.get("counts") or {}
        for k in ("planes", "points_total", "orphans"):
            agg[k] += int(c.get(k) or 0)
    serve_cmd = f"cd {out_root} && python3 -m http.server {port} --bind 0.0.0.0"
    receipt = {
        "schema": "phd_s3_verify_web_receipt_v1",
        "task": "PHD-S3-VERIFY-PAGES-v1 / viewer_p1 (페이지 1 — 평면 가설)",
        "built_at": manifest["built_at"],
        "config_used": str(cfg_path) if cfg_path else "contract-defaults(config 파일 없음)",
        "inputs": inputs,
        "runs": run_hashes,
        "counts": agg,
        "serve_note": serve_note,
        "serve_cmd": serve_cmd,
        "url": f"http://<host>:{port}/viewer_p1/",
        "not_official": True,
        "scientific_verdict": None,
    }
    json.dump(receipt, open(viewer_dir / "web_receipt_v1.json", "w"),
              ensure_ascii=False, indent=1)

    print(f"viewer built: {viewer_dir}  runs={len(runs)}"
          f" ({', '.join(r['name'] for r in runs) or '없음'})")
    print(f"serve:  {serve_cmd}")
    print(f"open:   http://<host>:{port}/viewer_p1/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
