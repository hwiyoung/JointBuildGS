"""PHD-MAIN-PREP-DISCARD-RULE-v1: additions to s03_stage1.py made after equivalence check 1 had finished (so that every
check-1 run used one version of the script). Output-only additions, no change to any computed value:
  - the export for the fork also writes the mark codes (index of the smallest rule threshold t with |r| <= t tau; -1 no mark;
    len(THRESHOLDS) beyond the largest) so that fork r11 can read the own marks of pixels without a patch for any rule
  - summary.json records the mesh directory (mesh_dir) of the run
  python3 patch_s03_after_eq1.py   (stdlib; asserts every target once)"""
from pathlib import Path

p = Path(__file__).with_name("s03_stage1.py")
s = p.read_text()
R = [
    ('''        for sub in ("conf", "mvs", "prior", "tau", "locmap", "markmap"):''',
     '''        for sub in ("conf", "mvs", "prior", "tau", "locmap", "markmap", "markcode"):'''),
    ('''            np.save(EX / "markmap" / f"{stem}.npy", mk_.reshape(H, W))''',
     '''            np.save(EX / "markmap" / f"{stem}.npy", mk_.reshape(H, W))
            code = np.full(len(a1), -1, np.int32)
            rr = ar / np.where(tau_px > 0, tau_px, np.nan)
            code[a1] = np.searchsorted(np.asarray(tly.THRESHOLDS), rr[a1], side="left")
            mc_ = np.full(H * W, -1, np.int32); mc_[q["idx"]] = code; np.save(EX / "markcode" / f"{stem}.npy", mc_.reshape(H, W))'''),
    ('''                confidence=conf, knn_check=knn_check, module="src/phd/prior_propagation_v5",''',
     '''                confidence=conf, knn_check=knn_check, module="src/phd/prior_propagation_v5", mesh_dir=str(mesh_dir),'''),
]
for a, b in R:
    assert s.count(a) == 1, a[:80]
    s = s.replace(a, b)
p.write_text(s)
print("s03 patched")
