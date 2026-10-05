"""Generate an isolated two-pass gsplat adapter from preserved historical bytes.

C4 is filtered appearance; C8 is reserved plane-only geometry. Existing sources
and the previous development kernel/cache are never modified.
"""
import argparse
import hashlib
import json
from pathlib import Path


def sha(data):return hashlib.sha256(data).hexdigest()


def once(source,old,new):
    if source.count(old)!=1:raise ValueError(f"expected exactly one patch anchor: {old[:90]!r}")
    return source.replace(old,new)


def main(config_path):
    cfg=json.loads(Path(config_path).read_text());out=Path("/output")
    if any(out.iterdir()):raise ValueError("empty new output required")
    root=Path(cfg["source_overlay_root"])
    fwd_path=root/"rasterize_to_pixels_2dgs_fwd.cu"
    bwd_path=root/"rasterize_to_pixels_2dgs_bwd.cu"
    fwd=fwd_path.read_text();bwd=bwd_path.read_text()
    fwd=once(fwd,"""            const S surface_depth =
                s.x * w_M.x + s.y * w_M.y + w_M.z;""","""            // Reserved 8-feature pass: plane-only geometric evidence.
            // C4 appearance never evaluates the unsafe auxiliary hit depth.
            S surface_depth = 0.f;
            if constexpr (COLOR_DIM == 8) {
                surface_depth = s.x * w_M.x + s.y * w_M.y + w_M.z;
                if (!isfinite(s.x) || !isfinite(s.y) ||
                    !isfinite(surface_depth) || surface_depth <= 0.01f) continue;
            }""")
    fwd=once(fwd,"""            const S gauss_weight = min(gauss_weight_3d, gauss_weight_2d);""","""            const S gauss_weight = COLOR_DIM == 8 ? gauss_weight_3d
                                                       : min(gauss_weight_3d, gauss_weight_2d);""")
    fwd=once(fwd,"""            median_depth += surface_depth * vis;""","""            if constexpr (COLOR_DIM == 8) median_depth += surface_depth * vis;""")
    fwd=once(fwd,"""            if (next_T <= 1e-4) { // this pixel is done: exclusive
                done = true;
                break;
            }""","""            if constexpr (COLOR_DIM != 8) {
                if (next_T <= 1e-4) { // Preserve historical appearance bytes.
                    done = true;
                    break;
                }
            }""")
    fwd=once(fwd,"""            T = next_T;""","""            T = next_T;
            if constexpr (COLOR_DIM == 8) {
                // Include the crossing plane, so omitted tail mass <= 1e-4.
                if (T <= 1e-4f) { done = true; break; }
            }""")
    bwd=once(bwd,"""                gauss_weight = min(gauss_weight_3d, gauss_weight_2d);""","""                gauss_weight = COLOR_DIM == 8 ? gauss_weight_3d
                                              : min(gauss_weight_3d, gauss_weight_2d);
                if constexpr (COLOR_DIM == 8) {
                    const S hit_z = s.x * w_M.x + s.y * w_M.y + w_M.z;
                    if (!isfinite(s.x) || !isfinite(s.y) || !isfinite(hit_z) || hit_z <= 0.01f)
                        valid = false;
                }""")
    bwd=once(bwd,"""                const S surface_depth =
                    s.x * w_M.x + s.y * w_M.y + w_M.z;
                S v_depth = fac * v_median;""","""                S surface_depth = 0.f;
                S v_depth = 0.f;
                if constexpr (COLOR_DIM == 8) {
                    surface_depth = s.x * w_M.x + s.y * w_M.y + w_M.z;
                    v_depth = fac * v_median;
                }""")
    bwd=once(bwd,"""                v_alpha +=
                    (surface_depth * T - buffer_surface * ra) * v_median;""","""                if constexpr (COLOR_DIM == 8) {
                    v_alpha += (surface_depth * T - buffer_surface * ra) * v_median;
                }""")
    start=bwd.index("                //====== 2DGS ======//")
    end=bwd.index("\n                GSPLAT_PRAGMA_UNROLL\n                for (uint32_t k = 0; k < COLOR_DIM; ++k) {\n                    buffer[k]",start)
    bwd=bwd[:start]+"""                // Appearance alpha and direct geometry-hit derivatives are
                // separate. An opacity clamp suppresses d(alpha), never d(hit).
                const bool alpha_unclamped = opac * vis <= 0.999f;
                const S v_G = alpha_unclamped ? opac * v_alpha : 0.f;
                const bool plane_branch = COLOR_DIM == 8 || gauss_weight_3d <= gauss_weight_2d;
                if (plane_branch) {
                    const vec2<S> v_s = {
                        v_G * -vis * s.x + v_depth * w_M.x,
                        v_G * -vis * s.y + v_depth * w_M.y
                    };
                    const S v_sx_pz = v_s.x / ray_cross.z;
                    const S v_sy_pz = v_s.y / ray_cross.z;
                    const vec3<S> v_ray_cross = {
                        v_sx_pz, v_sy_pz, -(v_sx_pz * s.x + v_sy_pz * s.y)
                    };
                    const vec3<S> v_h_u = glm::cross(h_v, v_ray_cross);
                    const vec3<S> v_h_v = glm::cross(v_ray_cross, h_u);
                    v_u_M_local = {-v_h_u.x, -v_h_u.y, -v_h_u.z};
                    v_v_M_local = {-v_h_v.x, -v_h_v.y, -v_h_v.z};
                    v_w_M_local = {
                        px * v_h_u.x + py * v_h_v.x + v_depth * s.x,
                        px * v_h_u.y + py * v_h_v.y + v_depth * s.y,
                        px * v_h_u.z + py * v_h_v.z + v_depth
                    };
                } else if (alpha_unclamped) {
                    const S v_G_ddelx = -vis * FILTER_INV_SQUARE * d.x;
                    const S v_G_ddely = -vis * FILTER_INV_SQUARE * d.y;
                    v_xy_local = {v_G * v_G_ddelx, v_G * v_G_ddely};
                    if (v_means2d_abs != nullptr) {
                        v_xy_abs_local = {abs(v_xy_local.x), abs(v_xy_local.y)};
                    }
                }
                if (alpha_unclamped) v_opacity_local = vis * v_alpha;
"""+bwd[end:]
    bwd=once(bwd,"""                buffer_surface += surface_depth * fac;""","""                if constexpr (COLOR_DIM == 8) buffer_surface += surface_depth * fac;""")
    (out/"overlay").mkdir()
    (out/"overlay"/fwd_path.name).write_text(fwd);(out/"overlay"/bwd_path.name).write_text(bwd)
    record={"contract":"PHD_P2_V2_C4_FILTERED_RGB_C8_INDEPENDENT_PLANE_GEOMETRY_v1",
        "source_hashes":{str(fwd_path):sha(fwd_path.read_bytes()),str(bwd_path):sha(bwd_path.read_bytes())},
        "output_hashes":{fwd_path.name:sha(fwd.encode()),bwd_path.name:sha(bwd.encode())},
        "feature_contract":{"4":"unchanged filtered appearance, unsafe auxiliary disabled",
           "8":"reserved dummy features; plane-only alpha and independent T; native normals/alpha plus auxiliary sum(w*z_hit)"},
        "geometry_hit_condition":"finite positive cameraZ>0.01, plane alpha>=1/255; original raster tile culling and centerZ order retained; geometry includes earlystop crossing primitive",
        "source_generator_sha256":sha(Path(__file__).read_bytes()),"config":cfg,"scientific_verdict":None}
    (out/"adapter_manifest.json").write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps(record),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--config",required=True);main(p.parse_args().config)
