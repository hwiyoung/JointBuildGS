"""Compare a main-experiment scene images.bin with the 937-image model (rotation / centre differences, 2-D observation count).
Usage: python3 -I pose_check.py <colmap_dense/sparse> <scene/sparse/0> [<scene2/sparse/0> ...]"""
import sys, struct, json
import numpy as np
def qR(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])
def read(p):
    ims = {}; n2d = 0
    with open(p + "/images.bin", "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            f.read(4); q = struct.unpack("<dddd", f.read(32)); t = np.array(struct.unpack("<ddd", f.read(24))); cid = struct.unpack("<i", f.read(4))[0]
            name = b""
            while (c := f.read(1)) != b"\x00":
                name += c
            k = struct.unpack("<Q", f.read(8))[0]; f.seek(24 * k, 1); n2d += k
            R = qR(q); ims[name.decode().rsplit(".", 1)[0]] = (R, -R.T @ t)
    with open(p + "/cameras.bin", "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]; cid, model, w, h = struct.unpack("<iiQQ", f.read(24)); par = struct.unpack("<4d", f.read(32))
    return ims, n2d, (model, w, h, par)
base, _, bc = read(sys.argv[1])
print("base camera", bc, "images", len(base))
for sc in sys.argv[2:]:
    ims, n2d, cam = read(sc)
    rot = []; dc = []
    for k, (R, C) in ims.items():
        Rb, Cb = base[k]
        rot.append(np.degrees(np.arccos(np.clip((np.trace(R @ Rb.T) - 1) / 2, -1, 1)))); dc.append(np.linalg.norm(C - Cb))
    print(sc.split("/")[-4], sc.split("/")[-3], "images", len(ims), "2D obs", n2d, "camera", cam, "max rot deg", float(np.max(rot)), "max centre diff m", float(np.max(dc)))
