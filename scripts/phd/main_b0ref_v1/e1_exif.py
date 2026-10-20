"""PHD-MAIN-B0REF-v1 일 4 7.4: capture time of the B0 images (the 15 GeoGS example views = the B0 author views A15) from EXIF
(DateTimeOriginal, OffsetTimeOriginal, GPS date/time) and the DJI XMP block when present. Read-only. (jointbuildgs:dev, CPU)

  python e1_exif.py   -> /b0/prep/image_times.json   [이 요청에서 냄] scientific_verdict: null"""
import io
import re
import zipfile
from pathlib import Path

from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS

from b0_common import B0, PH, jdump, now

IMG = PH / "geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/scene/images"
ZIP = Path("/art/phase-payloads/p0-audit/data/raw/uav/Images.zip")   # TUM2TWIN Images.zip (the example images carry no EXIF)


def main():
    rows = []
    zf = zipfile.ZipFile(ZIP)
    members = {Path(n).name: n for n in zf.namelist() if n.upper().endswith(".JPG")}
    names = sorted(members)
    for p in sorted(IMG.glob("*.JPG")):
        data = zf.read(members[p.name]) if p.name in members else p.read_bytes()
        im = Image.open(io.BytesIO(data))
        ex = im.getexif()
        tags = {TAGS.get(k, k): v for k, v in ex.items()}
        sub = {TAGS.get(k, k): v for k, v in ex.get_ifd(0x8769).items()}
        gps = {GPSTAGS.get(k, k): v for k, v in ex.get_ifd(0x8825).items()}
        raw = data[:200000]
        xmp = {}
        for key in ("drone-dji:GpsLatitude", "drone-dji:RelativeAltitude", "drone-dji:GimbalPitchDegree", "drone-dji:UTCAtExposure"):
            m = re.search(re.escape(key).encode() + rb"=\"([^\"]*)\"", raw)
            if m:
                xmp[key] = m.group(1).decode(errors="replace")
        rows.append(dict(image=p.name, from_zip=p.name in members, DateTimeOriginal=str(sub.get("DateTimeOriginal", tags.get("DateTime"))), OffsetTimeOriginal=str(sub.get("OffsetTimeOriginal")),
                         GPSDateStamp=str(gps.get("GPSDateStamp")), GPSTimeStamp=str(gps.get("GPSTimeStamp")), Model=str(tags.get("Model")), xmp=xmp))
    jdump(B0 / "prep/image_times.json", dict(images=rows, source=str(IMG), zip=str(ZIP), zip_jpg_count=len(names), zip_first=names[0], zip_last=names[-1],
                                             made=now(), scientific_verdict=None))
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
