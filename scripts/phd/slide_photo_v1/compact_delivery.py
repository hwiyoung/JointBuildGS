"""Keep raw native crop payloads external; preserve review images and positions."""
import shutil
from scipy.spatial import ConvexHull
from common import *
def compact(x):
    if isinstance(x,dict):
        if 'polygon_px' in x:
            p=np.asarray(x['polygon_px']);x['polygon_px']=p[ConvexHull(p).vertices].tolist() if len(p)>=3 else p.tolist()
        if 'file' in x and '/task0_crops/' in x['file'] and not x['file'].endswith('_pair.png'):x['file']=str(PAY/'task0/native_crops'/Path(x['file']).name)
        return {k:compact(v) for k,v in x.items()}
    if isinstance(x,list):return [compact(v) for v in x]
    return x
def main():
    out=PAY/'task0/native_crops';out.mkdir(exist_ok=True)
    for pat in ['*_best.png','*_oblique.png']:
        for p in (DOC/'figures/task0_crops').glob(pat):shutil.move(str(p),str(out/p.name))
    for p in [DOC/'figures/task0_contact_sheet.json',PAY/'task0/top10_photos.json']:
        dump(p,compact(load(p)))
if __name__=='__main__':main()
