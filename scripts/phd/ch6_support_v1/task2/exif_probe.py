"""Read EXIF + DJI XMP of a few members of Images.zip (no extraction to disk). Usage: python3 -I exif_probe.py <zip> <out.json>"""
import json, sys, zipfile, io, re
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
zp, out = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(zp)
names = [i for i in z.infolist() if i.filename.lower().endswith(('.jpg', '.jpeg'))]
res = dict(n_members=len(z.infolist()), n_jpg=len(names), first=names[0].filename, last=names[-1].filename,
           total_uncompressed=sum(i.file_size for i in names))
# day / flight-block statistics from file names
stamps = sorted(re.search(r'DJI_(\d{14})_', i.filename).group(1) for i in names if re.search(r'DJI_(\d{14})_', i.filename))
res["first_stamp"], res["last_stamp"] = stamps[0], stamps[-1]
pick = [names[0], names[len(names)//2], names[-1]]
samples = []
for zi in pick:
    raw = z.read(zi.filename)
    im = Image.open(io.BytesIO(raw))
    ex = im.getexif()
    d = {TAGS.get(k, k): (str(v)[:120]) for k, v in ex.items()}
    sub = ex.get_ifd(0x8769)
    d.update({TAGS.get(k, k): (str(v)[:120]) for k, v in sub.items() if TAGS.get(k, k) not in ("MakerNote",)})
    gps = ex.get_ifd(0x8825)
    d["GPS"] = {GPSTAGS.get(k, k): str(v)[:80] for k, v in gps.items()}
    m = re.search(rb'<x:xmpmeta.*?</x:xmpmeta>', raw[:200000], re.S)
    xmp = {}
    if m:
        for k, v in re.findall(rb'(drone-dji:[A-Za-z]+)="([^"]*)"', m.group(0)):
            xmp[k.decode()] = v.decode()[:120]
        for k, v in re.findall(rb'(tiff:[A-Za-z]+|exif:[A-Za-z]+|xmp:[A-Za-z]+)="([^"]*)"', m.group(0)):
            xmp[k.decode()] = v.decode()[:120]
    samples.append(dict(member=zi.filename, bytes=zi.file_size, size=im.size, mode=im.mode, exif=d, xmp=xmp))
res["samples"] = samples
json.dump(res, open(out, "w"), indent=1, ensure_ascii=False)
print(json.dumps(res, indent=1, ensure_ascii=False)[:9000])
