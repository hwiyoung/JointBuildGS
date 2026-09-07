"""Freeze native GeoGS AlexNet/VGG LPIPS weights in a new external cache.

Run inside the isolated GeoGS Docker image with network access for acquisition.
Later runs mount this directory read-only and set TORCH_HOME=<cache-root>/torch.
No project scene, training image, or evaluation reference is used by this probe.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

import torch
from torchvision.models import AlexNet_Weights, VGG16_Weights


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    args = parser.parse_args()
    args.cache_root.mkdir(parents=True, exist_ok=False)
    hub_root = args.cache_root / "torch/hub"
    checkpoints = hub_root / "checkpoints"
    checkpoints.mkdir(parents=True)
    remote = "https://github.com/richzhang/PerceptualSimilarity.git"
    commit = subprocess.check_output(
        ["git", "ls-remote", remote, "refs/heads/master"], text=True
    ).split()[0]
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("Unverifiable LPIPS weight source commit")
    weights = {
        "alexnet": AlexNet_Weights.IMAGENET1K_V1.url,
        "vgg16": VGG16_Weights.IMAGENET1K_V1.url,
        "alex_lpips": f"https://raw.githubusercontent.com/richzhang/PerceptualSimilarity/{commit}/lpips/weights/v0.1/alex.pth",
        "vgg_lpips": f"https://raw.githubusercontent.com/richzhang/PerceptualSimilarity/{commit}/lpips/weights/v0.1/vgg.pth",
    }
    manifest = {"task_id": "PHD-GEOGS-P1P2P3-v1", "scientific_verdict": None,
                "lpips_weights_commit": commit, "weights": {}}
    for name, url in weights.items():
        output = checkpoints / url.rsplit("/", 1)[1]
        tmp = output.with_suffix(output.suffix + ".partial")
        digest = hashlib.sha256()
        with urllib.request.urlopen(url, timeout=120) as response, tmp.open("xb") as dst:
            while chunk := response.read(1024 * 1024):
                dst.write(chunk)
                digest.update(chunk)
        sha256 = digest.hexdigest()
        if name in ("alexnet", "vgg16"):
            expected = output.stem.rsplit("-", 1)[1]
            if not sha256.startswith(expected):
                raise ValueError(f"Torchvision weight checksum mismatch for {name}")
        tmp.rename(output)
        manifest["weights"][name] = {"url": url, "path": str(output.relative_to(args.cache_root)),
                                    "bytes": output.stat().st_size, "sha256": sha256}
    torch.hub.set_dir(str(hub_root))
    sys.path.insert(0, str(args.source_root))
    from lpipsPyTorch.modules.lpips import LPIPS
    zeros = torch.zeros(1, 3, 64, 64)
    with torch.no_grad():
        manifest["identical_image_lpips"] = {
            name: float(LPIPS(name)(zeros, zeros).item()) for name in ("alex", "vgg")}
    (args.cache_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
