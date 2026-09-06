"""MVS lineage validation and SH0/SH3 color-only diagnostic adapters."""
import numpy as np
from src.phd.p2_ab_v3.appearance_sh import StructuredGaussians as SHGaussians
from src.phd.p2_ab_v3.appearance_sh import render_view as sh3_render_view
from src.phd.p2_ab_v2.reconstruction import render_view as sh0_render_view


def validate_mvs_initial(seed,g0,native,expected_count=None):
    """Require exact original source membership, not a filename-based MVS claim."""
    ids=np.asarray(seed["seed_id"])
    if ids.ndim!=1 or ids.dtype.kind not in "iu":raise ValueError("invalid source row IDs")
    if len(np.unique(ids))!=len(ids) or np.any(ids<0) or np.any(ids>=len(native["mvs_xyz"])):
        raise ValueError("duplicate or out-of-range MVS source rows")
    if expected_count is not None and len(ids)!=expected_count:raise ValueError("unexpected MVS seed count")
    checks={"xyz_native_exact":np.array_equal(seed["xyz"],native["mvs_xyz"][ids].astype(np.float32)),
        "tile_rows_exact":np.array_equal(seed["native_row"],native["mvs_tile_rows"][ids]),
        "patch_ids_exact":np.array_equal(seed["native_patch_id"],native["mvs_patch_id"][ids]),
        "units_exact":np.array_equal(seed["unit_index"],native["mvs_unit_index"][ids]),
        "g0_xyz_exact":np.array_equal(g0["xyz"],seed["xyz"])}
    for key in ["seed_id","native_row","native_patch_id","unit_index"]:
        checks["g0_"+key+"_exact"]=np.array_equal(g0[key],seed[key])
    if not all(checks.values()):raise ValueError("MVS provenance mismatch: "+str(checks))
    return dict(source="current_image_MVS",native_count=len(native["mvs_xyz"]),seed_count=len(ids),
        checks=checks,actual_A_action_consumed=False)


class StructuredGaussians(SHGaussians):
    def __init__(self,seed,cfg,device="cuda"):
        super().__init__(seed,cfg,device)
        self.active_sh_degree=3

    def state_arrays(self,seed):
        result=super().state_arrays(seed)
        result["sh_degree"]=self.active_sh_degree
        return result


def freeze_except_color(model,degree):
    if degree not in [0,3]:raise ValueError("probe only declares SH0 and SH3")
    model.active_sh_degree=degree
    names={"sh0","sh_rest"} if degree==3 else {"sh0"}
    for name,p in model.named_parameters():p.requires_grad_(name in names)
    return [model.sh0,model.sh_rest] if degree==3 else [model.sh0]


def render_view(model,view):
    return sh3_render_view(model,view) if model.active_sh_degree==3 else sh0_render_view(model,view)
