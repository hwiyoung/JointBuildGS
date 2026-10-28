"""File-backed columns: small CPU jobs stay within their 4 GiB container limit."""
import zipfile,json
from collections.abc import Mapping
from pathlib import Path
import numpy as np

class Columns(Mapping):
    def __init__(self,path):
        self.path=Path(path);self.keys_=json.loads((self.path/'columns.json').read_text());self.arrays={}
    def __len__(self):return len(self.keys_)
    def __iter__(self):return iter(self.keys_)
    def __getitem__(self,key):
        if key not in self.arrays:self.arrays[key]=np.load(self.path/(key+'.npy'),mmap_mode='r')
        return self.arrays[key]

def unpack_npz(source,path):
    path=Path(path);done=path/'columns.json'
    if done.exists():return Columns(path)
    path.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(source) as z:
        names=z.namelist();assert all('/' not in n and n.endswith('.npy') for n in names)
        for name in names:
            p=path/name;t=p.with_suffix('.npy.tmp')
            with z.open(name) as src,t.open('wb') as dst:
                for chunk in iter(lambda:src.read(2**20),b''):dst.write(chunk)
            t.replace(p)
    done.write_text(json.dumps([n[:-4] for n in names]))
    return Columns(path)
