"""Bounded native-float32 Gaussian PLY serialization; parameter values are unchanged."""
import hashlib
import json
from pathlib import Path
import time
from types import MethodType

import numpy as np
from plyfile import PlyData, PlyElement
import torch

CHUNK_ROWS = 65536
FIELDS = (["x", "y", "z", "nx", "ny", "nz"] + [f"f_dc_{i}" for i in range(3)]
          + [f"f_rest_{i}" for i in range(45)] + ["opacity", "scale_0", "scale_1"]
          + [f"rot_{i}" for i in range(4)])


def append_audit(model, payload):
    path = getattr(model, "_jbgs_stream_ply_audit_path", None)
    if path is not None:
        with Path(path).open("a") as stream:
            stream.write(json.dumps(dict(schema="jointbuildgs.geogs.stream_ply.v3", scientific_verdict=None,
                                         **payload), allow_nan=False) + "\n")


def save_ply(model, path):
    """Same default binary header, 61 float fields, vertex order and bytes as native."""
    started = time.monotonic()
    n = model._xyz.shape[0]
    chunk_rows = getattr(model, "_jbgs_stream_ply_chunk_rows", CHUNK_ROWS)
    if type(chunk_rows) is not int or not 1 <= chunk_rows <= CHUNK_ROWS:
        raise ValueError("PLY chunk rows must be within the fixed maximum65536")
    if model.construct_list_of_attributes() != FIELDS:
        raise ValueError("Require the frozen 61-field degree3 native Gaussian PLY schema")
    attributes = ((model._xyz, (n, 3)), (model._features_dc, (n, 1, 3)),
                  (model._features_rest, (n, 15, 3)), (model._opacity, (n, 1)),
                  (model._scaling, (n, 2)), (model._rotation, (n, 4)))
    if any(tuple(tensor.shape) != shape or tensor.dtype != torch.float32 for tensor, shape in attributes):
        raise ValueError("Require frozen native float32 Gaussian shapes")
    dtype = np.dtype([(name, "f4") for name in FIELDS])
    # Ask the installed, image-bound plyfile to create the native header without
    # allocating an N-row placeholder. Only the vertex count is substituted.
    header = PlyData([PlyElement.describe(np.empty(0, dtype=dtype), "vertex")]).header
    if header.count("element vertex 0\n") != 1:
        raise ValueError("Unexpected native PLY header construction")
    header = (header.replace("element vertex 0\n", f"element vertex {n}\n", 1) + "\n").encode("ascii")
    buffer = np.empty(min(n, chunk_rows), dtype=dtype)
    digest, chunks = hashlib.sha256(), 0
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("wb") as stream:
            stream.write(header)
            digest.update(header)
            for start in range(0, n, chunk_rows):
                stop = min(n, start + chunk_rows)
                rows = buffer[:stop-start]
                # Transfer each bounded tensor slice before applying SH layout
                # indexing on CPU; no whole-model CPU arrays or CUDA transpose
                # copies are created, and no floating arithmetic is applied.
                values = model._xyz.detach()[start:stop].to("cpu", non_blocking=False).numpy()
                for index, name in enumerate(("x", "y", "z")): rows[name] = values[:, index]
                del values
                for name in ("nx", "ny", "nz"): rows[name] = 0.0
                values = model._features_dc.detach()[start:stop].to("cpu", non_blocking=False).numpy()
                for channel in range(3): rows[f"f_dc_{channel}"] = values[:, 0, channel]
                del values
                values = model._features_rest.detach()[start:stop].to("cpu", non_blocking=False).numpy()
                for channel in range(3):
                    for coefficient in range(15):
                        rows[f"f_rest_{channel*15+coefficient}"] = values[:, coefficient, channel]
                del values
                for tensor, names in ((model._opacity, ["opacity"]), (model._scaling, ["scale_0", "scale_1"]),
                                      (model._rotation, [f"rot_{i}" for i in range(4)])):
                    values = tensor.detach()[start:stop].to("cpu", non_blocking=False).numpy()
                    for index, name in enumerate(names): rows[name] = values[:, index]
                    del values
                stream.write(rows.data)
                digest.update(rows.data)
                chunks += 1
        append_audit(model, dict(status="PASS_STREAMED_PLY_WRITTEN", path=str(path), gaussians=n,
            fields=len(FIELDS), bytes=path.stat().st_size, sha256=digest.hexdigest(), chunks=chunks,
            maximum_chunk_rows=chunk_rows, header_bytes=len(header),
            bounded_CPU_payload_bytes=(61 + 45) * 4 * min(n, chunk_rows),
            full_model_tuple_list_created=False, whole_model_CPU_arrays_created=False,
            elapsed_seconds=time.monotonic()-started))
    except Exception as error:
        append_audit(model, dict(status="FAIL_STREAMED_PLY_WRITE", path=str(path), gaussians=n,
                                completed_chunks=chunks, error_type=type(error).__name__, error=str(error)))
        raise


def bind(model, audit_path):
    if getattr(model, "_jbgs_stream_ply_bound", False):
        raise ValueError("Stream PLY writer already bound")
    model._jbgs_stream_ply_audit_path = Path(audit_path)
    model._jbgs_stream_ply_chunk_rows = CHUNK_ROWS
    model.save_ply = MethodType(save_ply, model)
    model._jbgs_stream_ply_bound = True
