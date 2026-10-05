"""Content hashes of the deterministic outputs of PHD-STAGE2-R7-PROPAGATION-v1 (array contents, not zip bytes: npz files
carry write times). python content_hashes.py <out.json>   # mounts /p7 (ro for reading)"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

P7 = Path("/p7")
out = {}


def h(b):
    return hashlib.sha256(b).hexdigest()[:16]


for f in sorted((P7 / "stage1/products").glob("*/store_*.npz")):
    z = np.load(f)
    out[str(f.relative_to(P7))] = {k: h(np.ascontiguousarray(z[k]).tobytes()) for k in sorted(z.files)}
for f in sorted((P7 / "stage1/products").glob("*/locmap/*.npy"))[:6] + sorted((P7 / "inputs").glob("*/tau_spec/*.npy"))[:6] + \
        sorted((P7 / "inputs").glob("*/seat_surface.npy")):
    out[str(f.relative_to(P7))] = h(np.load(f).tobytes())
for f in [P7 / "stage1/tolerance.json", P7 / "premeasure_v2/tables.md", P7 / "verify/verify_dry.json"] + sorted((P7 / "inputs").glob("*/prepare_*.json")):
    out[str(f.relative_to(P7))] = h(f.read_bytes())
for f in sorted((P7 / "runs").glob("*/model/monitor/init_points.npz")):
    z = np.load(f)
    out[str(f.relative_to(P7))] = {k: h(np.ascontiguousarray(z[k]).tobytes()) for k in sorted(z.files)}
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, sort_keys=True))
print(len(out), "entries")
