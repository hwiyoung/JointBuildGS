"""PHD-MAIN-FIXTEST-v1 일 7 step 4 (sensitivity only; the fill task's values and files stay as they are): the wall-present flag
(virtual-view mesh within 0.25 m of the cell centre) for EVERY cell of the B173nb_b10 LoD2 face 53, including the 3,262 cells that one
training view put a pixel on (outside the unseen set), for the proposed method's two seeds (jointbuildgs:dev, CPU; no GPU, no render).
  bash run_item7.sh extra_flags extra_flags.py
Same rule and code as the fill task's virtual component (scripts/phd/main_fill_v1/virtual/vv_metrics.py measure, lines 134-152: the
mesh cut to the wall region, MeshScene distance <= 0.25 m); the cells' labels for the cells outside the set come from cause.py
(the unseen split's rule with the column's current top). The flags of the set's cells must equal SL's wall_flags_LoD2.npz.
Reads /item7/cause_cells.npz (cause.py). Writes /item7/extra_flags.npz and /item7/extra_flags.json. scientific_verdict: null."""
import sys

import numpy as np

sys.path.insert(0, "/repo")
import item7_common as I  # noqa: E402
from src.phd.metrics_v3.surface import MeshScene  # noqa: E402

RESULTS = ("prop_LoD2_s0", "prop_LoD2_s1")
_TY = {"double": "<f8", "float64": "<f8", "float": "<f4", "float32": "<f4", "uchar": "u1", "uint8": "u1", "char": "i1", "int8": "i1",
       "ushort": "<u2", "uint16": "<u2", "short": "<i2", "int16": "<i2", "uint": "<u4", "uint32": "<u4", "int": "<i4", "int32": "<i4"}


def ply_open(path):
    """copied from scripts/phd/main_fill_v1/virtual/vv_metrics.py ply_open (itself figs_bl.ply_open, lines 131-157)."""
    with open(path, "rb") as f:
        head = []
        while True:
            ln = f.readline().decode("ascii", "replace").strip()
            head.append(ln)
            if ln == "end_header":
                break
        off = f.tell()
    assert "format binary_little_endian 1.0" in head, path
    elems = []
    for ln in head:
        p = ln.split()
        if p and p[0] == "element":
            elems.append([p[1], int(p[2]), []])
        elif p and p[0] == "property":
            elems[-1][2].append(p[1:])
    (vn, nv, vp), (fn, nf, fp) = elems[0], elems[1]
    assert vn == "vertex" and fn == "face" and len(fp) == 1 and fp[0][0] == "list", path
    vdt = np.dtype([(q[1], _TY[q[0]]) for q in vp])
    fdt = np.dtype([("n", _TY[fp[0][1]]), ("i", _TY[fp[0][2]], (3,))])
    vm = np.memmap(path, dtype=vdt, mode="r", offset=off, shape=(nv,))
    fm = np.memmap(path, dtype=fdt, mode="r", offset=off + nv * vdt.itemsize, shape=(nf,))
    if nf:
        assert int(fm["n"][: min(nf, 1000)].min()) == 3 and int(fm["n"].max()) == 3, f"not all triangles: {path}"
    return vm, fm


def wall_region(w):
    """copied from vv_metrics.wall_region (figs_bl.py site_regions 'wall', lines 172-175)."""
    return (np.asarray(w["centre"], np.float64), np.asarray(w["t"], np.float64), np.asarray(w["normal"], np.float64),
            w["s_range"][0] - 1.5, w["s_range"][1] + 1.5, 1.5, w["z_range"][0] - 1.5, w["z_range"][1] + 1.5)


def _keep(Vx, reg):
    """copied from vv_metrics._keep (figs_bl.py _keep, lines 177-181)."""
    c, t, n, slo, shi, hd, zlo, zhi = reg
    d = (Vx - c) @ n
    s = (Vx - c) @ t
    return (np.abs(d) <= hd) & (s >= slo) & (s <= shi) & (Vx[:, 2] >= zlo) & (Vx[:, 2] <= zhi)


def share(flag, m):
    return dict(share=float(flag[m].mean()) if m.any() else None, present=int(flag[m].sum()), patches=int(m.sum()))


def main():
    T = I.Timer()
    w, un, face = I.wall_place()
    reg = wall_region(w)
    C = np.load(I.OUT / "cause_cells.npz")
    X, in_set, li, li_rule, Tm = C["centre"], C["in_set"], C["li"], C["li_rule"], C["T"]
    pos = {int(l_): k for k, l_ in enumerate(C["loc"])}
    order = np.array([pos[int(p)] for p in un["patch"][face]])           # face patches of unseen.npz -> cells
    fl = np.load(I.VW / "wall_flags_LoD2.npz")
    out = dict(task_id="PHD-MAIN-FIXTEST-v1", item="일 7", step="extra_flags (sensitivity)", mark="[이 발주에서 냄]", site=I.SITE,
               face=int(w["surf_ext"]), rule="virtual-view mesh within 0.25 m of the cell centre (vv_metrics.measure lines 134-152)",
               results={}, scientific_verdict=None)
    arrays = {}
    for res in RESULTS:
        js = I.jload(I.VW / f"{res}__LoD2.json")
        mesh = I.MF / js["mesh"].split("MF/", 1)[1]
        st = mesh.stat()
        same_mesh = int(st.st_size) == int(js["mesh_size"]) and int(st.st_mtime_ns) == int(js["mesh_mtime_ns"])
        vm, fm = ply_open(mesh)
        Vx = np.stack([np.asarray(vm["x"], np.float64), np.asarray(vm["y"], np.float64), np.asarray(vm["z"], np.float64)], 1)
        Fi = np.asarray(fm["i"])
        keepv = _keep(Vx, reg)
        Fc = Fi[keepv[Fi].any(1)].astype(np.int64)
        del Fi, vm, fm
        d = MeshScene(Vx, Fc).distance(X)
        del Vx
        pres = d <= 0.25
        fill_flags = fl[res].astype(bool)
        mine_on_set = pres[order]
        cnt_now = in_set & (li == 0)                      # the fill's count: the set's label-0 cells
        all0 = li_rule == 0                               # every cell of the face with label 0 by the same rule
        out["results"][res] = dict(
            mesh=js["mesh"], same_mesh_as_fill=same_mesh, crop_triangles=int(len(Fc)), crop_triangles_fill=js["wall"]["crop_triangles"],
            set_flags_equal_fill=bool(np.array_equal(mine_on_set, fill_flags)), set_flags_differ=int((mine_on_set != fill_flags).sum()),
            now_as_fill=share(pres, cnt_now),
            without_T=share(pres, cnt_now & ~Tm),
            with_every_cell_of_T=share(pres, all0),
            T_set_cells=share(pres, cnt_now & Tm), T_cells_outside_set=share(pres, all0 & ~in_set & Tm),
            outside_set_outside_T=share(pres, all0 & ~in_set & ~Tm),
            T_every_cell=share(pres, all0 & Tm))
        arrays[res] = pres
        T.mark(res)
        I.log(res, out["results"][res])
    out["seconds"] = T.marks
    I.jdump(I.OUT / "extra_flags.json", out)
    np.savez_compressed(I.OUT / "extra_flags.npz", loc=C["loc"], **arrays)
    I.log("extra_flags done", T.marks)


if __name__ == "__main__":
    main()
