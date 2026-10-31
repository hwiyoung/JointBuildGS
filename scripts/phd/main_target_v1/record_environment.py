"""Record the exact image's installed versions without installing dependencies."""
import importlib.metadata as md,os,platform
from common import *
names=['torch','numpy','scipy','open3d','plyfile','Pillow','diff-surfel-rasterization','simple-knn']
versions={}
for n in names:
    try:versions[n]=md.version(n)
    except md.PackageNotFoundError:versions[n]='distribution metadata unavailable'
dump(DOC/'tables/stage1_environment.json',dict(at=stamp(),image=os.environ['TARGET_IMAGE'],python=platform.python_version(),packages=versions,
    execution='Docker; no installation; CPU inventory of the GPU preflight image',scientific_verdict=None))
print(versions,flush=True)
