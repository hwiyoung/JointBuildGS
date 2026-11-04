"""Create bounded-size inspection copies; publication figures are unchanged."""
from common import *
from PIL import Image
import sys

if __name__ == '__main__':
    dest = O / 'validation' / 'previews'
    dest.mkdir(parents=True, exist_ok=True)
    for prior in sys.argv[1:]:
        for number in range(3, 8):
            source = D / 'figures' / f'그림7_{number}_{prior}.png'
            with Image.open(source) as im:
                im.thumbnail((2100, 1500), Image.Resampling.LANCZOS)
                im.save(dest / source.name)
