"""Inspect saved native renders without changing training, meshes, or masks.

Run inside the GeoGS Docker image. Rectangles are manually reviewed sky-only
diagnostic samples, never training masks or automatic semantic labels.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    assert Path("/.dockerenv").exists(), "Docker required"
    cfg = json.loads(Path(a.config).read_text())
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=False)
    (out / "config.json").write_text(json.dumps(cfg, indent=2))
    (out / "source.py").write_bytes(Path(__file__).read_bytes())
    base = Path(cfg["render_directory"])
    if cfg["mode"] == "contact_sheet":
        files = sorted((base / "gt").glob("*.png"))
        w, h, cols = 240, 180, 7
        sheet = Image.new("RGB", (w * cols, (h + 24) * ((len(files) + cols - 1) // cols)), "white")
        draw = ImageDraw.Draw(sheet)
        for i, f in enumerate(files):
            with Image.open(f) as im:
                thumb = im.convert("RGB")
                thumb.thumbnail((w, h))
            x, y = i % cols * w, i // cols * (h + 24)
            draw.text((x + 3, y + 3), f.stem, fill="black")
            sheet.paste(thumb, (x, y + 24))
        sheet.save(out / "contact.png")
        result = {"images": len(files)}
    else:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle
        index = cfg["index"]
        rgb = base / "gt" / f"{index:05d}.png"
        pred = base / "renders" / f"{index:05d}.png"
        dep = base / "vis" / f"depth_{index:05d}.tiff"
        with Image.open(rgb) as im:
            original = np.asarray(im.convert("RGB"))
        with Image.open(pred) as im:
            rendered = np.asarray(im.convert("RGB"))
        with Image.open(dep) as im:
            depth = np.asarray(im).copy()
        x0, y0, x1, y1 = cfg["sky_rectangle_xyxy"]
        region = depth[y0:y1, x0:x1]
        valid = np.isfinite(region) & (region > 0)
        accepted = valid & (region <= cfg["tsdf_depth_trunc_m"])
        values = region[valid]
        result = dict(index=index, image_size_wh=list(original.shape[1::-1]),
                      rectangle_meaning="MANUALLY_REVIEWED_SKY_ONLY_DIAGNOSTIC_NOT_A_TRAINING_MASK",
                      rectangle=cfg["sky_rectangle_xyxy"], pixels=int(region.size),
                      positive_finite_depth_pixels=int(valid.sum()),
                      within_tsdf_depth_range_pixels=int(accepted.sum()),
                      depth_quantiles_m=np.quantile(values, [0, .1, .5, .9, 1]).tolist() if values.size else [],
                      input_sha256={str(f): sha(f) for f in [rgb, pred, dep]})
        if "input_root" in cfg:
            inp = Path(cfg["input_root"])
            split = json.loads((inp / "scene/split_manifest.json").read_text())
            name = sorted(split["train"], key=lambda x: x["name"])[index]["name"]
            assert name == cfg["image_name"]
            source_image = inp / "scene/images" / name
            with Image.open(source_image) as im:
                result["source_image_mode"] = im.mode
                assert np.array_equal(np.asarray(im.convert("RGB")), original)
            result["source_image_exact_rgb_match"] = True
            result["image_name"] = name
            source_depths = {}
            for key, path in [("prior", inp / "prior/raw_depth" / (Path(name).stem + ".npy")),
                              ("mvs", inp / "mvs_rgb/raw_depth" / (Path(name).stem + ".npy")),
                              ("anchor8k_render", Path(cfg["anchor_render_directory"]) / "vis" / f"depth_{index:05d}.tiff")]:
                if path.suffix == ".npy":
                    array = np.load(path, allow_pickle=False).squeeze()
                else:
                    with Image.open(path) as im:
                        array = np.asarray(im).copy()
                assert array.ndim == 2
                sy, sx = array.shape[0] / original.shape[0], array.shape[1] / original.shape[1]
                rect = [int(np.ceil(x0*sx)), int(np.ceil(y0*sy)), int(np.floor(x1*sx)), int(np.floor(y1*sy))]
                sample = array[rect[1]:rect[3], rect[0]:rect[2]]
                finite = np.isfinite(sample) & (sample > 0)
                values_source = sample[finite]
                source_depths[key] = dict(shape=list(array.shape), rectangle_on_native_grid=rect,
                    pixels=int(sample.size), positive_finite_depth_pixels=int(finite.sum()),
                    within_tsdf_depth_range_pixels=int((finite & (sample <= cfg["tsdf_depth_trunc_m"])).sum()),
                    depth_quantiles_m=np.quantile(values_source, [0, .1, .5, .9, 1]).tolist() if values_source.size else [],
                    path=str(path), sha256=sha(path))
            result["source_depth_diagnostic"] = source_depths
        fig, ax = plt.subplots(1, 3, figsize=(15, 5), constrained_layout=True)
        ax[0].imshow(original); ax[0].set_title("Original RGB")
        ax[1].imshow(rendered); ax[1].set_title("Gaussian RGB (before TSDF)")
        dm = ax[2].imshow(np.ma.masked_where(~np.isfinite(depth) | (depth <= 0), depth),
                          cmap="viridis", vmin=0, vmax=cfg["tsdf_depth_trunc_m"])
        ax[2].set_title("Gaussian surface depth (m)")
        fig.colorbar(dm, ax=ax[2], shrink=.65)
        for axis in ax:
            axis.add_patch(Rectangle((x0, y0), x1-x0, y1-y0, fill=False, edgecolor="red", linewidth=1.5))
            axis.set_axis_off()
        fig.suptitle(f"View {index:05d}: red rectangle is a manually reviewed diagnostic sky sample")
        fig.savefig(out / "sky_rgb_depth.png", dpi=130)
        plt.close(fig)
    result.update(status="PASS", scientific_verdict=None, script_sha256=sha(Path(__file__)))
    (out / "receipt.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
