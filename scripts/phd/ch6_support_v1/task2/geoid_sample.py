"""Sample the BKG GCG2016 quasigeoid GeoTIFF at given lon/lat (bilinear), reading GeoTIFF tags with PIL.
Usage: python3 -I geoid_sample.py <tif> lon,lat [lon,lat ...]"""
import sys
import numpy as np
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
im = Image.open(sys.argv[1])
tags = im.tag_v2
scale = tags.get(33550); tie = tags.get(33922); gkd = tags.get(34735); nodata = tags.get(42113); desc = tags.get(270)
print("size", im.size, "mode", im.mode, "pixel scale", scale, "tiepoint", tie, "nodata", nodata, "description", desc)
print("geokeys", gkd)
a = np.array(im, dtype=np.float64)
print("value range", np.nanmin(a), np.nanmax(a))
sx, sy = scale[0], scale[1]; I0, J0, _, X0, Y0, _ = tie
for arg in sys.argv[2:]:
    lon, lat = map(float, arg.split(","))
    # PixelIsArea assumed; pixel centre of column i at X0 + (i + 0.5) * sx
    is_point = gkd is not None and 1025 in gkd[4::4] and gkd[4:][list(gkd[4::4]).index(1025) * 4 + 3] == 2
    off = 0.0 if is_point else 0.5
    fi = (lon - X0) / sx - off + I0; fj = (Y0 - lat) / sy - off + J0
    i0, j0 = int(np.floor(fi)), int(np.floor(fj)); di, dj = fi - i0, fj - j0
    v = (a[j0, i0] * (1 - di) * (1 - dj) + a[j0, i0 + 1] * di * (1 - dj) + a[j0 + 1, i0] * (1 - di) * dj + a[j0 + 1, i0 + 1] * di * dj)
    print(f"lon {lon} lat {lat}: zeta = {v:.4f} m (nearest {a[int(round(fj)), int(round(fi))]:.4f}; raster type PixelIsPoint={is_point})")
