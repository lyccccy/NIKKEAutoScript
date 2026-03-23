#!/usr/bin/env python3
"""
Import selected FindText templates from DoroHelper PicLib.ahk and export them to PNG files.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import cv2
import numpy as np

FINDTEXT_CHARS = '0123456789+/ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

TARGETS = {
    '推图·放大镜': 'MINIMAP_ZOOM_ICON.png',
    '推图·红色的三角': 'MINIMAP_ENEMY_TRIANGLE.png',
    '推图·地图的指针': 'MINIMAP_MAP_POINTER.png',
    '推图·红色的圈': 'MINIMAP_ENEMY_CIRCLE.png',
}


def base64_to_bitstring(encoded: str) -> str:
    table = {ch: f'{idx:06b}' for idx, ch in enumerate(FINDTEXT_CHARS)}
    bits = ''.join(table[ch] for ch in encoded if ch in table)
    # Same trimming behavior as FindText().base64tobit()
    bits = re.sub(r'10*$', '', bits)
    return bits


def decode_findtext_bitmap(width: int, encoded: str) -> np.ndarray:
    bits = base64_to_bitstring(encoded)
    if width <= 0:
        raise ValueError(f'Invalid width: {width}')
    if len(bits) < width:
        raise ValueError(f'Not enough bits for width={width}, got={len(bits)}')

    height = len(bits) // width
    bits = bits[: width * height]
    arr = np.fromiter((1 if ch == '1' else 0 for ch in bits), dtype=np.uint8, count=len(bits)).reshape(height, width)
    # Export as RGB image for Template loading compatibility.
    img = np.repeat((arr * 255)[:, :, None], repeats=3, axis=2)
    return img


def parse_piclib(piclib_text: str) -> dict[str, tuple[int, str]]:
    pattern = re.compile(r'PicLib\("\|<([^>]+)>[^$]*\$(\d+)\.([0-9A-Za-z+/]+)"')
    entries = {}
    for match in pattern.finditer(piclib_text):
        name, width, encoded = match.group(1), int(match.group(2)), match.group(3)
        entries[name] = (width, encoded)
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--piclib', type=Path, required=True, help='Path to DoroHelper/lib/PicLib.ahk')
    parser.add_argument('--outdir', type=Path, required=True, help='Output directory for PNG templates')
    args = parser.parse_args()

    piclib_text = args.piclib.read_text(encoding='utf-8')
    entries = parse_piclib(piclib_text)
    args.outdir.mkdir(parents=True, exist_ok=True)

    missing = []
    for name, out_name in TARGETS.items():
        if name not in entries:
            missing.append(name)
            continue
        width, encoded = entries[name]
        image = decode_findtext_bitmap(width, encoded)
        out_file = args.outdir / out_name
        cv2.imwrite(str(out_file), cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
        print(f'Exported: {name} -> {out_file}')

    if missing:
        print(f'Missing templates: {missing}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

