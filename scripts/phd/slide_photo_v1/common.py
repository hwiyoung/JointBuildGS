"""Task-only paths; geometry helpers reuse REGIONFIG, no prior task writes."""
import importlib.util
import sys
from pathlib import Path
_s=importlib.util.spec_from_file_location('region_geometry','/repo/scripts/phd/main_regionfig_v1/common.py')
G=importlib.util.module_from_spec(_s);_s.loader.exec_module(G)
import numpy as np
PH=G.PH; S0=G.S0; S1=G.S1; U=G.U; RAW=G.RAW
W=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
PAY=Path('/payload'); DOC=Path('/docs'); CFG=Path('/cfg'); REPO=Path('/repo')
load=G.load;dump=G.dump;sha=G.sha;now=G.now
GEOMETRY_KEYS=['centre','normal','roof_like','tangent1','tangent2','area','building','face_ext','surf','raw_centre','source_patch','patch_id','normal_defined']
def config():
    c=load(CFG/'slide_photo_v1.json');l=load(CFG/'slide_photo_v1.lock.json')
    assert sha(CFG/'slide_photo_v1.json')==l['config_sha256'];return c
def geometry(tile,prior):
    p=W/'patch_values'/f'{tile}__{prior}__R1.5.npz'
    # Deliberate allowlist: never decompress prior outcomes or classifications.
    with np.load(p) as z:return {k:z[k] for k in GEOMETRY_KEYS}
def depth(p):
    a=Path(p).read_bytes();off=0
    for _ in range(3):off=a.find(b'&',off,100)+1
    w,h,ch=map(int,a[:off].decode().split('&')[:3])
    return np.frombuffer(a,dtype='<f4',offset=off,count=w*h).reshape((w,h),order='F').T.copy()
def plot_setup(size=36):
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for p in ['/fonts/NotoSansCJK-Regular.ttc','/fonts/NotoSansCJK-Bold.ttc']:font_manager.fontManager.addfont(p)
    plt.rcParams.update({'font.family':'Noto Sans CJK JP','font.size':size,'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False})
    return plt
