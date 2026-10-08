"""Replace the brand image and regenerate packaged PNGs. Dev-only dependency: Pillow.

    python3 scripts/build-icons.py path/to/new-image.png
    python3 scripts/build-icons.py  # regenerate from the checked-in source
"""
from __future__ import annotations
import argparse
import pathlib
from PIL import Image, ImageOps

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'extension/assets/brand.png'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', nargs='?', type=pathlib.Path, default=SOURCE)
    args = parser.parse_args()
    # Validate before replacing the previous source; always keep the complete supplied artwork.
    with Image.open(args.image) as original:
        original.load()
        image = original.convert('RGBA')
    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    if args.image.resolve() != SOURCE.resolve():
        image.save(SOURCE, format='PNG')
    dest = SOURCE.parent / 'icons'
    dest.mkdir(exist_ok=True)
    for size in (16, 32, 48, 128):
        fitted = ImageOps.contain(image, (size, size), Image.Resampling.LANCZOS)
        icon = Image.new('RGBA', (size, size))
        icon.paste(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
        icon.save(dest / f'icon-{size}.png')
    print('Updated extension/assets/brand.png and icons (16, 32, 48, 128). Reload the extension.')

if __name__ == '__main__':
    main()
