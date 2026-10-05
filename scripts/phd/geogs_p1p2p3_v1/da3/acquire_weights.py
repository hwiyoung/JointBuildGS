"""Acquire a pinned official DA3 model into new external task storage only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.request

MODEL = "depth-anything/DA3NESTED-GIANT-LARGE"
REVISION = "8615eefb62f2db4f8d6ebaa59160086981672829"
WEIGHT_SHA256 = "8899faf998dedbc230261ab736fa57015280727399429122d44d4f9e7aac2ddd"
WEIGHT_BYTES = 6759558100
SOURCE_COMMIT = "3d835ec1a5802d64a8b8b15f817a1ab54809bfe4"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, dest: Path, expected_size: int, expected_sha: str | None):
    if dest.exists():
        digest = sha(dest)
        if dest.stat().st_size != expected_size or (expected_sha and digest != expected_sha):
            raise ValueError(f"Existing target identity mismatch: {dest}")
        return digest
    part = dest.with_name(dest.name + ".part")
    for attempt in range(1, 6):
        offset = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": "JointBuildGS-DA3-pinned-acquisition/1"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                if offset and (response.status != 206 or not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-")):
                    raise RuntimeError("Server did not honor exact partial-file resume")
                with part.open("ab" if offset else "xb") as out:
                    last_report = time.monotonic()
                    while True:
                        block = response.read(8 << 20)
                        if not block:
                            break
                        out.write(block)
                        offset += len(block)
                        if time.monotonic() - last_report > 30:
                            print(json.dumps({"file": dest.name, "bytes": offset, "total": expected_size}), flush=True)
                            last_report = time.monotonic()
            if part.stat().st_size != expected_size:
                raise RuntimeError(f"Size mismatch: {part.stat().st_size} != {expected_size}")
            digest = sha(part)
            if expected_sha and digest != expected_sha:
                raise ValueError("Downloaded bytes differ from publisher LFS SHA256")
            part.rename(dest)
            return digest
        except Exception as error:
            print(json.dumps({"attempt": attempt, "file": dest.name, "error": str(error)}), flush=True)
            if attempt == 5 or isinstance(error, ValueError):
                raise
            time.sleep(min(attempt * 3, 15))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        raise FileExistsError(args.receipt)
    commit = subprocess.check_output(["git", "-c", f"safe.directory={args.source_root}",
                                      "-C", str(args.source_root), "rev-parse", "HEAD"], text=True).strip()
    if commit != SOURCE_COMMIT:
        raise ValueError(f"Official source commit differs: {commit}")
    args.weights_root.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    tree_url = f"https://huggingface.co/api/models/{MODEL}/tree/{REVISION}?recursive=true"
    with urllib.request.urlopen(tree_url, timeout=90) as response:
        upstream = json.load(response)
    weight = next(row for row in upstream if row["path"] == "model.safetensors")
    if weight["lfs"]["oid"] != WEIGHT_SHA256 or weight["size"] != WEIGHT_BYTES:
        raise ValueError("Pinned model metadata changed")
    receipt = dict(task_id="PHD-GEOGS-P1P2P3-v1", scientific_verdict=None,
                   model=MODEL, model_revision=REVISION, official_tree_url=tree_url,
                   source_repository="https://github.com/ByteDance-Seed/Depth-Anything-3",
                   source_commit=SOURCE_COMMIT, source_files={}, files={}, upstream_tree=upstream,
                   reference_accessed=False, status="RUNNING", started_unix=time.time())
    for path in sorted(args.source_root.rglob("*")):
        if path.is_file() and ".git" not in path.relative_to(args.source_root).parts:
            receipt["source_files"][str(path.relative_to(args.source_root))] = sha(path)
    try:
        for row in upstream:
            if row["type"] != "file" or "/" in row["path"]:
                continue
            name = row["path"]
            url = f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}?download=true"
            digest = download(url, args.weights_root / name, row["size"], row.get("lfs", {}).get("oid"))
            receipt["files"][name] = dict(bytes=row["size"], sha256=digest, url=url)
        receipt["status"] = "PASS_PINNED_OFFICIAL_SOURCE_AND_WEIGHTS"
    except Exception as error:
        receipt.update(status="FAILED_ACQUISITION", error=str(error))
        raise
    finally:
        receipt["ended_unix"] = time.time()
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
