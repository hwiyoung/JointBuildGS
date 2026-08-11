#!/usr/bin/env python3
"""Create the frozen gsplat-1.4 surface-intersection output overlay.

The pinned gsplat 1.4 kernel already computes the perspective-correct local
ray--surfel intersection ``s`` for opacity, but its rendered depth channels use
the Gaussian centre Z.  This task-local overlay leaves every historical output
unchanged and repurposes the otherwise unused ``render_median`` output as
``sum_i(alpha_i T_i z_hit_i)``.  The repository renderer normalises this sum by
the unchanged accumulated alpha only when the task-local environment flag is
present.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


PINNED = {
    "cuda/csrc/rasterize_to_pixels_2dgs_fwd.cu":
        "c5e7b0350a332c4885ed22f2642eaa7364011a658bead35193cb33748c100505",
    "cuda/csrc/rasterize_to_pixels_2dgs_bwd.cu":
        "a7e591d3b427c876f173a99d6c737f941063cf96c869c805187a66d8d869f311",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one source match, got {count}")
    return text.replace(old, new, 1)


def patch_forward(text: str) -> str:
    text = replace_once(
        text,
        """            const vec2<S> s =
                vec2<S>(ray_cross.x / ray_cross.z, ray_cross.y / ray_cross.z);

            const S gauss_weight_3d = s.x * s.x + s.y * s.y;
""",
        """            const vec2<S> s =
                vec2<S>(ray_cross.x / ray_cross.z, ray_cross.y / ray_cross.z);
            // Perspective-correct camera-Z of this exact ray--surfel hit.
            const S surface_depth =
                s.x * w_M.x + s.y * w_M.y + w_M.z;

            const S gauss_weight_3d = s.x * s.x + s.y * s.y;
""",
        "forward surface-depth insertion",
    )
    text = replace_once(
        text,
        """            // compute median depth
            if (T > 0.5) {
                median_depth = c_ptr[COLOR_DIM - 1];
                median_idx = batch_start + t;
            }
""",
        """            // Task-local auxiliary output: unnormalised expected
            // perspective-correct surface-intersection depth.  Historical
            // render_colors/depth, distortion, RGB, alpha and normals above
            // remain untouched.
            median_depth += surface_depth * vis;
            median_idx = batch_start + t;
""",
        "forward auxiliary accumulation",
    )
    return text


def patch_backward(text: str) -> str:
    text = replace_once(
        text,
        """    S buffer[COLOR_DIM] = {0.f};
    S buffer_normals[3] = {0.f};
""",
        """    S buffer[COLOR_DIM] = {0.f};
    S buffer_normals[3] = {0.f};
    // Reverse-compositing accumulator for the task-local surface sum.
    S buffer_surface = 0.f;
""",
        "backward surface buffer",
    )
    text = replace_once(
        text,
        """                s = {ray_cross.x / ray_cross.z, ray_cross.y / ray_cross.z};

                gauss_weight_3d = s.x * s.x + s.y * s.y;
""",
        """                s = {ray_cross.x / ray_cross.z, ray_cross.y / ray_cross.z};

                gauss_weight_3d = s.x * s.x + s.y * s.y;
""",
        "backward intersection anchor",
    )
    text = replace_once(
        text,
        """                // gradient contribution from median depth
                if (batch_end - t == median_idx) {
                    v_rgb_local[COLOR_DIM - 1] += v_median;
                }

                // compute the current T for this gaussian
""",
        """                // compute the current T for this gaussian.  The
                // task-local auxiliary is an expected surface-hit sum, not a
                // selected median contributor.
""",
        "backward remove median selector",
    )
    text = replace_once(
        text,
        """                // update v_rgb for this gaussian
                const S fac = alpha * T;
""",
        """                // update v_rgb for this gaussian
                const S fac = alpha * T;
                const S surface_depth =
                    s.x * w_M.x + s.y * w_M.y + w_M.z;
                S v_depth = fac * v_median;
""",
        "backward surface value gradient",
    )
    text = replace_once(
        text,
        """                for (uint32_t k = 0; k < COLOR_DIM; ++k) {
                    v_alpha +=
                        (rgbs_batch[t * COLOR_DIM + k] * T - buffer[k] * ra) *
                        v_render_c[k];
                }

                // update v_normal for this gaussian
""",
        """                for (uint32_t k = 0; k < COLOR_DIM; ++k) {
                    v_alpha +=
                        (rgbs_batch[t * COLOR_DIM + k] * T - buffer[k] * ra) *
                        v_render_c[k];
                }
                v_alpha +=
                    (surface_depth * T - buffer_surface * ra) * v_median;

                // update v_normal for this gaussian
""",
        "backward surface alpha gradient",
    )
    text = replace_once(
        text,
        """                //====== 2DGS ======//
                if (opac * vis <= 0.999f) {
                    S v_depth = 0.f;
""",
        """                //====== 2DGS ======//
                if (opac * vis <= 0.999f) {
""",
        "backward use surface depth gradient",
    )
    text = replace_once(
        text,
        """                for (uint32_t k = 0; k < COLOR_DIM; ++k) {
                    buffer[k] += rgbs_batch[t * COLOR_DIM + k] * fac;
                }

                GSPLAT_PRAGMA_UNROLL
""",
        """                for (uint32_t k = 0; k < COLOR_DIM; ++k) {
                    buffer[k] += rgbs_batch[t * COLOR_DIM + k] * fac;
                }
                buffer_surface += surface_depth * fac;

                GSPLAT_PRAGMA_UNROLL
""",
        "backward surface reverse accumulator",
    )
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    observed = {rel: sha256(source / rel) for rel in PINNED}
    if observed != PINNED:
        raise RuntimeError(f"pinned gsplat source hash mismatch: {observed}")

    manifest_path = output / "surface_overlay_manifest.json"
    if output.exists():
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text())
            if manifest.get("source_sha256") == PINNED:
                print(json.dumps(manifest, sort_keys=True))
                return
        raise RuntimeError(f"refusing to overwrite non-matching overlay: {output}")

    temporary = output.with_name(output.name + ".tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    package = temporary / "gsplat"
    shutil.copytree(source, package)

    fwd_rel = "cuda/csrc/rasterize_to_pixels_2dgs_fwd.cu"
    bwd_rel = "cuda/csrc/rasterize_to_pixels_2dgs_bwd.cu"
    (package / fwd_rel).write_text(
        patch_forward((package / fwd_rel).read_text()), encoding="utf-8"
    )
    (package / bwd_rel).write_text(
        patch_backward((package / bwd_rel).read_text()), encoding="utf-8"
    )
    manifest = {
        "contract": "gsplat_1.4_render_median_is_surface_intersection_weighted_sum_v1",
        "source_sha256": PINNED,
        "patched_sha256": {
            fwd_rel: sha256(package / fwd_rel),
            bwd_rel: sha256(package / bwd_rel),
        },
        "historical_outputs_modified": [],
        "repurposed_auxiliary_output": "render_median",
        "formula": "sum_i(alpha_i*T_i*(s_x*T_wx+s_y*T_wy+T_wz))",
        "scientific_verdict": None,
    }
    (temporary / "surface_overlay_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.rename(output)
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
