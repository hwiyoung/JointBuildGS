"""Run an unmodified preprocessing/evaluation entry point with fixed RNG seed 0."""
import os,runpy,sys,random
from pathlib import Path
import numpy as np
random.seed(0);np.random.seed(0)
try:
 import open3d as o3d
 o3d.utility.random.seed(0)
except ImportError:pass
script=Path(sys.argv[1]).resolve();sys.argv=sys.argv[1:];sys.path.insert(0,str(script.parent));runpy.run_path(str(script),run_name='__main__')
