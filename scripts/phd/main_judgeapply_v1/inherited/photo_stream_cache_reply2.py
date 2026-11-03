"""JPEG-backed, bounded LRU supplying exact float32 pixels to the frozen score kernel."""
import collections,time

class StreamImageCache:
    # A worker keeps recent photos between tiles; each process owns at most 4 GiB.
    entries=collections.OrderedDict()
    resident_bytes=0
    budget_bytes=4*2**30
    def __init__(self,cam,root,budget=None):
        self.cam=cam;self.root=root;self.used=type(self).resident_bytes
        self.decodes=0;self.decode_seconds=0.;self.spill_bytes=0
        self.hits=0;self.evictions=0;self.need={}
    def prepare(self,levels):
        self.need={int(j):set(map(int,k)) for j,k in levels.items()}
    def get(self,j,k):
        cls=type(self);key=(j,k)
        if key in cls.entries:
            self.hits+=1;cls.entries.move_to_end(key);return cls.entries[key]
        start=time.monotonic()
        images=self.cam.gray_pyramid(j,self.need[j])
        self.decode_seconds+=time.monotonic()-start;self.decodes+=1
        wanted=images[k]
        for level,im in images.items():
            key=(j,level)
            if key in cls.entries:cls.resident_bytes-=cls.entries.pop(key).nbytes
            while cls.entries and cls.resident_bytes+im.nbytes>cls.budget_bytes:
                _,old=cls.entries.popitem(last=False);cls.resident_bytes-=old.nbytes;self.evictions+=1
            assert im.nbytes<=cls.budget_bytes
            cls.entries[key]=im;cls.resident_bytes+=im.nbytes
        self.used=cls.resident_bytes
        return wanted
