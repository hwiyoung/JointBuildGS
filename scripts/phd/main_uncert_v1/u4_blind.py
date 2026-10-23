"""PHD-MAIN-UNCERT-v1 8.7 check: copies of the figures with the title cut off (the top 0.3 inch at 300 dpi = 90 pixels, where every
figure's title is drawn) for a reader who has not seen the titles.

  python u4_blind.py <figure folder name> <name ...>   -> /out/work/blind/<name>.png   scientific_verdict: null."""
import sys

from PIL import Image

sys.path.insert(0, "/repo/scripts/phd/main_uncert_v1")
import uc_common as U  # noqa: E402

if __name__ == "__main__":
    folder = sys.argv[1]
    O = U.WORK / "blind"
    O.mkdir(parents=True, exist_ok=True)
    for nm in sys.argv[2:]:
        im = Image.open(U.DOCS / "figures" / folder / f"{nm}.png")
        w, h = im.size
        im.crop((0, 90, w, h)).save(O / f"{nm}.png")
        U.log(nm, w, h)
