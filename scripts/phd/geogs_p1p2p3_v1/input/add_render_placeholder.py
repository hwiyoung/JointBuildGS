"""Add an explicit empty geometry placeholder for native read-only rendering.

Native render.py may read sparse/0 even with a loaded Gaussian model. The empty
PLY prevents its automatic write conversion; ALS training uses sparse_lod/0.
"""
import argparse
from pathlib import Path
import struct
from .prepare import sha,write_json


def run(scene):
    if not Path("/.dockerenv").exists():raise RuntimeError("Docker required")
    source=scene/"sparse/0/points3D.bin"
    if source.read_bytes()!=struct.pack("<Q",0):raise ValueError("Only the declared empty sparse geometry can receive a placeholder")
    destination=scene/"sparse/0/points3D.ply"
    header="ply\nformat ascii 1.0\ncomment EMPTY_METADATA_PLACEHOLDER_NOT_TRAINING_GEOMETRY\nelement vertex 0\n"
    header+="".join("property float "+name+"\n" for name in ("x","y","z","nx","ny","nz"))
    header+="".join("property uchar "+name+"\n" for name in ("red","green","blue"))+"end_header\n"
    with destination.open("x") as stream:stream.write(header)
    write_json(scene/"render_placeholder_receipt.json",dict(status="EMPTY_SPARSE_PLY_RENDER_READER_PLACEHOLDER",scientific_verdict=None,
        point_count=0,path=str(destination),sha256=sha(destination),source_empty_bin_sha256=sha(source),
        training_initialization="sparse_lod/0/points3D.ply contains actual ALS-derived points; --lod_init required",
        purpose="Avoid native render reader writing conversion files to read-only input. Loaded Gaussian model remains render geometry.",
        source_sha256=sha(__file__)))
    print(str(destination))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene",type=Path,required=True)
    run(parser.parse_args().scene)
